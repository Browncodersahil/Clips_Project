import json
import time
import logging
from typing import List, Dict, Any, Optional
from groq import Groq
from tenacity import retry, wait_exponential, stop_after_attempt
from app.config import settings
from app.schemas import Transcript, HighlightItem, HighlightsList
from app.pipeline.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

def get_groq_client() -> Groq:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured in .env or environment")
    return Groq(api_key=settings.GROQ_API_KEY)

def format_transcript_window(segments: List[Any]) -> str:
    """
    Formats segments into clean timestamped blocks to minimize token overhead.
    Groups tiny consecutive segments into natural 15-20s blocks.
    """
    lines = []
    current_text = []
    block_start = None
    block_end = None

    for s in segments:
        text = s.text.strip()
        if not text:
            continue
        if block_start is None:
            block_start = s.start
            block_end = s.end
            current_text = [text]
        elif (s.end - block_start) < 18.0 and len(" ".join(current_text)) < 220:
            current_text.append(text)
            block_end = s.end
        else:
            lines.append(f"[{block_start:.1f}s - {block_end:.1f}s] {' '.join(current_text)}")
            block_start = s.start
            block_end = s.end
            current_text = [text]

    if current_text and block_start is not None:
        lines.append(f"[{block_start:.1f}s - {block_end:.1f}s] {' '.join(current_text)}")

    return "\n".join(lines)

ROTATING_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b"
]

@retry(
    wait=wait_exponential(multiplier=2.0, min=3, max=30),
    stop=stop_after_attempt(4),
    reraise=True
)
def call_llm_for_highlights(
    client: Groq,
    formatted_text: str,
    min_score: int,
    min_sec: int,
    max_sec: int,
    creator_brief: Optional[str] = None,
    preferred_model: Optional[str] = None
) -> List[HighlightItem]:
    user_prompt = build_user_prompt(
        transcript_text=formatted_text,
        min_seconds=min_sec,
        max_seconds=max_sec,
        min_score=min_score,
        creator_brief=creator_brief
    )

    models_order = [preferred_model] if preferred_model else []
    for m in ROTATING_MODELS:
        if m not in models_order:
            models_order.append(m)

    content = None
    last_err = None
    for model_name in models_order:
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "rate_limit" in err_str or "429" in err_str:
                    logger.warning(f"Rate limit on {model_name}. Trying alternate model in pool: {e}")
                    break
                else:
                    logger.warning(f"Model {model_name} failed: {e}. Trying next option...")
                    break
        if content:
            break

    if not content:
        raise RuntimeError(f"All Groq LLM models failed to generate highlights: {last_err}")
    try:
        data = json.loads(content)
        # Ensure 'highlights' key exists or find list in dict
        if "highlights" in data and isinstance(data["highlights"], list):
            items_raw = data["highlights"]
        elif isinstance(data, list):
            items_raw = data
        else:
            # Look for any list in the values
            items_raw = next((v for v in data.values() if isinstance(v, list)), [])

        parsed = HighlightsList.model_validate({"highlights": items_raw})
        return parsed.highlights
    except Exception as e:
        logger.warning(f"Error parsing LLM highlights response: {e}. Raw content: {content[:200]}")
        raise

def deduplicate_highlights(highlights: List[HighlightItem], max_clips: Optional[int], min_score: int) -> List[HighlightItem]:
    """
    Filters by min_score, deduplicates overlapping intervals, and sorts by score.
    If max_clips <= 0 or None, returns all qualifying non-overlapping highlights (maximum clips mode).
    """
    # Filter by min_score
    valid = [h for h in highlights if h.score >= min_score and (h.end - h.start) >= 10.0]
    # Sort primarily by score descending, secondarily by duration
    valid.sort(key=lambda h: (h.score, h.end - h.start), reverse=True)

    accepted: List[HighlightItem] = []
    for candidate in valid:
        c_start = candidate.start
        c_end = candidate.end

        # Check overlap with already accepted items
        overlap = False
        for acc in accepted:
            # Overlap interval
            inter_start = max(c_start, acc.start)
            inter_end = min(c_end, acc.end)
            if inter_end > inter_start:
                inter_len = inter_end - inter_start
                # If overlap exceeds 50% of candidate or 10 seconds, skip
                if inter_len >= 10.0 or (inter_len / (c_end - c_start)) > 0.4:
                    overlap = True
                    break

        if not overlap:
            accepted.append(candidate)
            # If max_clips is set and > 0, stop when limit is reached; otherwise collect all clips
            if max_clips and max_clips > 0 and len(accepted) >= max_clips:
                break

    # Sort accepted chronologically for orderly processing
    accepted.sort(key=lambda h: h.start)
    return accepted

def find_highlights(
    transcript: Transcript,
    video_id: str,
    max_clips: Optional[int] = None,
    min_score: Optional[int] = None,
    force: bool = False,
    creator_brief: Optional[str] = None
) -> List[HighlightItem]:
    """
    Scans the transcript using windowed LLM prompts to identify viral highlight segments.
    Applies creator brief rules when provided or present in briefs/brief.md.
    Saves and caches results in data/highlights/<video_id>.json.
    """
    settings.ensure_directories()
    highlights_file = settings.highlights_dir / f"{video_id}.json"

    limit_clips = max_clips if max_clips is not None else settings.MAX_CLIPS
    score_threshold = min_score if min_score is not None else settings.MIN_SCORE

    active_brief = creator_brief if creator_brief is not None else settings.get_creator_brief()
    if active_brief:
        logger.info(f"Applying creator brief rules to highlight detection ({len(active_brief)} chars).")
    else:
        logger.info("No creator brief detected. Running standard highlight detection.")

    if highlights_file.exists() and not force:
        logger.info(f"Loading cached highlights from {highlights_file}")
        try:
            with open(highlights_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_list = [HighlightItem.model_validate(h) for h in data]
            return deduplicate_highlights(cached_list, limit_clips, score_threshold)
        except Exception as e:
            logger.warning(f"Failed loading cached highlights: {e}")

    if not transcript.segments:
        logger.warning(f"No segments found in transcript for video {video_id}")
        return []

    client = get_groq_client()
    all_raw_highlights: List[HighlightItem] = []

    # Window transcript into 5-minute windows (stay well within Groq 7,000 ITPM limits)
    window_duration = 300.0  # 5 minutes
    window_step = 240.0      # 4 minutes step (1 min overlap)

    start_sec = 0.0
    total_duration = transcript.duration or transcript.segments[-1].end
    window_idx = 0

    while start_sec < total_duration:
        end_sec = start_sec + window_duration
        window_segs = [s for s in transcript.segments if s.start >= start_sec and s.start < end_sec]

        if window_segs:
            target_model = ROTATING_MODELS[window_idx % len(ROTATING_MODELS)]
            window_idx += 1
            logger.info(f"Analyzing window [{start_sec/60:.1f}m - {end_sec/60:.1f}m] using {target_model} ({len(window_segs)} segments)...")
            formatted = format_transcript_window(window_segs)
            try:
                found = call_llm_for_highlights(
                    client=client,
                    formatted_text=formatted,
                    min_score=score_threshold,
                    min_sec=settings.MIN_CLIP_SECONDS,
                    max_sec=settings.MAX_CLIP_SECONDS,
                    creator_brief=active_brief,
                    preferred_model=target_model
                )
                logger.info(f"Found {len(found)} candidate moments in window [{start_sec/60:.1f}m - {end_sec/60:.1f}m].")
                all_raw_highlights.extend(found)
            except Exception as e:
                logger.error(f"Error querying LLM for highlights: {e}")

            # Brief pacing pause
            time.sleep(1.0)

        start_sec += window_step

    # Deduplicate & filter
    final_highlights = deduplicate_highlights(all_raw_highlights, limit_clips, score_threshold)

    # Save to data/highlights/<video_id>.json
    with open(highlights_file, "w", encoding="utf-8") as f:
        json.dump([h.model_dump() for h in final_highlights], f, indent=2, ensure_ascii=False)

    logger.info(f"Selected {len(final_highlights)} viral highlights for clipping.")
    return final_highlights
