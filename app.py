import logging
import uuid
from typing import Dict

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile, status

from chroma_manager import document_already_ingested, semantic_search
from models import IngestionResult, QueryRequest, QueryResponse
from services import process_document
from utils import file_md5, save_upload_to_disk


logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Ingestion API")

v1_router = APIRouter(prefix="/v1")


@v1_router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@v1_router.post(
    "/documents",
    response_model=IngestionResult,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(file: UploadFile = File(...)) -> IngestionResult:
    """
    Ingest a PDF document into the vector store.
    
    This endpoint handles HTTP request/response only. All business logic
    is delegated to the service layer (services.process_document).
    """
    # Validate file type
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must be a PDF.",
        )

    pdf_path = await save_upload_to_disk(file)
    document_id = str(uuid.uuid4())
    
    try:
        pdf_hash = file_md5(pdf_path)

        # Check for duplicate ingestion
        if document_already_ingested(pdf_hash):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document has already been ingested.",
            )

        # Delegate all business logic to service layer
        logger.info(f"[ROUTER] Processing document: {file.filename}")
        num_chunks = await process_document(pdf_path, document_id, pdf_hash)
        
    finally:
        # Clean up temporary file
        try:
            pdf_path.unlink()
        except FileNotFoundError:
            pass

    # Validate result
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

    return QueryResponse(
        query=query,
        results=results,
    )


app.include_router(v1_router)