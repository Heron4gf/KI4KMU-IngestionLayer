import logging
import uuid
from typing import Dict

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile, status

from chroma_manager import (
    document_already_ingested,
    semantic_search,
    store_chunks_in_chroma,
)
from models import IngestionResult, QueryRequest, QueryResponse
from unstructured_manager import (
    chunk_pdf_with_unstructured,
    extract_images_with_unstructured,
)
from utils import file_md5, save_upload_to_disk


logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Ingestion API")

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
    """
    Ingest a PDF document into the vector store.
    
    Pipeline:
    1. Extract text chunks (chunking_strategy=by_title)
    2. Extract raw images with base64 payload
    3. Generate captions for images using VLM
    4. Store everything in a single Chroma collection
    """
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must be a PDF.",
        )

    pdf_path = await save_upload_to_disk(file)
    document_id = str(uuid.uuid4())
    
    try:
        pdf_hash = file_md5(pdf_path)

        if document_already_ingested(pdf_hash):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document has already been ingested.",
            )

        # Step 1: Extract text chunks only (no image extraction)
        logger.info(f"[INGEST] Step 1: Extracting text chunks from {file.filename}")
        text_elements = await chunk_pdf_with_unstructured(pdf_path)
        logger.info(f"[INGEST] Extracted {len(text_elements)} text chunks")

        # Step 2: Extract raw images with base64 payload (no chunking)
        logger.info(f"[INGEST] Step 2: Extracting raw images from {file.filename}")
        image_elements = await extract_images_with_unstructured(pdf_path)
        logger.info(f"[INGEST] Extracted {len(image_elements)} raw images")

        # Step 3: Store both text chunks and images in Chroma
        # Images are embedded via their captions, base64 stored in metadata
        logger.info(f"[INGEST] Step 3: Storing in Chroma")
        num_chunks = store_chunks_in_chroma(
            text_elements, image_elements, document_id, pdf_hash
        )
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

    return QueryResponse(
        query=query,
        results=results,
    )


app.include_router(v1_router)