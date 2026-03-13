import asyncio
import logging
from pathlib import Path

import httpx

from app.services.unstructured_service import chunk_pdf_with_unstructured
from app.services.image_service import process_images_pipeline
from app.infrastructure.chroma_repository import (
    document_already_ingested,
    store_chunks_in_chroma,
)
from app.infrastructure.graphdb_writer import insert_chunk, insert_entity
from app.core.config import LANGEXTRACT_URL
from app.utils.files import file_md5

logger = logging.getLogger(__name__)


async def _extract_entities(client: httpx.AsyncClient, text: str) -> list[dict]:
    try:
        r = await client.post(
            f"{LANGEXTRACT_URL}/extract",
            json={"text": text},
        )
        r.raise_for_status()
        return r.json().get("extractions", [])
    except httpx.HTTPError as e:
        logger.warning("[SERVICE] Langextract call failed: %s", e)
        return []


async def _process_single_chunk(client: httpx.AsyncClient, i: int, element: dict, document_id: str):
    chunk_id = f"{document_id}_chunk_{i}"
    text = element.get("text", "")
    metadata = {
        **element.get("metadata", {}),
        "document_id": document_id,
        "chunk_index": i,
        "text": text,
    }

    await asyncio.to_thread(insert_chunk, chunk_id, metadata)
    
    extractions = await _extract_entities(client, text)

    for extraction in extractions:
        entity_label = extraction.get("extraction_text", "").strip()
        if entity_label:
            await asyncio.to_thread(insert_entity, entity_label, chunk_id)


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

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [
            _process_single_chunk(client, i, element, document_id)
            for i, element in enumerate(text_elements)
        ]
        if tasks:
            await asyncio.gather(*tasks)

    logger.info("[SERVICE] GraphDB write complete for document %s", document_id)

    return num_stored