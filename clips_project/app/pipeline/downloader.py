import re
import shutil
import logging
from pathlib import Path
from typing import Dict, Any
import yt_dlp
from app.config import settings

logger = logging.getLogger(__name__)

def sanitize_filename(name: str) -> str:
    """Sanitize string to produce safe, clean filenames."""
    cleaned = re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")
    return cleaned[:80] if len(cleaned) > 80 else cleaned

def download_video(url_or_path: str, force: bool = False) -> Dict[str, Any]:
    """
    Downloads a video from Kick (or uses an existing local video), returning metadata and path.
    Saves to data/downloads/<video_id>.mp4.
    """
    local_path = Path(url_or_path)
    if local_path.is_file():
        logger.info(f"Using local video input: {local_path}")
        video_id = sanitize_filename(local_path.stem)
        target_path = settings.downloads_dir / f"{video_id}.mp4"
        if not target_path.exists() or force:
            shutil.copy2(local_path, target_path)
        return {
            "video_path": target_path,
            "video_id": video_id,
            "title": local_path.stem,
            "uploader": "Streamer",
            "duration": 0.0,
            "url": str(local_path.resolve())
        }

    logger.info(f"Extracting Kick video metadata from: {url_or_path}")
    ydl_opts_info = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url_or_path, download=False)
    except Exception as e:
        logger.error(f"Failed to fetch metadata from {url_or_path}: {e}")
        raise ValueError(f"Could not retrieve video from {url_or_path}: {str(e)}")

    if not info:
        raise ValueError(f"No stream or VOD found for URL: {url_or_path}")

    raw_id = str(info.get("id") or info.get("title", "kick_stream"))
    video_id = sanitize_filename(raw_id)
    title = info.get("title") or "Kick Stream"
    uploader = info.get("uploader") or info.get("channel") or "KickStreamer"
    duration = float(info.get("duration") or 0.0)

    output_filename = f"{video_id}.mp4"
    output_path = settings.downloads_dir / output_filename

    if output_path.exists() and not force:
        logger.info(f"Cached video found: {output_path} (skipping download)")
        return {
            "video_path": output_path,
            "video_id": video_id,
            "title": title,
            "uploader": uploader,
            "duration": duration,
            "url": url_or_path
        }

    logger.info(f"Downloading stream/video to {output_path}...")
    ydl_opts_download = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(settings.downloads_dir / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([url_or_path])
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise RuntimeError(f"Failed downloading video: {e}")

    if not output_path.exists():
        matches = list(settings.downloads_dir.glob(f"{video_id}.*"))
        if matches:
            output_path = matches[0]
        else:
            raise FileNotFoundError(f"Downloaded file not found at {output_path}")

    logger.info(f"Download completed: {output_path}")
    return {
        "video_path": output_path,
        "video_id": video_id,
        "title": title,
        "uploader": uploader,
        "duration": duration,
        "url": url_or_path
    }
