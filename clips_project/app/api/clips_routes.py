import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clips", tags=["Clips"])

@router.get(
    "",
    summary="List all ready-to-upload clips"
)
def list_clips() -> List[Dict[str, Any]]:
    """
    Returns all generated reels in data/Final_Clip/ along with their paired metadata JSONs.
    """
    settings.ensure_directories()
    clips_list = []

    # Find all json files in Final_Clip/
    json_files = sorted(settings.final_clip_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for jf in json_files:
        base_name = jf.stem
        mp4_path = settings.final_clip_dir / f"{base_name}.mp4"
        if mp4_path.exists():
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["name"] = base_name
                metadata["video_url"] = f"/clips/{base_name}/video"
                metadata["metadata_url"] = f"/clips/{base_name}"
                clips_list.append(metadata)
            except Exception as e:
                logger.error(f"Error reading metadata from {jf}: {e}")

    return clips_list

@router.get(
    "/{name}",
    summary="Get metadata for a specific clip"
)
def get_clip_metadata(name: str) -> Dict[str, Any]:
    """
    Retrieves the paired metadata JSON for a clip given its base name.
    """
    json_file = settings.final_clip_dir / f"{name}.json"
    if not json_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clip metadata '{name}' not found in {settings.final_clip_dir.name}."
        )

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        metadata["name"] = name
        metadata["video_url"] = f"/clips/{name}/video"
        return metadata
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed reading clip metadata: {str(e)}"
        )

@router.get(
    "/{name}/video",
    summary="Stream or download the reel MP4"
)
def get_clip_video(name: str):
    """
    Returns the ready-to-upload MP4 video file.
    """
    video_file = settings.final_clip_dir / f"{name}.mp4"
    if not video_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file for '{name}' not found in {settings.final_clip_dir.name}."
        )

    return FileResponse(
        path=str(video_file),
        media_type="video/mp4",
        filename=video_file.name
    )
