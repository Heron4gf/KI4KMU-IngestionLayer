import asyncio
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    document_id: Optional[str] = None
    num_chunks: Optional[int] = None
    error: Optional[str] = None


_store: dict[str, JobRecord] = {}
_lock = asyncio.Lock()


async def create_job(job_id: str, filename: str) -> JobRecord:
    record = JobRecord(job_id=job_id, status=JobStatus.PENDING, filename=filename)
    async with _lock:
        _store[job_id] = record
    return record


async def update_job(job_id: str, **kwargs) -> None:
    async with _lock:
        record = _store[job_id]
        _store[job_id] = record.model_copy(update=kwargs)


async def get_job(job_id: str) -> Optional[JobRecord]:
    return _store.get(job_id)
