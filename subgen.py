import sys
import os
import subprocess
from faster_whisper import WhisperModel

def extract_audio(video_path, audio_path):
    """Extract audio from video file using ffmpeg."""
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # no video
        "-acodec", "pcm_s16le",  # WAV format
        "-ar", "16000",  # 16kHz sample rate (good for Whisper/Kotoba-Whisper)
        "-ac", "1",  # mono
        audio_path,
        "-y"  # overwrite
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def transcribe_audio(audio_path):
    """Transcribe audio using Kotoba-Whisper v2.0 Faster on CPU."""
    # Use the kotoba-whisper model
    model = WhisperModel("kotoba-tech/kotoba-whisper-v2.0-faster",
                         device="cpu",
                         compute_type="int8")  # or "float16" if int8 gives too many errors

    # Use Japanese, chunk_length to avoid huge memory usage for long files
    segments, info = model.transcribe(
        audio_path,
        language="ja",
        beam_size=5,
        chunk_length=15,  # seconds; adjust based on memory / latency
        condition_on_previous_text=False
    )
    segment_list = list(segments)
    # Optionally: combine text if needed
    text = " ".join([seg.text for seg in segment_list])
    return text, segment_list

def generate_srt(segments, output_path):
    """Generate SRT subtitle file from transcription segments."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            start = segment.start
            end = segment.end
            text = segment.text.strip()
            if not text:
                continue
            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(f"{text}\n\n")

def format_time(seconds: float) -> str:
    """Format seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python subgen.py <video_file1> <video_file2> ...")
        sys.exit(1)

    for video_path in sys.argv[1:]:
        if not os.path.exists(video_path):
            print(f"Error: File '{video_path}' does not exist.")
            continue

        base_name = os.path.splitext(video_path)[0]
        audio_path = base_name + "_temp.wav"
        srt_path = base_name + ".srt"

        try:
            print(f"Processing {video_path}...")
            print("Extracting audio...")
            extract_audio(video_path, audio_path)
            print("Transcribing audio (Japanese)...")
            text, segments = transcribe_audio(audio_path)
            print("Generating subtitles...")
            generate_srt(segments, srt_path)
            print(f"Subtitles saved to '{srt_path}'")
        except Exception as e:
            print(f"Error processing '{video_path}': {str(e)}")
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"Temporary audio file '{audio_path}' removed.")

    print("All files processed.")
