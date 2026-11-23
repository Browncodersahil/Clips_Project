from pathlib import Path
from typing import Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API & Keys
    GROQ_API_KEY: str = ""

    # Pipeline audio & transcription settings
    CHUNK_SECONDS: int = 300
    CHUNK_OVERLAP_SECONDS: int = 10
    WHISPER_MODEL: str = "whisper-large-v3-turbo"
    TRANSCRIBE_WORKERS: int = 2

    # Highlight picking settings
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    MIN_SCORE: int = 7
    MAX_CLIPS: int = 0  # 0 = unlimited / maximum clips from entire stream
    MIN_CLIP_SECONDS: int = 15
    MAX_CLIP_SECONDS: int = 60
    CLIP_PADDING_SECONDS: float = 1.0

    # Output video formatting
    OUTPUT_WIDTH: int = 1080
    OUTPUT_HEIGHT: int = 1920
    OUTPUT_FPS: int = 30
    LAYOUT: str = "blur"  # "blur" or "crop"
    TARGET_LUFS: float = -14.0
    CAPTIONS_FONT_SIZE: int = 42
    LOGO_MAX_WIDTH: int = 180
    LOGO_MAX_HEIGHT: int = 80
    LOGO_BOTTOM_MARGIN: int = 100

    # System & Service
    MAX_CONCURRENT_JOBS: int = 1
    DATA_DIR: str = "data"
    BRIEFS_DIR: str = "briefs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def base_data_dir(self) -> Path:
        path = self.project_root / self.DATA_DIR
        return path

    @property
    def downloads_dir(self) -> Path:
        return self.base_data_dir / "downloads"

    @property
    def audio_dir(self) -> Path:
        return self.base_data_dir / "audio"

    @property
    def chunks_dir(self) -> Path:
        return self.base_data_dir / "chunks"

    @property
    def transcripts_dir(self) -> Path:
        return self.base_data_dir / "transcripts"

    @property
    def highlights_dir(self) -> Path:
        return self.base_data_dir / "highlights"

    @property
    def clips_dir(self) -> Path:
        return self.base_data_dir / "clips"

    @property
    def jobs_dir(self) -> Path:
        return self.base_data_dir / "jobs"

    @property
    def final_clip_dir(self) -> Path:
        return self.base_data_dir / "Final_Clip"

    @property
    def briefs_dir(self) -> Path:
        return self.project_root / self.BRIEFS_DIR

    @property
    def log_file(self) -> Path:
        return self.base_data_dir / "run.log"

    def get_creator_brief(self, custom_path: Path | str | None = None) -> str | None:
        """Reads brief.md from briefs/ or custom path if it exists and has content."""
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                txt = p.read_text(encoding="utf-8").strip()
                return txt if txt else None
            return None

        brief_file = self.briefs_dir / "brief.md"
        if brief_file.is_file():
            txt = brief_file.read_text(encoding="utf-8").strip()
            if txt:
                return txt

        # Check if any .md file exists in briefs_dir
        if self.briefs_dir.exists():
            for md_file in self.briefs_dir.glob("*.md"):
                txt = md_file.read_text(encoding="utf-8").strip()
                if txt:
                    return txt
        return None

    def get_creator_logo_path(self, custom_path: Path | str | None = None) -> Path | None:
        """Finds creator logo image (png/jpg/jpeg/webp) in briefs/ or custom path."""
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return p
            return None

        if not self.briefs_dir.exists():
            return None

        # Prioritize logo.png, logo.jpg, etc.
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            cand = self.briefs_dir / f"logo{ext}"
            if cand.is_file():
                return cand

        # Otherwise find any image file in briefs/
        for cand in self.briefs_dir.iterdir():
            if cand.is_file() and cand.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                return cand
        return None

    def ensure_directories(self) -> None:
        """Create all required data and briefs folders if they do not exist."""
        folders = [
            self.base_data_dir,
            self.downloads_dir,
            self.audio_dir,
            self.chunks_dir,
            self.transcripts_dir,
            self.highlights_dir,
            self.clips_dir,
            self.jobs_dir,
            self.final_clip_dir,
            self.briefs_dir,
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)

settings = Settings()
