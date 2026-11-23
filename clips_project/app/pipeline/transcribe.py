import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from groq import Groq
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from app.config import settings
from app.schemas import Transcript, Segment, WordTimestamp

logger = logging.getLogger(__name__)

def get_groq_client() -> Groq:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured in .env or environment")
    return Groq(api_key=settings.GROQ_API_KEY)

@retry(
    wait=wait_exponential(multiplier=1.5, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True
)
def transcribe_chunk(client: Groq, chunk_info: Dict[str, Any]) -> Dict[str, Any]:
    """Transcribes a single audio chunk via Groq Whisper API with timestamps."""
    chunk_path: Path = chunk_info["chunk_path"]
    offset = float(chunk_info["offset_seconds"])
    idx = chunk_info["index"]

    logger.info(f"Transcribing chunk {idx} ({chunk_path.name}) at offset {offset:.1f}s...")
    with open(chunk_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            file=audio_file,
            model=settings.WHISPER_MODEL,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
            temperature=0.0
        )

    # Groq returns a Transcription or dict-like object
    data = response.to_dict() if hasattr(response, "to_dict") else dict(response)
    data["_chunk_offset"] = offset
    data["_chunk_index"] = idx
    return data

def transcribe_chunks_and_merge(
    chunks: List[Dict[str, Any]],
    video_id: str,
    source_url: str = "",
    force: bool = False
) -> Transcript:
    """
    Transcribes audio chunks in parallel, converts timestamps to global video time,
    deduplicates overlap regions, and caches the transcript JSON in data/transcripts/<video_id>.json.
    """
    settings.ensure_directories()
    transcript_file = settings.transcripts_dir / f"{video_id}.json"

    # Check cache
    if transcript_file.exists() and not force:
        logger.info(f"Loading cached transcript: {transcript_file}")
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Transcript.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed loading cached transcript, re-transcribing: {e}")

    client = get_groq_client()
    raw_results: List[Dict[str, Any]] = []

    # Parallel transcription with worker limit
    max_workers = max(1, min(settings.TRANSCRIBE_WORKERS, len(chunks)))
    logger.info(f"Dispatching transcription with {max_workers} worker threads...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(transcribe_chunk, client, chunk): chunk
            for chunk in chunks
        }
        for future in as_completed(future_map):
            try:
                res = future.result()
                raw_results.append(res)
            except Exception as e:
                chunk = future_map[future]
                logger.error(f"Failed transcribing chunk {chunk['index']}: {e}")
                raise RuntimeError(f"Transcription failed on chunk {chunk['index']}: {e}")

    # Sort results by chunk index
    raw_results.sort(key=lambda x: x.get("_chunk_index", 0))

    # Merge segments and words into global timestamps with overlap deduplication
    all_segments: List[Segment] = []
    seg_id_counter = 0
    last_accepted_end = 0.0

    for chunk_res in raw_results:
        offset = float(chunk_res.get("_chunk_offset", 0.0))
        chunk_segments = chunk_res.get("segments") or []
        chunk_words = chunk_res.get("words") or []

        # Map words by timestamp or approximate if returned at chunk level
        global_words: List[WordTimestamp] = []
        for w in chunk_words:
            w_start = round(float(w.get("start", 0.0)) + offset, 3)
            w_end = round(float(w.get("end", 0.0)) + offset, 3)
            global_words.append(WordTimestamp(
                word=w.get("word", ""),
                start=w_start,
                end=w_end,
                probability=w.get("probability")
            ))

        for seg in chunk_segments:
            seg_start = round(float(seg.get("start", 0.0)) + offset, 3)
            seg_end = round(float(seg.get("end", 0.0)) + offset, 3)
            text = seg.get("text", "").strip()

            # Overlap deduplication: skip segments that start before previous chunk end
            if seg_start < (last_accepted_end - 0.5):
                continue

            # Associate words inside this segment time window
            seg_words = [
                w for w in global_words
                if (w.start >= seg_start - 0.1 and w.end <= seg_end + 0.1)
            ]

            all_segments.append(Segment(
                id=seg_id_counter,
                start=seg_start,
                end=seg_end,
                text=text,
                words=seg_words
            ))
            seg_id_counter += 1
            last_accepted_end = max(last_accepted_end, seg_end)

    total_duration = last_accepted_end if all_segments else 0.0
    transcript = Transcript(
        video_id=video_id,
        source_url=source_url,
        duration=total_duration,
        segments=all_segments
    )

    # Save to data/transcripts/<video_id>.json
    with open(transcript_file, "w", encoding="utf-8") as f:
        json.dump(transcript.model_dump(), f, indent=2, ensure_ascii=False)

    logger.info(f"Transcript successfully merged and saved to {transcript_file}")
    return transcript
