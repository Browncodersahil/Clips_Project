import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

def get_media_duration(file_path: Path) -> float:
    """Uses ffprobe to obtain exact duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(file_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    except Exception as e:
        logger.warning(f"Could not probe duration for {file_path}: {e}")
        return 0.0

def extract_and_chunk_audio(
    video_path: Path,
    video_id: str,
    force: bool = False
) -> List[Dict[str, Any]]:
    """
    Extracts 16kHz mono audio from the video and chunks it with overlap.
    Full audio -> data/audio/<video_id>.mp3
    Chunks -> data/chunks/<video_id>_chunk_000.mp3
    """
    settings.ensure_directories()
    full_audio_path = settings.audio_dir / f"{video_id}.mp3"

    # Step 1: Extract full audio if not cached
    if not full_audio_path.exists() or force:
        logger.info(f"Extracting full audio to {full_audio_path}...")
        cmd_extract = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "64k",
            str(full_audio_path)
        ]
        res = subprocess.run(cmd_extract, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg audio extraction failed: {res.stderr}")
            raise RuntimeError(f"FFmpeg failed to extract audio: {res.stderr}")
    else:
        logger.info(f"Using cached full audio: {full_audio_path}")

    total_duration = get_media_duration(full_audio_path)
    if total_duration <= 0:
        total_duration = get_media_duration(video_path)

    logger.info(f"Audio duration: {total_duration:.2f} seconds")

    chunk_size = settings.CHUNK_SECONDS
    overlap = settings.CHUNK_OVERLAP_SECONDS
    step = chunk_size - overlap

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0
    current_offset = 0.0

    # If stream is very short, single chunk
    if total_duration <= chunk_size:
        chunk_file = settings.chunks_dir / f"{video_id}_chunk_0000.mp3"
        if not chunk_file.exists() or force:
            # Copy full audio or extract slice
            cmd = [
                "ffmpeg", "-y",
                "-i", str(full_audio_path),
                "-c", "copy",
                str(chunk_file)
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [{
            "chunk_path": chunk_file,
            "offset_seconds": 0.0,
            "duration": total_duration,
            "index": 0
        }]

    while current_offset < total_duration:
        chunk_file = settings.chunks_dir / f"{video_id}_chunk_{chunk_index:04d}.mp3"
        duration_to_cut = min(float(chunk_size), total_duration - current_offset)

        if duration_to_cut <= 2.0:  # Skip tiny residual chunks under 2s
            break

        if not chunk_file.exists() or force:
            cmd_cut = [
                "ffmpeg",
                "-y",
                "-ss", str(current_offset),
                "-t", str(duration_to_cut),
                "-i", str(full_audio_path),
                "-c", "copy",
                str(chunk_file)
            ]
            res = subprocess.run(cmd_cut, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error(f"Failed cutting chunk {chunk_index}: {res.stderr}")
                raise RuntimeError(f"FFmpeg failed cutting chunk: {res.stderr}")

        chunks.append({
            "chunk_path": chunk_file,
            "offset_seconds": current_offset,
            "duration": duration_to_cut,
            "index": chunk_index
        })

        chunk_index += 1
        current_offset += step

    logger.info(f"Generated {len(chunks)} audio chunks for transcription.")
    return chunks
