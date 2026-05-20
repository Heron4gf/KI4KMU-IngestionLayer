import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Dict

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from langfuse import observe

from app.models.api_models import QueryRequest, QueryResponse
from app.models.job_models import JobAccepted, JobStatusResponse
from app.services.document_service import process_document
from app.services.query_service import (
    hybrid_search,
    _vector_search_sections,
    _graph_keyword_search_chunks,
    _resolve_vector_sections_to_chunks,
    _graph_traversal_expand_chunks,
    _rerank_chunks,
    _merge_chunks,
)
from app.infrastructure.job_store import JobStatus, JobStage, create_job, get_job, update_job

logger = logging.getLogger(__name__)
v1_router = APIRouter(prefix="/v1")


@observe(name="run_ingestion", as_type="chain", capture_input=True, capture_output=True)
async def _run_ingestion(job_id: str, file_bytes: bytes, filename: str) -> None:
    import tempfile
    import pathlib

    tmp = pathlib.Path(tempfile.mktemp(suffix=".pdf"))
    try:
        await update_job(job_id, status=JobStatus.PROCESSING)
        tmp.write_bytes(file_bytes)
        document_id = str(uuid.uuid4())
        num_chunks = await process_document(tmp, document_id, job_id=job_id)
        if num_chunks == 0:
            await update_job(job_id, status=JobStatus.FAILED, stage=JobStage.FAILED, error="No chunks were stored for this document.")
        else:
            await update_job(job_id, status=JobStatus.COMPLETED, stage=JobStage.COMPLETED, document_id=document_id, num_chunks=num_chunks)
    except Exception as e:
        logger.exception(f"[INGESTION] Job {job_id} failed: {e}")
        await update_job(job_id, status=JobStatus.FAILED, error=str(e))
    finally:
        tmp.unlink(missing_ok=True)


async def _stream_retrieval(query: str, top_k: int) -> AsyncGenerator[str, None]:
    """Yield SSE events, one per retrieval stage."""

    def sse(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n"

    # Stage 1 — vector search + graph keyword in parallel
    vector_results, graph_chunks = await asyncio.gather(
        _vector_search_sections(query),
        _graph_keyword_search_chunks(query),
    )

    yield sse("vector_results", {
        "nodes": [
            {"id": r.id, "label": r.id[:12], "type": "section", "score": round(r.score, 4)}
            for r in vector_results
        ]
    })
    yield sse("graph_keyword", {
        "nodes": [{"id": c["chunk_id"], "label": c["chunk_id"][:12], "type": "kw_chunk"} for c in graph_chunks],
        "edges": [
            {"id": f"kw_{c['chunk_id']}", "source": c.get("section_id", "graph"), "target": c["chunk_id"], "via": "keyword"}
            for c in graph_chunks if c.get("section_id")
        ],
    })

    # Stage 2 — resolve vector sections to their chunks
    vector_chunks = await _resolve_vector_sections_to_chunks(vector_results)
    yield sse("vector_chunks", {
        "nodes": [{"id": c["chunk_id"], "label": c["chunk_id"][:12], "type": "v_chunk"} for c in vector_chunks],
        "edges": [
            {"id": f"vc_{c['chunk_id']}", "source": c["section_id"], "target": c["chunk_id"], "via": "contains"}
            for c in vector_chunks
        ],
    })

    # Stage 3 — graph traversal expansion
    traversal_chunks = await _graph_traversal_expand_chunks(vector_results)
    yield sse("traversal", {
        "nodes": [{"id": c["chunk_id"], "label": c["chunk_id"][:12], "type": "t_chunk"} for c in traversal_chunks],
        "edges": [
            {"id": f"tr_{c['chunk_id']}", "source": c["seed_section_id"], "target": c["chunk_id"], "via": "traversal"}
            for c in traversal_chunks if c.get("seed_section_id")
        ],
    })

    # Stage 4 — rerank and emit final top-k
    all_chunks = _merge_chunks(vector_chunks, graph_chunks, traversal_chunks)
    final_results = await _rerank_chunks(query, all_chunks, top_k)
    top_ids = {r.id for r in final_results}

    yield sse("rerank_done", {
        "top_k": [
            {"id": r.id, "score": round(r.score, 4), "text_preview": r.text[:120]}
            for r in final_results
        ],
        "all_ids": [c["chunk_id"] for c in all_chunks],
        "top_ids": list(top_ids),
    })


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
@observe(name="query_documents", as_type="span", capture_input=True, capture_output=True)
async def query_documents(body: QueryRequest) -> QueryResponse:
    query = body.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty.",
        )
    results = await hybrid_search(
        query,
        body.max_vector_results,
        body.max_graph_results,
        body.max_results_total,
    )
    return QueryResponse(query=query, results=results)


@v1_router.get("/query/stream")
async def stream_query(query: str, top_k: int = 5) -> StreamingResponse:
    if not query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query must not be empty.")
    return StreamingResponse(
        _stream_retrieval(query.strip(), top_k),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
