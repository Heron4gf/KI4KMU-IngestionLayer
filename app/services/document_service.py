import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx
from langfuse import observe

from app.services.unstructured_service import chunk_pdf_with_unstructured
from app.services.image_service import process_images_pipeline
from app.infrastructure.chroma_repository import document_already_ingested, store_chunks_in_chroma, delete_document_chunks
from app.infrastructure.graphdb_writer import insert_document, insert_chunk, insert_image, insert_or_merge_section
from app.infrastructure.job_store import JobStage, update_job
from app.core.config import SECTION_EXTRACTOR_URL
from app.utils.files import file_md5

logger = logging.getLogger(__name__)


async def _extract_sections(client: httpx.AsyncClient, chunk_id: str, text: str) -> list[dict]:
    """Call the section extractor service. Returns [] on failure — chunk ingestion must never fail."""
    try:
        r = await client.post(f"{SECTION_EXTRACTOR_URL}/extract-sections", json={"text": text})
        r.raise_for_status()
        return r.json().get("sections", [])
    except httpx.HTTPError as e:
        logger.warning("[SERVICE] Section extractor call failed for chunk %s: %s", chunk_id, e)
        return []


async def _process_single_chunk(client: httpx.AsyncClient, i: int, element: dict, document_id: str):
    chunk_id = f"{document_id}_chunk_{i}"
    text = element.get("text", "")
    page_number = element.get("metadata", {}).get("page_number")

    await asyncio.to_thread(insert_chunk, chunk_id, document_id, text, i, page_number)

    sections = await _extract_sections(client, chunk_id, text)
    for section in sections:
        await asyncio.to_thread(insert_or_merge_section, section, chunk_id)


@observe(name="document_processing", as_type="chain", capture_input=True, capture_output=True)
async def process_document(pdf_path: Path, document_id: str, job_id: Optional[str] = None) -> int:
    logger.info("[SERVICE] Starting document processing for: %s", pdf_path.name)

    pdf_hash = file_md5(pdf_path)
    if document_already_ingested(pdf_hash):
        raise ValueError("This document has already been ingested.")

    async def _stage(stage: JobStage):
        if job_id:
            await update_job(job_id, stage=stage)

    # Ensure the Document root node exists before any belongsTo edges are written
    await asyncio.to_thread(insert_document, document_id, pdf_hash)

    await _stage(JobStage.CHUNKING_TEXT)
    text_elements = await chunk_pdf_with_unstructured(pdf_path)
    logger.info("[SERVICE] Extracted %d text chunks", len(text_elements))

    await _stage(JobStage.EXTRACTING_IMAGES)
    captioned_images = await process_images_pipeline(pdf_path)
    logger.info("[SERVICE] Extracted %d captioned images", len(captioned_images))

    await _stage(JobStage.STORING_CHUNKS)
    num_stored = await asyncio.to_thread(
        store_chunks_in_chroma,
        text_elements=text_elements,
        captioned_images=captioned_images,
        document_id=document_id,
        pdf_hash=pdf_hash,
    )
    logger.info("[SERVICE] Stored %d chunks in Chroma", num_stored)

    # Write image nodes to GraphDB
    for idx, image_element in enumerate(captioned_images):
        raw_metadata = image_element.get("metadata") or {}
        image_b64 = raw_metadata.get("image_base64")
        page_number = raw_metadata.get("page_number")
        if image_b64:
            image_id = f"{document_id}_image_{idx}"
            await asyncio.to_thread(insert_image, image_id, document_id, image_b64, page_number)

    await _stage(JobStage.EXTRACTING_SECTIONS)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            tasks = [_process_single_chunk(client, i, element, document_id) for i, element in enumerate(text_elements)]
            if tasks:
                await asyncio.gather(*tasks)
        await _stage(JobStage.WRITING_GRAPHDB)
        logger.info("[SERVICE] GraphDB write complete for document %s", document_id)
    except Exception as e:
        logger.error("[SERVICE] GraphDB write failed, rolling back Chroma for document %s: %s", document_id, e)
        await asyncio.to_thread(delete_document_chunks, document_id)
        raise

    return num_stored