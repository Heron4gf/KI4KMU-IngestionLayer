import logging
import uuid
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.models.api_models import QueryRequest, QueryResponse
from app.models.job_models import JobAccepted, JobStatusResponse
from app.services.document_service import process_document
from app.services.query_service import hybrid_search
from app.infrastructure.job_store import JobStatus, create_job, get_job, update_job

logger = logging.getLogger(__name__)
v1_router = APIRouter(prefix="/v1")


async def _run_ingestion(job_id: str, file_bytes: bytes, filename: str) -> None:
    import tempfile
    import pathlib

    tmp = pathlib.Path(tempfile.mktemp(suffix=".pdf"))
    try:
        await update_job(job_id, status=JobStatus.PROCESSING)
        tmp.write_bytes(file_bytes)
        document_id = str(uuid.uuid4())
        num_chunks = await process_document(tmp, document_id)
        if num_chunks == 0:
            await update_job(job_id, status=JobStatus.FAILED, error="No chunks were stored for this document.")
        else:
            await update_job(job_id, status=JobStatus.COMPLETED, document_id=document_id, num_chunks=num_chunks)
    except Exception as e:
        logger.exception(f"[INGESTION] Job {job_id} failed: {e}")
        await update_job(job_id, status=JobStatus.FAILED, error=str(e))
    finally:
        tmp.unlink(missing_ok=True)


@v1_router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@v1_router.post("/documents", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> JSONResponse:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must be a PDF.",
        )
    job_id = str(uuid.uuid4())
    file_bytes = await file.read()
    await create_job(job_id, file.filename)
    background_tasks.add_task(_run_ingestion, job_id, file_bytes, file.filename)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=JobAccepted(
            job_id=job_id,
            status=JobStatus.PENDING,
            status_url=f"/v1/jobs/{job_id}",
        ).model_dump(),
        headers={"Location": f"/v1/jobs/{job_id}"},
    )


@v1_router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@v1_router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query_documents(body: QueryRequest) -> QueryResponse:
    query = body.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty.",
        )
    results = hybrid_search(
        query,
        body.max_vector_results,
        body.max_graph_results,
        body.max_results_total,
    )
    return QueryResponse(query=query, results=results)
