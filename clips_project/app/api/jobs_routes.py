from typing import List
from fastapi import APIRouter, HTTPException, status
from app.schemas import CreateJobRequest, CreateJobResponse, JobResponse
from app.jobs import job_manager

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post(
    "",
    response_model=CreateJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a Kick clipping job"
)
def create_job(request: CreateJobRequest):
    """
    Enqueue a background job to download, transcribe, find highlights,
    and generate finished vertical reels into data/Final_Clip/.
    """
    job = job_manager.create_job(request)
    return CreateJobResponse(
        job_id=job.job_id,
        status=job.status,
        message="Job successfully enqueued and will run in the background."
    )

@router.get(
    "",
    response_model=List[JobResponse],
    summary="List all jobs"
)
def list_jobs():
    """Retrieve all submitted jobs, ordered newest first."""
    return job_manager.list_jobs()

@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status and progress"
)
def get_job(job_id: str):
    """
    Check status, active stage, progress (0-100), and final clip list of a job.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )
    return job

@router.delete(
    "/{job_id}",
    summary="Cancel or remove a job"
)
def delete_job(job_id: str):
    """Cancel a queued/running job or remove a finished job entry."""
    success = job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )
    return {"message": f"Job '{job_id}' successfully cancelled/deleted."}
