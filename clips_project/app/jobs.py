import json
import logging
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from queue import Queue, Empty
from app.config import settings
from app.schemas import JobStatus, JobStage, JobResponse, CreateJobRequest
from app.pipeline.runner import run_pipeline

logger = logging.getLogger(__name__)

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, JobResponse] = {}
        self.work_queue: Queue = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        """Initializes job directory, recovers interrupted jobs, and starts worker loop."""
        settings.ensure_directories()
        self._recover_interrupted_jobs()

        if self.worker_thread is None or not self.worker_thread.is_alive():
            self._stop_event.clear()
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("JobManager worker thread started.")

    def _recover_interrupted_jobs(self):
        """Loads jobs from disk and marks interrupted jobs as failed."""
        for file in settings.jobs_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                job = JobResponse.model_validate(data)
                if job.status in [JobStatus.RUNNING, JobStatus.QUEUED]:
                    job.status = JobStatus.FAILED.value
                    job.stage = JobStage.FAILED.value
                    job.error = "Interrupted by server restart"
                    job.updated_at = datetime.now(timezone.utc).isoformat()
                    self._save_job_to_disk(job)
                self.jobs[job.job_id] = job
            except Exception as e:
                logger.error(f"Error reading job file {file}: {e}")

    def _save_job_to_disk(self, job: JobResponse):
        job_file = settings.jobs_dir / f"{job.job_id}.json"
        with open(job_file, "w", encoding="utf-8") as f:
            json.dump(job.model_dump(), f, indent=2, ensure_ascii=False)

    def create_job(self, req: CreateJobRequest) -> JobResponse:
        job_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        job = JobResponse(
            job_id=job_id,
            kick_url=req.kick_url,
            status=JobStatus.QUEUED.value,
            stage=JobStage.QUEUED.value,
            progress=0,
            clips=[],
            failed_clips=[],
            created_at=now,
            updated_at=now
        )
        with self._lock:
            self.jobs[job_id] = job
            self._save_job_to_disk(job)

        # Enqueue work parameters
        self.work_queue.put((job_id, req))
        logger.info(f"Enqueued job {job_id} for URL {req.kick_url}")
        return job

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        with self._lock:
            if job_id in self.jobs:
                return self.jobs[job_id]

        # Check disk if not in memory
        job_file = settings.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            try:
                with open(job_file, "r", encoding="utf-8") as f:
                    job = JobResponse.model_validate(json.load(f))
                    with self._lock:
                        self.jobs[job_id] = job
                    return job
            except Exception as e:
                logger.error(f"Failed to load job {job_id} from disk: {e}")
        return None

    def list_jobs(self) -> List[JobResponse]:
        with self._lock:
            # Sort newest first
            return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return False

            if job.status in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
                job.status = JobStatus.CANCELLED.value
                job.stage = JobStage.FAILED.value
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_job_to_disk(job)
                logger.info(f"Cancelled job {job_id}")
                return True
            else:
                # Remove finished job record from memory and disk
                self.jobs.pop(job_id, None)
                job_file = settings.jobs_dir / f"{job_id}.json"
                if job_file.exists():
                    job_file.unlink()
                return True

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                job_id, req = self.work_queue.get(timeout=1.0)
            except Empty:
                continue

            with self._lock:
                job = self.jobs.get(job_id)
                if not job or job.status == JobStatus.CANCELLED.value:
                    self.work_queue.task_done()
                    continue
                job.status = JobStatus.RUNNING.value
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_job_to_disk(job)

            def progress_callback(stage: JobStage, pct: int):
                with self._lock:
                    if job_id in self.jobs:
                        j = self.jobs[job_id]
                        j.stage = stage.value
                        j.progress = pct
                        j.updated_at = datetime.now(timezone.utc).isoformat()
                        self._save_job_to_disk(j)

            try:
                result = run_pipeline(
                    kick_url=req.kick_url,
                    max_clips=req.max_clips or settings.MAX_CLIPS,
                    min_score=req.min_score or settings.MIN_SCORE,
                    layout=req.layout or settings.LAYOUT,
                    force=req.force or False,
                    keep_temp=req.keep_temp or False,
                    brief_path=req.brief_path,
                    logo_path=req.logo_path,
                    progress_callback=progress_callback
                )
                with self._lock:
                    job.status = JobStatus.DONE.value
                    job.stage = JobStage.DONE.value
                    job.progress = 100
                    job.clips = result.get("clips", [])
                    job.failed_clips = result.get("failed_clips", [])
                    job.updated_at = datetime.now(timezone.utc).isoformat()
                    self._save_job_to_disk(job)

            except Exception as e:
                logger.error(f"Job {job_id} encountered fatal error: {e}", exc_info=True)
                with self._lock:
                    job.status = JobStatus.FAILED.value
                    job.stage = JobStage.FAILED.value
                    job.error = str(e)
                    job.updated_at = datetime.now(timezone.utc).isoformat()
                    self._save_job_to_disk(job)
            finally:
                self.work_queue.task_done()

job_manager = JobManager()
