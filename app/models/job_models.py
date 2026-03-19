from typing import Optional
from pydantic import BaseModel
from app.infrastructure.job_store import JobStatus


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    document_id: Optional[str] = None
    num_chunks: Optional[int] = None
    error: Optional[str] = None
