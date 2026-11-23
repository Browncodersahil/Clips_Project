import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.schemas import Transcript, HighlightItem

logger = logging.getLogger(__name__)

def snap_to_word_boundaries(
    target_start: float,
    target_end: float,
    transcript: Transcript,
    padding: float = 1.0
) -> Tuple[float, float]:
    """
    Snaps target_start and target_end to natural segment boundaries so words are not cut in half,
    and applies a safety padding.
    """
    if not transcript.segments:
        return max(0.0, target_start - padding), target_end + padding

    # Find segment containing or closest to target_start
    snapped_start = target_start
    for seg in transcript.segments:
        if seg.start <= target_start <= seg.end:
            # Snap to start of this sentence/segment
            snapped_start = seg.start
            break
        elif seg.start > target_start:
            # Nearest upcoming segment
            snapped_start = max(0.0, seg.start)
            break

    # Find segment containing or closest to target_end
    snapped_end = target_end
    for seg in reversed(transcript.segments):
        if seg.start <= target_end <= seg.end:
            snapped_end = seg.end
            break
        elif seg.end < target_end:
            snapped_end = seg.end
            break

    # Apply padding
    final_start = max(0.0, snapped_start - padding)
    final_end = snapped_end + padding

    # Bound check against video duration if available
    if transcript.duration and final_end > transcript.duration:
        final_end = transcript.duration

    return round(final_start, 2), round(final_end, 2)

def cut_clips(
    video_path: Path,
    highlights: List[HighlightItem],
    transcript: Transcript,
    video_id: str,
    force: bool = False
) -> List[Dict[str, Any]]:
    """
    Cuts exact clips from original video with ffmpeg using frame-accurate re-encoding.
    Outputs to data/clips/<video_id>_raw_{index:02d}.mp4.
    """
    settings.ensure_directories()
    results: List[Dict[str, Any]] = []

    for idx, h in enumerate(highlights, start=1):
        raw_clip_filename = f"{video_id}_raw_{idx:02d}.mp4"
        raw_clip_path = settings.clips_dir / raw_clip_filename

        snapped_start, snapped_end = snap_to_word_boundaries(
            target_start=h.start,
            target_end=h.end,
            transcript=transcript,
            padding=settings.CLIP_PADDING_SECONDS
        )
        duration = round(snapped_end - snapped_start, 2)

        if duration <= 1.0:
            logger.warning(f"Clip {idx} duration too short ({duration}s), skipping.")
            continue

        if not raw_clip_path.exists() or force:
            logger.info(f"Cutting clip {idx}/{len(highlights)}: {snapped_start:.1f}s to {snapped_end:.1f}s ({duration:.1f}s) -> {raw_clip_path.name}")
            # Fast lossless stream copy (takes ~0.1s per clip instead of 15s)
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(snapped_start),
                "-i", str(video_path),
                "-t", str(duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                str(raw_clip_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                logger.warning(f"Stream copy failed on clip {idx}, falling back to fast encode: {res.stderr}")
                cmd_fallback = [
                    "ffmpeg",
                    "-y",
                    "-ss", str(snapped_start),
                    "-i", str(video_path),
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    "-c:a", "copy",
                    "-avoid_negative_ts", "make_zero",
                    str(raw_clip_path)
                ]
                res_fallback = subprocess.run(cmd_fallback, capture_output=True, text=True)
                if res_fallback.returncode != 0:
                    logger.error(f"FFmpeg fallback error cutting clip {idx}: {res_fallback.stderr}")
                    continue
        else:
            logger.info(f"Using cached raw clip: {raw_clip_path}")

        results.append({
            "raw_clip_path": raw_clip_path,
            "highlight": h,
            "snapped_start": snapped_start,
            "snapped_end": snapped_end,
            "duration": duration,
            "index": idx
        })

    logger.info(f"Successfully cut {len(results)} raw clips.")
    return results
