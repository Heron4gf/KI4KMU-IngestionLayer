import asyncio
import logging
from pathlib import Path

from app.services.unstructured_service import chunk_pdf_with_unstructured
from app.services.image_service import process_images_pipeline
from app.infrastructure.chroma_repository import (
    document_already_ingested,
    store_chunks_in_chroma,
)
from app.utils.files import file_md5

logger = logging.getLogger(__name__)


async def process_document(pdf_path: Path, document_id: str) -> int:
    logger.info("[SERVICE] Starting document processing for: %s", pdf_path.name)

    pdf_hash = file_md5(pdf_path)

    if document_already_ingested(pdf_hash):
        raise ValueError("This document has already been ingested.")

    text_elements, captioned_images = await asyncio.gather(
        chunk_pdf_with_unstructured(pdf_path),
        process_images_pipeline(pdf_path),
    )

    logger.info(
        "[SERVICE] Pipeline complete: %d text chunks, %d captioned images",
        len(text_elements),
        len(captioned_images),
    )

    num_stored = await asyncio.to_thread(
        store_chunks_in_chroma,
        text_elements=text_elements,
        captioned_images=captioned_images,
        document_id=document_id,
        pdf_hash=pdf_hash,
    )

    logger.info("[SERVICE] Stored %d chunks in Chroma", num_stored)

    return num_stored
