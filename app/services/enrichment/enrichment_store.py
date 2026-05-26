import uuid
from collections import deque
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class EnrichmentJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EnrichmentJobRecord(BaseModel):
    job_id: str
    document_id: str
    status: EnrichmentJobStatus
    error: Optional[str] = None


class EnrichmentJobStore:
    """In-memory store for enrichment jobs. Thread-safe via GIL for simple dict/deque ops."""

    def __init__(self) -> None:
        self._records: dict[str, EnrichmentJobRecord] = {}
        self._queue: deque[tuple[str, str]] = deque()  # (document_id, job_id)

    def enqueue(self, document_id: str) -> str:
        job_id = str(uuid.uuid4())
        record = EnrichmentJobRecord(
            job_id=job_id,
            document_id=document_id,
            status=EnrichmentJobStatus.PENDING,
        )
        self._records[job_id] = record
        self._queue.append((document_id, job_id))
        return job_id

    def pop_pending(self) -> Optional[tuple[str, str]]:
        """Return (document_id, job_id) of the next pending job, or None."""
        if self._queue:
            return self._queue.popleft()
        return None

    def set_status(self, job_id: str, status: EnrichmentJobStatus, error: Optional[str] = None) -> None:
        if job_id in self._records:
            self._records[job_id] = self._records[job_id].model_copy(
                update={"status": status, "error": error}
            )

    def get(self, job_id: str) -> Optional[EnrichmentJobRecord]:
        return self._records.get(job_id)
