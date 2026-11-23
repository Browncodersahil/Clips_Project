import logging
import shutil
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import HealthResponse
from app.jobs import job_manager
from app.api.jobs_routes import router as jobs_router
from app.api.clips_routes import router as clips_router

# Setup file & console logging
settings.ensure_directories()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file, encoding="utf-8")
    ]
)
logger = logging.getLogger("kick_clipper")

def check_ffmpeg() -> bool:
    """Verifies that ffmpeg is available in system PATH."""
    try:
        res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return res.returncode == 0
    except Exception:
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Kick Stream Auto-Clipper FastAPI Service...")
    settings.ensure_directories()

    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        logger.warning("WARNING: ffmpeg not detected on PATH. Video processing will fail unless ffmpeg is installed.")
    else:
        logger.info("FFmpeg detected and operational.")

    if not settings.GROQ_API_KEY:
        logger.warning("WARNING: GROQ_API_KEY is missing. Set it in .env to enable Whisper and LLM highlight features.")
    else:
        logger.info("GROQ_API_KEY detected.")

    # Start job manager worker thread
    job_manager.start()

    yield

    # Shutdown
    logger.info("Shutting down Kick Stream Auto-Clipper service...")
    job_manager._stop_event.set()

app = FastAPI(
    title="Kick Stream Auto-Clipper API",
    description="Automated AI pipeline turning Kick streams into ready-to-upload vertical reels with captions.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(jobs_router)
app.include_router(clips_router)

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check & environment verification"
)
def health_check():
    """
    Returns service health status, FFmpeg availability, and GROQ API key configuration state.
    """
    return HealthResponse(
        status="ok",
        ffmpeg_available=check_ffmpeg(),
        groq_api_key_configured=bool(settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip()),
        version="1.0.0"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
