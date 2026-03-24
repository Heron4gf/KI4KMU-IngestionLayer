import asyncio
import httpx
import tempfile
from fastapi import HTTPException, status
from pathlib import Path
from typing import Any, Dict, List, Optional
from pypdf import PdfWriter, PdfReader
from app.core.config import UNSTRUCTURED_URL, UNSTRUCTURED_READ_TIMEOUT, UNSTRUCTURED_SPLIT_PAGE_SIZE, UNSTRUCTURED_SPLIT_CONCURRENCY


async def _call_unstructured_single(
    client: httpx.AsyncClient,
    pdf_path: Path,
    starting_page_number: int,
    **kwargs,
) -> List[Dict[str, Any]]:
    data: Dict[str, Any] = {
        "skip_infer_table_types": [],
        "starting_page_number": str(starting_page_number),
    }
    for key, val in kwargs.items():
        if val is not None:
            if isinstance(val, list):
                data[key] = val
            else:
                data[key] = str(val) if not isinstance(val, bool) else val

    with pdf_path.open("rb") as f:
        response = await client.post(
            UNSTRUCTURED_URL,
            files={"files": (pdf_path.name, f, "application/pdf")},
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


def _split_pdf_to_batches(pdf_path: Path, page_size: int) -> List[tuple[Path, int]]:
    """Split a PDF into temporary per-batch files. Returns list of (tmp_path, starting_page_number)."""
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    batches = []

    for start in range(0, total_pages, page_size):
        end = min(start + page_size, total_pages)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        writer.write(tmp)
        tmp.close()
        batches.append((Path(tmp.name), start + 1))  # starting_page_number is 1-indexed

    return batches


async def _call_unstructured(
    pdf_path: Path,
    chunking_strategy: Optional[str] = None,
    max_characters: Optional[int] = None,
    overlap: Optional[int] = None,
    extract_image_block_types: Optional[List[str]] = None,
    extract_image_block_to_payload: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    kwargs = {
        "chunking_strategy": chunking_strategy,
        "max_characters": max_characters,
        "overlap": overlap,
        "extract_image_block_types": extract_image_block_types,
        "extract_image_block_to_payload": extract_image_block_to_payload,
    }

    timeout = httpx.Timeout(connect=30.0, write=60.0, read=UNSTRUCTURED_READ_TIMEOUT, pool=60.0)
    batches = _split_pdf_to_batches(pdf_path, UNSTRUCTURED_SPLIT_PAGE_SIZE)

    semaphore = asyncio.Semaphore(UNSTRUCTURED_SPLIT_CONCURRENCY)

    async def _process_batch(batch_path: Path, starting_page: int) -> List[Dict[str, Any]]:
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    return await _call_unstructured_single(client, batch_path, starting_page, **kwargs)
            finally:
                batch_path.unlink(missing_ok=True)

    tasks = [_process_batch(p, start) for p, start in batches]
    results = await asyncio.gather(*tasks)

    return [element for batch_result in results for element in batch_result]
