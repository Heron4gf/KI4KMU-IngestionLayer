import logging
import uuid
from typing import Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.api_models import IngestionResult, QueryRequest, QueryResponse
from app.services.document_service import process_document
from app.infrastructure.chroma_repository import semantic_search
from app.utils.files import save_upload_to_disk

logger = logging.getLogger(__name__)

v1_router = APIRouter(prefix="/v1")


@v1_router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@v1_router.post(
    "/documents",
    response_model=IngestionResult,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(file: UploadFile = File(...)) -> IngestionResult:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must be a PDF.",
        )

    pdf_path = await save_upload_to_disk(file)
    document_id = str(uuid.uuid4())

    try:
        logger.info(f"[ROUTER] Processing document: {file.filename}")
        num_chunks = await process_document(pdf_path, document_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    finally:
        try:
            pdf_path.unlink()
        except FileNotFoundError:
            pass

    if num_chunks == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No chunks were stored for this document.",
        )

    return IngestionResult(
        document_id=document_id,
        filename=file.filename,
        num_chunks=num_chunks,
    )


@v1_router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
)
async def query_documents(body: QueryRequest) -> QueryResponse:
    query = body.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty.",
        )

    results = semantic_search(query, body.top_k)

    return QueryResponse(query=query, results=results)
