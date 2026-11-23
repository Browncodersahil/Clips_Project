from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator, AliasChoices

class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    FINDING_HIGHLIGHTS = "finding_highlights"
    CLIPPING = "clipping"
    EDITING = "editing"
    DONE = "done"
    FAILED = "failed"

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CreateJobRequest(BaseModel):
    kick_url: str = Field(..., description="Stream or video URL (YouTube, Kick, Twitch) or local video file path", validation_alias=AliasChoices("kick_url", "url", "stream_url"))
    max_clips: Optional[int] = Field(0, ge=0, description="Max highlights to generate (0 or None = unlimited / maximum clips)")
    min_score: Optional[int] = Field(7, ge=1, le=10, description="Minimum viral rating (1-10)")
    layout: Optional[str] = Field("blur", description="Layout: 'blur' or 'crop'")
    force: Optional[bool] = Field(False, description="Re-run intermediate stages even if cached")
    keep_temp: Optional[bool] = Field(False, description="Do not delete temporary audio chunks")
    brief_path: Optional[str] = Field(None, description="Optional path to custom creator brief .md file")
    logo_path: Optional[str] = Field(None, description="Optional path to custom creator logo image")

    @field_validator("kick_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v_clean = v.strip()
        # Accept YouTube, Kick, Twitch, direct video links or local files
        supported_domains = ["youtube.com", "youtu.be", "kick.com", "twitch.tv"]
        is_supported_domain = any(domain in v_clean.lower() for domain in supported_domains)
        is_local_or_media = (
            v_clean.startswith("http://") or
            v_clean.startswith("https://") or
            v_clean.endswith((".mp4", ".mkv", ".ts", ".mov", ".webm")) or
            v_clean.startswith("test_")
        )
        if is_supported_domain or is_local_or_media:
            return v_clean
        raise ValueError("Invalid URL: Please provide a valid YouTube, Kick, Twitch stream/VOD link or video path.")

class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobResponse(BaseModel):
    job_id: str
    kick_url: str
    status: str
    stage: str
    progress: int = Field(0, ge=0, le=100)
    error: Optional[str] = None
    failed_clips: List[str] = Field(default_factory=list)
    clips: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

# Whisper / Transcription Schemas
class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    probability: Optional[float] = None

class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: List[WordTimestamp] = Field(default_factory=list)

class Transcript(BaseModel):
    video_id: str
    source_url: Optional[str] = ""
    duration: float = 0.0
    segments: List[Segment] = Field(default_factory=list)

# Highlight Schemas
class HighlightItem(BaseModel):
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    score: int = Field(..., ge=1, le=10, description="Score 1-10")
    reason: str = Field(..., description="Why this moment is engaging")
    title: str = Field(..., description="Catchy viral short title")
    description: str = Field(..., description="Viral caption for social platforms")
    hashtags: List[str] = Field(default_factory=list, description="Array of relevant hashtags")

class HighlightsList(BaseModel):
    highlights: List[HighlightItem] = Field(default_factory=list)

# Final Clip Metadata (1:1 with Final_Clip/<name>.json)
class FinalClipMetadata(BaseModel):
    title: str
    description: str
    hashtags: List[str]
    video_file: str
    source_url: str = ""
    source_start: float = 0.0
    source_end: float = 0.0
    score: int = 7
    reason: Optional[str] = ""
    duration: Optional[float] = 0.0
    created_at: Optional[str] = ""

class HealthResponse(BaseModel):
    status: str
    ffmpeg_available: bool
    groq_api_key_configured: bool
    version: str = "1.0.0"
