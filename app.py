from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
import os
from subgen import extract_audio, transcribe_audio, generate_srt

app = FastAPI(
    title="Subtitle Generator API",
    description="Asynchronous subtitle generation using Faster Whisper",
)

# Task storage (in production, use Redis or database)
tasks = {}

# Mounted directory for videos
MOUNT_DIR = "/app/videos"


class GenerateRequest(BaseModel):
    video_path: str  # Relative path from mounted directory


class TaskResponse(BaseModel):
    status: str  # "pending", "completed", "error"
    srt_path: str = None
    error: str = None


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

        # Generate SRT
        generate_srt(segments, srt_path)

        # Cleanup
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
