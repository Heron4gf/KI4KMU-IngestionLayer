import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

UNSTRUCTURED_URL = os.getenv(
    "UNSTRUCTURED_URL",
    "http://unstructured:8000/general/v0/general",
)

UNSTRUCTURED_CHUNKING_STRATEGY = os.getenv(
    "UNSTRUCTURED_CHUNKING_STRATEGY",
    "by_title",
)
UNSTRUCTURED_MAX_CHARACTERS = int(os.getenv("UNSTRUCTURED_MAX_CHARACTERS", "1000"))
UNSTRUCTURED_OVERLAP = int(os.getenv("UNSTRUCTURED_OVERLAP", "150"))


async def _call_unstructured(
    pdf_path: Path,
    chunking_strategy: Optional[str] = None,
    max_characters: Optional[int] = None,
    overlap: Optional[int] = None,
    extract_image_block_types: Optional[List[str]] = None,
    extract_image_block_to_payload: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Base function to call Unstructured API with configurable parameters."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        files = {
            "files": (
                pdf_path.name,
                pdf_path.open("rb"),
                "application/pdf",
            )
        }
        data: Dict[str, Any] = {
            "skip_infer_table_types": [],
        }
        
        # Add chunking parameters only if provided
        if chunking_strategy is not None:
            data["chunking_strategy"] = chunking_strategy
        if max_characters is not None:
            data["max_characters"] = str(max_characters)
        if overlap is not None:
            data["overlap"] = str(overlap)
        
        # Add image extraction parameters only if provided
        if extract_image_block_types is not None:
            data["extract_image_block_types"] = extract_image_block_types
        if extract_image_block_to_payload is not None:
            data["extract_image_block_to_payload"] = extract_image_block_to_payload
        
        response = await client.post(
            UNSTRUCTURED_URL,
            files=files,
            data=data,
        )
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unstructured API error ({response.status_code}): {response.text}",
        )
    elements = response.json()
    if not isinstance(elements, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unstructured API did not return a list of elements.",
        )
    return elements


async def chunk_pdf_with_unstructured(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extract text chunks from PDF using Unstructured.
    
    This function focuses ONLY on text chunking:
    - Uses chunking_strategy=by_title
    - No image extraction (extract_image_block_types not set)
    - Returns text elements that can be embedded directly
    """
    logger.info(f"[UNSTRUCTURED] Extracting text chunks from: {pdf_path.name}")
    
    elements = await _call_unstructured(
        pdf_path,
        chunking_strategy=UNSTRUCTURED_CHUNKING_STRATEGY,
        max_characters=UNSTRUCTURED_MAX_CHARACTERS,
        overlap=UNSTRUCTURED_OVERLAP,
        # Explicitly NO image extraction for text-only path
    )
    
    # Filter out any Image elements that might slip through
    text_elements = [e for e in elements if e.get("type") != "Image"]
    logger.info(f"[UNSTRUCTURED] Extracted {len(text_elements)} text chunks")
    
    return text_elements


async def extract_images_with_unstructured(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extract raw images from PDF using Unstructured.
    
    This function extracts ONLY images without chunking:
    - No chunking_strategy (raw extraction)
    - extract_image_block_types=["Image"] for image elements
    - extract_image_block_to_payload=True to get base64 payload
    - Returns elements with type=="Image" and metadata.image_base64
    """
    logger.info(f"[UNSTRUCTURED] Extracting raw images from: {pdf_path.name}")
    
    elements = await _call_unstructured(
        pdf_path,
        # No chunking for image extraction
        extract_image_block_types=["Image"],
        extract_image_block_to_payload=True,
    )
    
    # Filter to keep only Image elements with base64 payload
    image_elements = []
    for element in elements:
        element_type = element.get("type", "")
        raw_metadata = element.get("metadata") or {}
        image_base64 = raw_metadata.get("image_base64")
        
        if element_type == "Image":
            if image_base64:
                image_elements.append(element)
                logger.debug(f"[UNSTRUCTURED] Found Image with base64: {len(image_base64)} chars")
            else:
                logger.warning(f"[UNSTRUCTURED] Image element missing image_base64, skipping")
        else:
            logger.debug(f"[UNSTRUCTURED] Skipping non-Image element: {element_type}")
    
    logger.info(f"[UNSTRUCTURED] Extracted {len(image_elements)} raw images with base64")
    
    return image_elements
