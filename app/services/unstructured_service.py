import logging
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import (
    UNSTRUCTURED_CHUNKING_STRATEGY,
    UNSTRUCTURED_MAX_CHARACTERS,
    UNSTRUCTURED_OVERLAP,
)
from app.infrastructure.unstructured_client import _call_unstructured

logger = logging.getLogger(__name__)


async def chunk_pdf_with_unstructured(pdf_path: Path) -> List[Dict[str, Any]]:
    logger.info(f"[UNSTRUCTURED] Extracting text chunks from: {pdf_path.name}")

    elements = await _call_unstructured(
        pdf_path,
        chunking_strategy=UNSTRUCTURED_CHUNKING_STRATEGY,
        max_characters=UNSTRUCTURED_MAX_CHARACTERS,
        overlap=UNSTRUCTURED_OVERLAP,
    )

    text_elements = [e for e in elements if e.get("type") != "Image"]
    logger.info(f"[UNSTRUCTURED] Extracted {len(text_elements)} text chunks")

    return text_elements


async def extract_images_with_unstructured(pdf_path: Path) -> List[Dict[str, Any]]:
    logger.info(f"[UNSTRUCTURED] Extracting raw images from: {pdf_path.name}")

    elements = await _call_unstructured(
        pdf_path,
        extract_image_block_types=["Image"],
        extract_image_block_to_payload=True,
    )

    image_elements: List[Dict[str, Any]] = []
    for element in elements:
        element_type = element.get("type", "")
        raw_metadata = element.get("metadata") or {}
        image_base64 = raw_metadata.get("image_base64")

        if element_type == "Image":
            if image_base64:
                image_elements.append(element)
                logger.debug(
                    "[UNSTRUCTURED] Found Image with base64: %s chars",
                    len(image_base64),
                )
            else:
                logger.warning(
                    "[UNSTRUCTURED] Image element missing image_base64, skipping"
                )
        else:
            logger.debug("[UNSTRUCTURED] Skipping non-Image element: %s", element_type)

    logger.info(
        "[UNSTRUCTURED] Extracted %d raw images with base64",
        len(image_elements),
    )

    return image_elements
