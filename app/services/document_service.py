import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.services.unstructured_service import chunk_pdf_with_unstructured
from app.services.image_service import process_images_pipeline
from app.infrastructure.chroma_repository import document_already_ingested, store_chunks_in_chroma
from app.infrastructure.graphdb_writer import insert_chunk, insert_typed_entity, insert_relationship
from app.infrastructure.job_store import JobStage, update_job
from app.core.config import LANGEXTRACT_URL
from app.utils.files import file_md5

logger = logging.getLogger(__name__)

_GRAPHDB_METADATA_BLOCKLIST = {"orig_elements", "languages", "filetype"}


async def _extract_entities(client: httpx.AsyncClient, text: str) -> list[dict]:
    try:
        r = await client.post(f"{LANGEXTRACT_URL}/extract", json={"text": text})
        r.raise_for_status()
        return r.json().get("extractions", [])
    except httpx.HTTPError as e:
        logger.warning("[SERVICE] Langextract call failed: %s", e)
        return []


async def _process_single_chunk(client: httpx.AsyncClient, i: int, element: dict, document_id: str):
    chunk_id = f"{document_id}_chunk_{i}"
    text = element.get("text", "")
    raw_metadata = {**element.get("metadata", {}), "document_id": document_id, "chunk_index": i, "text": text}
    metadata = {k: v for k, v in raw_metadata.items() if k not in _GRAPHDB_METADATA_BLOCKLIST}

    await asyncio.to_thread(insert_chunk, chunk_id, metadata)

    extractions = await _extract_entities(client, text)
    for extraction in extractions:
        cls = extraction.get("extraction_class", "").strip().lower()
        if cls == "beziehung":
            await asyncio.to_thread(insert_relationship, extraction, chunk_id)
        else:
            await asyncio.to_thread(insert_typed_entity, extraction, chunk_id)


async def process_document(pdf_path: Path, document_id: str, job_id: Optional[str] = None) -> int:
    logger.info("[SERVICE] Starting document processing for: %s", pdf_path.name)

    pdf_hash = file_md5(pdf_path)
    if document_already_ingested(pdf_hash):
        raise ValueError("This document has already been ingested.")

    async def _stage(stage: JobStage):
        if job_id:
            await update_job(job_id, stage=stage)

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

    await _stage(JobStage.EXTRACTING_ENTITIES)
    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [_process_single_chunk(client, i, element, document_id) for i, element in enumerate(text_elements)]
        if tasks:
            await asyncio.gather(*tasks)

    await _stage(JobStage.WRITING_GRAPHDB)
    logger.info("[SERVICE] GraphDB write complete for document %s", document_id)

    return num_stored
