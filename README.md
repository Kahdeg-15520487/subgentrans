# Subtitle Generator

A Python tool that uses Faster Whisper (CTranslate2 implementation) to generate subtitles for video files, with automatic translation to English using DeepSeek API.

## Requirements

- Python 3.7+
- FFmpeg (for audio extraction)
- DeepSeek API key (for translation to English)

## Installation

1. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Install FFmpeg:
   - Download from https://ffmpeg.org/download.html
   - Add to your system PATH

3. Set up DeepSeek API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your DeepSeek API key
   export DEEPSEEK_API_KEY="your-api-key-here"
   ```
   Get your API key from [DeepSeek Platform](https://platform.deepseek.com/)

   **Note:** If no API key is provided, the tool will generate Japanese subtitles without translation.

## Usage

### Command Line Tool

Run the script with one or more video file paths:

```
python subgen.py video1.mp4 video2.avi
```

For each video file, the tool will:
1. Extract audio to a temporary WAV file using FFmpeg
2. Transcribe the audio using Faster Whisper (base model on CPU)
3. Translate Japanese text to English using DeepSeek API (with contextual batch processing for improved accuracy)
4. Generate an SRT subtitle file with the same base name as the video
5. Clean up the temporary audio file

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

The API processes videos asynchronously and generates English subtitles from Japanese audio using DeepSeek translation with contextual batch processing for improved accuracy.

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
  "error": "error message if failed",
  "timing": {
    "audio_extraction": 2.34,
    "transcription": 45.67,
    "translation": 12.89,
    "srt_generation": 0.12,
    "cleanup": 0.01,
    "total": 61.03
  }
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

## Translation Features

- **Contextual Translation**: Each segment includes the previous 3 segments as context for more accurate translations
- **Batch Processing**: Segments are processed in batches of 5 for better API efficiency (configurable)
- **Fallback Handling**: Gracefully falls back to original Japanese text if translation fails
- **Cost Optimization**: Reduced API calls through batching
- **Performance Monitoring**: Detailed timing information for each processing stage

## Local Model Setup (Optional)

For faster startup and offline usage, you can download the Kotoba-Whisper model locally:

### Download Kotoba-Whisper Model

```bash
# Option 1: Use the provided script
python download_model.py

# Option 2: Manual download with huggingface-cli
pip install huggingface_hub
huggingface-cli download kotoba-tech/kotoba-whisper-v2.0-faster --local-dir models/kotoba-whisper-v2.0-faster --local-dir-use-symlinks False
```

### Alternative: Manual Download

You can also manually download the model files from the [Hugging Face model page](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0-faster) and place them in `models/kotoba-whisper-v2.0-faster/`.

### Benefits of Local Models

- **Faster startup**: No download time on first run
- **Offline usage**: Works without internet connection
- **Reliability**: No dependency on external downloads
- **Version control**: Keep specific model versions

If the local model folder `models/kotoba-whisper-v2.0-faster` exists, the application will automatically use it. Otherwise, it will download the model as before.