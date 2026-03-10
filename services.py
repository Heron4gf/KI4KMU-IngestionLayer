"""
Service module for document processing business logic.

This module contains the orchestration logic for:
- Image extraction and captioning pipeline
- Document processing pipeline
- Coordination between text chunking, image processing, and storage
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image
import base64
import io

from unstructured_manager import (
    chunk_pdf_with_unstructured,
    extract_images_with_unstructured,
)
from chroma_manager import store_chunks_in_chroma
from ml_services import captioner


logger = logging.getLogger(__name__)


async def process_images_pipeline(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extract images from PDF and generate captions in parallel.
    
    This function:
    1. Calls extract_images_with_unstructured to get raw images
    2. Maps caption generation over all images using asyncio.gather
    3. Returns list of captioned image elements
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of image elements with captions added to metadata
    """
    logger.info(f"[SERVICE] Starting image processing pipeline for: {pdf_path.name}")
    
    # Step 1: Extract raw images with base64 payload
    image_elements = await extract_images_with_unstructured(pdf_path)
    logger.info(f"[SERVICE] Extracted {len(image_elements)} raw images")
    
    if not image_elements:
        logger.info("[SERVICE] No images found, skipping captioning")
        return []
    
    # Step 2: Generate captions in parallel
    async def caption_image(element: Dict[str, Any]) -> Dict[str, Any]:
        """Caption a single image element."""
        raw_metadata = element.get("metadata") or {}
        image_b64 = raw_metadata.get("image_base64")
        
        if not image_b64:
            logger.warning("[SERVICE] Image element missing base64, skipping")
            return None
        
        # Decode base64 to PIL Image
        try:
            img_data = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
        except Exception as e:
            logger.warning(f"[SERVICE] Failed to decode image: {e}")
            return None
        
        # Generate caption using VLM
        try:
            caption = captioner.caption(img)
            if not caption:
                logger.warning("[SERVICE] Caption generation returned empty")
                return None
            
            # Add caption to element metadata
            element["metadata"]["image_caption"] = caption
            return element
        except Exception as e:
            logger.warning(f"[SERVICE] Caption generation failed: {e}")
            return None
    
    # Run all captioning tasks in parallel
    caption_tasks = [caption_image(elem) for elem in image_elements]
    captioned_results = await asyncio.gather(*caption_tasks)
    
    # Filter out None results (failed captions)
    captioned_images = [r for r in captioned_results if r is not None]
    
    logger.info(
        f"[SERVICE] Image pipeline complete: {len(captioned_images)}/{len(image_elements)} images captioned"
    )
    
    return captioned_images


async def process_document(
    pdf_path: Path,
    document_id: str,
    pdf_hash: str,
) -> int:
    """
    Process a complete document through the ingestion pipeline.
    
    This function orchestrates:
    1. Text chunking (parallel with image processing)
    2. Image extraction and captioning (parallel with text chunking)
    3. Storage of all chunks in Chroma
    
    Args:
        pdf_path: Path to the PDF file
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
        
    Returns:
        Total number of chunks stored in Chroma
    """
    logger.info(f"[SERVICE] Starting document processing for: {pdf_path.name}")
    
    # Run text chunking and image processing in parallel
    text_elements, captioned_images = await asyncio.gather(
        chunk_pdf_with_unstructured(pdf_path),
        process_images_pipeline(pdf_path),
    )
    
    logger.info(
        f"[SERVICE] Pipeline complete: {len(text_elements)} text chunks, "
        f"{len(captioned_images)} captioned images"
    )
    
    # Store all chunks in Chroma
    num_stored = store_chunks_in_chroma(
        text_elements=text_elements,
        captioned_images=captioned_images,
        document_id=document_id,
        pdf_hash=pdf_hash,
    )
    
    logger.info(f"[SERVICE] Stored {num_stored} chunks in Chroma")
    
    return num_stored