import logging
import shutil
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
from app.config import settings
from app.schemas import JobStage, Transcript
from app.pipeline.downloader import download_video
from app.pipeline.audio import extract_and_chunk_audio
from app.pipeline.transcribe import transcribe_chunks_and_merge
from app.pipeline.highlights import find_highlights
from app.pipeline.clipper import cut_clips
from app.pipeline.editor import edit_reel

logger = logging.getLogger(__name__)

def run_pipeline(
    kick_url: str,
    max_clips: Optional[int] = 0,
    min_score: int = 7,
    layout: str = "blur",
    force: bool = False,
    keep_temp: bool = False,
    brief_path: Optional[str] = None,
    logo_path: Optional[str] = None,
    progress_callback: Optional[Callable[[JobStage, int], None]] = None
) -> Dict[str, Any]:
    """
    Executes the full pipeline sequentially with progress reporting:
    1. Download video (0% -> 15%)
    2. Extract & chunk audio (15% -> 20%)
    3. Transcribe with Groq Whisper & merge timestamps (20% -> 55%)
    4. Detect highlights with Groq LLM applying creator brief if present (55% -> 65%)
    5. Cut raw clips with ffmpeg (65% -> 75%)
    6. Render vertical reels with small captions, creator logo at bottom, & loudnorm into Final_Clip/ (75% -> 100%)
    """
    def update_progress(stage: JobStage, pct: int):
        if progress_callback:
            progress_callback(stage, pct)

    settings.ensure_directories()
    failed_clips: List[str] = []
    completed_clips: List[str] = []

    actual_max_clips = max_clips if max_clips is not None else settings.MAX_CLIPS
    if actual_max_clips and actual_max_clips > 0:
        logger.info(f"Clip target limit: up to {actual_max_clips} clips with score >= {min_score}")
    else:
        logger.info(f"Clip target limit: MAXIMUM / UNLIMITED clips with score >= {min_score} from entire stream")

    # Check for creator brief and logo
    creator_brief = settings.get_creator_brief(brief_path)
    if creator_brief:
        logger.info(f"Loaded creator brief ({len(creator_brief)} chars) to guide highlight detection.")
    else:
        logger.info("No creator brief found. Proceeding with standard viral highlight detection.")

    active_logo = settings.get_creator_logo_path(logo_path)
    if active_logo and active_logo.is_file():
        logger.info(f"Loaded creator logo from {active_logo} to watermark at bottom.")
    else:
        logger.info("No creator logo found. Final clips will be rendered without logo overlay.")

    # 1. Download
    update_progress(JobStage.DOWNLOADING, 5)
    video_info = download_video(kick_url, force=force)
    video_path: Path = video_info["video_path"]
    video_id: str = video_info["video_id"]
    update_progress(JobStage.DOWNLOADING, 15)

    # 2. Extract and chunk audio
    update_progress(JobStage.EXTRACTING_AUDIO, 16)
    chunks = extract_and_chunk_audio(video_path=video_path, video_id=video_id, force=force)
    update_progress(JobStage.EXTRACTING_AUDIO, 20)

    # 3. Transcribe
    update_progress(JobStage.TRANSCRIBING, 25)
    transcript: Transcript = transcribe_chunks_and_merge(
        chunks=chunks,
        video_id=video_id,
        source_url=kick_url,
        force=force
    )
    update_progress(JobStage.TRANSCRIBING, 55)

    # 4. Highlights detection (with creator brief)
    update_progress(JobStage.FINDING_HIGHLIGHTS, 58)
    highlights = find_highlights(
        transcript=transcript,
        video_id=video_id,
        max_clips=actual_max_clips,
        min_score=min_score,
        force=force,
        creator_brief=creator_brief
    )
    update_progress(JobStage.FINDING_HIGHLIGHTS, 65)

    if not highlights:
        logger.warning(f"No highlights found with score >= {min_score}")
        update_progress(JobStage.DONE, 100)
        return {
            "video_id": video_id,
            "clips": [],
            "failed_clips": []
        }

    # 5. Cut raw clips
    update_progress(JobStage.CLIPPING, 68)
    raw_clips = cut_clips(
        video_path=video_path,
        highlights=highlights,
        transcript=transcript,
        video_id=video_id,
        force=force
    )
    update_progress(JobStage.CLIPPING, 75)

    # 6. Edit into final vertical reels (9:16 + small captions + creator logo at bottom + loudnorm)
    update_progress(JobStage.EDITING, 76)
    total_raw = len(raw_clips)

    for i, clip_info in enumerate(raw_clips):
        idx = clip_info["index"]
        clip_name = f"{video_id}_{idx:02d}_s{clip_info['highlight'].score}"
        try:
            logger.info(f"Processing reel {i+1}/{total_raw}: {clip_name}")
            res = edit_reel(
                raw_clip_info=clip_info,
                transcript=transcript,
                video_id=video_id,
                source_url=kick_url,
                layout=layout,
                force=force,
                logo_path=active_logo
            )
            completed_clips.append(res["name"])
        except Exception as e:
            logger.error(f"Error editing clip {clip_name}: {e}")
            failed_clips.append(f"{clip_name}: {str(e)}")

        # Fractional progress between 75% and 98%
        pct = 75 + int(((i + 1) / total_raw) * 23)
        update_progress(JobStage.EDITING, min(pct, 98))

    # Optional cleanup of audio chunks to save disk space
    if not keep_temp:
        logger.info("Cleaning up temporary audio chunks...")
        for c in chunks:
            chunk_file: Path = c["chunk_path"]
            if chunk_file.exists():
                try:
                    chunk_file.unlink()
                except Exception as e:
                    logger.debug(f"Could not delete temp chunk {chunk_file}: {e}")

    update_progress(JobStage.DONE, 100)
    logger.info(f"Pipeline finished! Completed {len(completed_clips)} clips in {settings.final_clip_dir}")

    return {
        "video_id": video_id,
        "clips": completed_clips,
        "failed_clips": failed_clips
    }
