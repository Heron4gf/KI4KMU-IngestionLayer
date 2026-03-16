import httpx
from fastapi import HTTPException, status
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import UNSTRUCTURED_URL

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