# Subtitle Generator

A Python tool that uses OpenAI's Whisper (CPU-only) to generate subtitles for video files.

## Requirements

- Python 3.7+
- FFmpeg (for audio extraction)

## Installation

1. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Install FFmpeg:
   - Download from https://ffmpeg.org/download.html
   - Add to your system PATH

## Usage

### Command Line Tool

Run the script with one or more video file paths:

```
python subgen.py video1.mp4 video2.avi
```

For each video file, the tool will:
1. Extract audio to a temporary WAV file using FFmpeg
2. Transcribe the audio using OpenAI Whisper (base model on CPU)
3. Generate an SRT subtitle file with the same base name as the video
4. Clean up the temporary audio file

## API Server

The tool also includes an asynchronous API server for task-based subtitle generation.

### Running the API Server

#### Using Docker Compose (Recommended)

1. Place your video files in the `videos/` directory
2. Run:
   ```bash
   docker-compose up --build
   ```

#### Manual Docker Build

```bash
docker build -t subgen-api .
docker run -p 8000:8000 -v $(pwd)/videos:/app/videos subgen-api
```

#### Direct Python

```bash
pip install -r requirements.txt
python app.py
```

Or with uvicorn:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### API Endpoints

#### POST /generate-subtitles

Start a subtitle generation task.

**Request Body:**
```json
{
  "video_path": "path/to/video.mp4"
}
```

**Response:**
```json
{
  "task_id": "uuid-string"
}
```

#### GET /task/{task_id}

Check task status.

**Response:**
```json
{
  "status": "pending|completed|error",
  "srt_path": "path/to/video.srt",
  "error": "error message if failed"
}
```

### API Usage Example

```bash
# Start processing
curl -X POST http://localhost:8000/generate-subtitles -H "Content-Type: application/json" -d '{"video_path": "myvideo.mp4"}'

# Response: {"task_id": "123e4567-e89b-12d3-a456-426614174000"}

# Check status
curl http://localhost:8000/task/123e4567-e89b-12d3-a456-426614174000

# When completed: {"status": "completed", "srt_path": "myvideo.srt"}
```

## Output

- SRT files will be created in the same directory as the input videos
- Example: `video1.mp4` → `video1.srt`

## Notes

- Uses the "base" Whisper model for processing (you can change to "small", "medium", etc. in the code)
- Runs on CPU only (no GPU required)
- Processing time depends on video length and your CPU
- API server uses background tasks for asynchronous processing