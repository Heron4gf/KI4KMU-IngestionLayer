import os
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException, status

UNSTRUCTURED_URL = os.getenv(
    "UNSTRUCTURED_URL",
    "http://unstructured:8000/general/v0/general",
)

UNSTRUCTURED_CHUNKING_STRATEGY = os.getenv(
    "UNSTRUCTURED_CHUNKING_STRATEGY",
    "by_title",
)
UNSTRUCTURED_MAX_CHARACTERS = os.getenv(
    "UNSTRUCTURED_MAX_CHARACTERS",
    "1000",
)
UNSTRUCTURED_OVERLAP = os.getenv(
    "UNSTRUCTURED_OVERLAP",
    "150",
)


async def chunk_pdf_with_unstructured(pdf_path: Path) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=300.0) as client:
        files = {
            "files": (
                pdf_path.name,
                pdf_path.open("rb"),
                "application/pdf",
            )
        }
        data = {
            "chunking_strategy": UNSTRUCTURED_CHUNKING_STRATEGY,
            "max_characters": UNSTRUCTURED_MAX_CHARACTERS,
            "overlap": UNSTRUCTURED_OVERLAP,
            "skip_infer_table_types": []
        }
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