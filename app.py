from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
import os
import requests
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
    translated_text = result["choices"][0]["message"]["content"].strip()

    return translated_text


def translate_segments(segments, target_lang: str = "en"):
    """Translate all segments to target language."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Warning: DEEPSEEK_API_KEY not set, skipping translation")
        return segments  # Return original segments if no API key

    translated_segments = []
    for segment in segments:
        try:
            translated_text = translate_text(segment.text, target_lang)
            # Create a new segment-like object with translated text
            translated_segment = type('TranslatedSegment', (), {
                'start': segment.start,
                'end': segment.end,
                'text': translated_text
            })()
            translated_segments.append(translated_segment)
        except Exception as e:
            print(f"Translation failed for segment: {e}")
            # Fall back to original text if translation fails
            translated_segments.append(segment)

    return translated_segments


def process_video(task_id: str, video_path: str):
    """Background task to process video and generate subtitles."""
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
        extract_audio(full_video_path, audio_path)

        # Transcribe
        text, segments = transcribe_audio(audio_path)

        # Translate segments to English
        print("Translating to English...")
        translated_segments = translate_segments(segments, "en")

        # Generate SRT
        generate_srt(translated_segments, srt_path)        # Cleanup
        os.remove(audio_path)

        tasks[task_id] = {"status": "completed", "srt_path": srt_path}

    except Exception as e:
        tasks[task_id] = {"status": "error", "error": str(e)}


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
