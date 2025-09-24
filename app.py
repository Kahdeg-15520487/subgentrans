from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
import os
import requests
import time
import re
from subgen import extract_audio, transcribe_audio, generate_srt

app = FastAPI(
    title="Subtitle Generator API",
    description="Asynchronous subtitle generation using Faster Whisper",
)

# Task storage (in production, use Redis or database)
tasks = {}

# Mounted directory for videos
MOUNT_DIR = "videos"


class GenerateRequest(BaseModel):
    video_path: str  # Relative path from mounted directory


class TaskResponse(BaseModel):
    status: str  # "pending", "completed", "error"
    srt_path: str = None
    error: str = None
    timing: dict = None  # Timing information for completed tasks


def translate_text(text: str, target_lang: str = "en") -> str:
    """Translate text using DeepSeek API."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = f"Translate the following Japanese text to English. Only return the translation, no explanations:\n\n{text}"

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()

    # Validate response structure
    if not result.get("choices") or len(result["choices"]) == 0:
        raise ValueError("Invalid API response: no choices returned")

    message = result["choices"][0].get("message")
    if not message or "content" not in message:
        raise ValueError("Invalid API response: no content in message")

    translated_text = message["content"]
    if translated_text is None:
        raise ValueError("API returned None for content")

    return translated_text.strip()


def translate_segments_batch(segments, target_lang: str = "en", batch_size: int = 5):
    """Translate segments in batches with context from previous segments."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Warning: DEEPSEEK_API_KEY not set, skipping translation")
        return segments  # Return original segments if no API key

    translated_segments = []

    # Process segments in batches
    for i in range(0, len(segments), batch_size):
        batch = segments[i:i + batch_size]

        # Create contextual translations for this batch
        batch_translations = translate_batch_with_context(batch, target_lang)

        # Add translated segments
        for j, translated_text in enumerate(batch_translations):
            segment_idx = i + j
            if segment_idx < len(segments):
                original_segment = segments[segment_idx]

                # Create translated segment
                translated_segment = type('TranslatedSegment', (), {
                    'start': original_segment.start,
                    'end': original_segment.end,
                    'text': translated_text
                })()
                translated_segments.append(translated_segment)

    return translated_segments


def translate_batch_with_context(segments_batch, target_lang: str = "en"):
    """Translate a batch of segments with context from previous segments."""
    if not segments_batch:
        return []

    # Build context-aware prompt
    prompt_parts = []
    prompt_parts.append(f"Translate the following Japanese text segments to English. Maintain the same number of segments in your response. Each segment should be on a new line. Only return the translations, no explanations:\n")

    for i, segment in enumerate(segments_batch):
        # Include context from previous segments (up to 3)
        context_segments = []
        for j in range(max(0, i-3), i):
            if j >= 0:
                context_segments.append(f"[{j+1}] {segments_batch[j].text}")

        if context_segments:
            context_text = " | ".join(context_segments)
            prompt_parts.append(f"Context: {context_text}")

        prompt_parts.append(f"[{i+1}] {segment.text}")

    full_prompt = "\n".join(prompt_parts)

    try:
        # Make single API call for the batch
        translated_batch_text = translate_text_batch(full_prompt, target_lang)
        print(f"[{len(segments_batch)} segments] API response received, length: {len(translated_batch_text) if translated_batch_text else 0}")

        # Parse the response - expect one translation per line
        translations = [line.strip() for line in translated_batch_text.split('\n') if line.strip()]
        print(f"Parsed {len(translations)} translations from response")

        # Remove numbering prefixes like [1], [2], etc.
        cleaned_translations = []
        for trans in translations:
            # Remove patterns like [1], [2], etc. from the beginning
            cleaned = re.sub(r'^\[\d+\]\s*', '', trans).strip()
            cleaned_translations.append(cleaned)

        translations = cleaned_translations
        print(f"After cleaning: {len(translations)} translations")

        # Ensure we have the right number of translations
        if len(translations) != len(segments_batch):
            print(f"Warning: Expected {len(segments_batch)} translations, got {len(translations)}")
            # Fall back to individual translations if batch parsing fails
            return [translate_text(segment.text, target_lang) for segment in segments_batch]

        return translations

    except Exception as e:
        print(f"Batch translation failed: {e}")
        # Fall back to individual translations
        return [translate_text(segment.text, target_lang) for segment in segments_batch]


def translate_text_batch(text: str, target_lang: str = "en") -> str:
    """Translate text using DeepSeek API (for batch processing)."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": text}
        ],
        "max_tokens": 2000,  # Larger for batch processing
        "temperature": 0.1
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()

    # Validate response structure
    if not result.get("choices") or len(result["choices"]) == 0:
        raise ValueError("Invalid API response: no choices returned")

    message = result["choices"][0].get("message")
    if not message or "content" not in message:
        raise ValueError("Invalid API response: no content in message")

    translated_text = message["content"]
    if translated_text is None:
        raise ValueError("API returned None for content")

    return translated_text.strip()


def process_video(task_id: str, video_path: str):
    """Background task to process video and generate subtitles."""
    start_time = time.time()
    print(f"[{task_id}] Starting processing for {video_path}")

    try:
        full_video_path = os.path.join(MOUNT_DIR, video_path)
        if not os.path.exists(full_video_path):
            tasks[task_id] = {
                "status": "error",
                "error": "Video file not found at " + full_video_path,
            }
            return

        base_name = os.path.splitext(full_video_path)[0]
        audio_path = base_name + "_temp.wav"
        srt_path = base_name + ".srt"

        # Extract audio
        audio_start = time.time()
        print(f"[{task_id}] Extracting audio...")
        extract_audio(full_video_path, audio_path)
        audio_time = time.time() - audio_start
        print(f"[{task_id}] Audio extraction: {audio_time:.2f}s")

        # Transcribe
        transcribe_start = time.time()
        print(f"[{task_id}] Transcribing audio...")
        text, segments = transcribe_audio(audio_path)
        transcribe_time = time.time() - transcribe_start
        print(f"[{task_id}] Transcription: {transcribe_time:.2f}s")

        # Translate segments to English
        translate_start = time.time()
        print(f"[{task_id}] Translating to English...")
        translated_segments = translate_segments_batch(segments, "en")
        translate_time = time.time() - translate_start
        print(f"[{task_id}] Translation: {translate_time:.2f}s")

        # Generate SRT
        srt_start = time.time()
        print(f"[{task_id}] Generating SRT...")
        generate_srt(translated_segments, srt_path)
        srt_time = time.time() - srt_start
        print(f"[{task_id}] SRT generation: {srt_time:.2f}s")

        # Cleanup
        cleanup_start = time.time()
        os.remove(audio_path)
        cleanup_time = time.time() - cleanup_start
        print(f"[{task_id}] Cleanup: {cleanup_time:.2f}s")

        total_time = time.time() - start_time
        tasks[task_id] = {
            "status": "completed",
            "srt_path": srt_path,
            "timing": {
                "audio_extraction": round(audio_time, 2),
                "transcription": round(transcribe_time, 2),
                "translation": round(translate_time, 2),
                "srt_generation": round(srt_time, 2),
                "cleanup": round(cleanup_time, 2),
                "total": round(total_time, 2)
            }
        }

        print(f"[{task_id}] Processing completed in {total_time:.2f}s")

    except Exception as e:
        total_time = time.time() - start_time
        error_msg = str(e)
        tasks[task_id] = {
            "status": "error",
            "error": error_msg,
            "timing": {
                "total": round(total_time, 2),
                "error_at": round(total_time, 2)
            }
        }
        print(f"[{task_id}] Processing failed after {total_time:.2f}s: {error_msg}")


@app.post("/generate-subtitles", response_model=dict)
async def generate_subtitles(
    request: GenerateRequest, background_tasks: BackgroundTasks
):
    """Start subtitle generation task."""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "pending"}

    background_tasks.add_task(process_video, task_id, request.video_path)

    return {"task_id": task_id}


@app.get("/task/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status and result."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    return TaskResponse(**task)


@app.get("/")
async def root():
    return {"message": "Subtitle Generator API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
