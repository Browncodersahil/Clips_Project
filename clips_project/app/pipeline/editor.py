import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings
from app.schemas import Transcript, HighlightItem, Segment, FinalClipMetadata

logger = logging.getLogger(__name__)

def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_ass_subtitles(
    segments: List[Segment],
    clip_start: float,
    clip_end: float,
    ass_path: Path,
    font_size: Optional[int] = None
) -> bool:
    """
    Generates ASS subtitle file with viral styling:
    Bold white text, black border/shadow, centered in lower third.
    Font size is sleek and small (default settings.CAPTIONS_FONT_SIZE, e.g. 42).
    Timestamps are adjusted relative to the cut clip start (0.0s).
    """
    actual_font_size = font_size or getattr(settings, "CAPTIONS_FONT_SIZE", 42)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{actual_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues: List[str] = []

    for seg in segments:
        # Check if segment words exist
        if seg.words:
            # Group words in chunks of 3 words for punchy reading
            chunk_size = 3
            for i in range(0, len(seg.words), chunk_size):
                word_chunk = seg.words[i:i + chunk_size]
                chunk_start = max(0.0, word_chunk[0].start - clip_start)
                chunk_end = min(clip_end - clip_start, word_chunk[-1].end - clip_start)

                if chunk_end > chunk_start + 0.1:
                    text = " ".join(w.word for w in word_chunk).strip().upper()
                    t_start = format_ass_time(chunk_start)
                    t_end = format_ass_time(chunk_end)
                    dialogues.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{text}")
        else:
            # Fallback to segment text
            rel_start = max(0.0, seg.start - clip_start)
            rel_end = min(clip_end - clip_start, seg.end - clip_start)
            if rel_end > rel_start + 0.2:
                text = seg.text.strip().upper()
                t_start = format_ass_time(rel_start)
                t_end = format_ass_time(rel_end)
                dialogues.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{text}")

    if not dialogues:
        return False

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogues) + "\n")

    return True

def edit_reel(
    raw_clip_info: Dict[str, Any],
    transcript: Transcript,
    video_id: str,
    source_url: str = "",
    layout: Optional[str] = None,
    force: bool = False,
    logo_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Renders 9:16 vertical video with blurred background or center crop,
    burns in sleek small captions, optionally overlays creator logo at bottom,
    and normalizes audio to -14 LUFS.
    Saves matching .mp4 and .json in Final_Clip/ with the EXACT same base name.
    """
    settings.ensure_directories()

    raw_clip_path: Path = raw_clip_info["raw_clip_path"]
    highlight: HighlightItem = raw_clip_info["highlight"]
    clip_start: float = raw_clip_info["snapped_start"]
    clip_end: float = raw_clip_info["snapped_end"]
    idx: int = raw_clip_info["index"]
    actual_layout = layout or settings.LAYOUT

    # Creator logo detection (if provided or present in briefs/)
    active_logo = logo_path if logo_path is not None else settings.get_creator_logo_path()
    has_logo = bool(active_logo and active_logo.is_file())
    if has_logo:
        logger.info(f"Applying creator logo from {active_logo.name} at bottom")
    else:
        logger.debug("No creator logo found. Rendering standard clip without logo.")

    # Shared base name: <video_id>_<idx:02d>_s<score>
    base_name = f"{video_id}_{idx:02d}_s{highlight.score}"
    final_mp4_path = settings.final_clip_dir / f"{base_name}.mp4"
    final_json_path = settings.final_clip_dir / f"{base_name}.json"

    if final_mp4_path.exists() and final_json_path.exists() and not force:
        logger.info(f"Reel already completed: {final_mp4_path.name}")
        return {
            "name": base_name,
            "mp4_path": final_mp4_path,
            "json_path": final_json_path,
            "title": highlight.title,
            "score": highlight.score
        }

    # Extract relevant segments for subtitles
    clip_segments = [
        s for s in transcript.segments
        if (s.start <= clip_end and s.end >= clip_start)
    ]

    ass_path = settings.clips_dir / f"{base_name}.ass"
    has_subtitles = generate_ass_subtitles(clip_segments, clip_start, clip_end, ass_path)

    # Prepare video filter complex using relative path to avoid Windows drive colon escaping issues
    try:
        ass_rel = ass_path.relative_to(settings.project_root).as_posix()
    except ValueError:
        ass_rel = ass_path.as_posix()

    max_w = settings.LOGO_MAX_WIDTH
    max_h = settings.LOGO_MAX_HEIGHT
    margin_b = settings.LOGO_BOTTOM_MARGIN

    parts = []
    if actual_layout == "crop":
        # Center crop to 9:16 (1080x1920)
        parts.append("[0:v]crop=ih*9/16:ih,scale=1080:1920[base_v]")
    else:
        # Blurred background + centered original video
        parts.append("[0:v]split=2[fg][bg]")
        parts.append("[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg_b]")
        parts.append("[fg]scale=1080:-1[fg_s]")
        parts.append("[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2[base_v]")

    curr = "base_v"
    if has_subtitles:
        parts.append(f"[{curr}]subtitles='{ass_rel}'[sub_v]")
        curr = "sub_v"

    if has_logo:
        parts.append(f"[1:v]scale=w={max_w}:h={max_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_s]")
        parts.append(f"[{curr}][logo_s]overlay=(W-w)/2:H-h-{margin_b}:shortest=1[v_out]")
    else:
        if curr != "v_out":
            parts.append(f"[{curr}]null[v_out]")

    filter_complex = ";".join(parts)

    logger.info(f"Rendering final reel: {final_mp4_path.name}...")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(raw_clip_path),
    ]

    if has_logo:
        cmd.extend(["-loop", "1", "-i", str(active_logo.resolve())])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "0:a?",
        "-af", f"loudnorm=I={settings.TARGET_LUFS}:LRA=11:TP=-1.5",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", str(settings.OUTPUT_FPS),
        str(final_mp4_path)
    ])

    res = subprocess.run(cmd, cwd=str(settings.project_root), capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg reel rendering failed for {base_name}: {res.stderr}")
        raise RuntimeError(f"Rendering error on {base_name}: {res.stderr}")

    # Write sidecar JSON only after successful mp4 render
    metadata = FinalClipMetadata(
        title=highlight.title,
        description=highlight.description,
        hashtags=highlight.hashtags,
        video_file=final_mp4_path.name,
        source_url=source_url,
        source_start=clip_start,
        source_end=clip_end,
        score=highlight.score,
        reason=highlight.reason,
        duration=round(clip_end - clip_start, 2),
        created_at=datetime.now(timezone.utc).isoformat()
    )

    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f, indent=2, ensure_ascii=False)

    logger.info(f"Successfully generated final pair: {final_mp4_path.name} and {final_json_path.name}")

    return {
        "name": base_name,
        "mp4_path": final_mp4_path,
        "json_path": final_json_path,
        "title": highlight.title,
        "score": highlight.score
    }
