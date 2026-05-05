import logging
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import PREPROCESSING_MAX_CHARACTERS
from app.infrastructure.pdf_extractor import extract_text_chunks, extract_images

logger = logging.getLogger(__name__)


async def chunk_pdf_with_preprocessing(pdf_path: Path) -> List[Dict[str, Any]]:
    logger.info(f"[EXTRACTOR] Extracting text chunks from: {pdf_path.name}")
    chunks = extract_text_chunks(pdf_path, max_chars=PREPROCESSING_MAX_CHARACTERS)
    logger.info(f"[EXTRACTOR] Extracted {len(chunks)} text chunks")
    return chunks


async def extract_images_with_preprocessing(pdf_path: Path) -> List[Dict[str, Any]]:
    logger.info(f"[EXTRACTOR] Extracting images from: {pdf_path.name}")
    images = extract_images(pdf_path)
    logger.info(f"[EXTRACTOR] Found {len(images)} images")
    return images