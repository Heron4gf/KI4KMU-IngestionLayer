import base64
import io
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pymupdf4llm
from PIL import Image

from app.utils.text_cleaning import fix_extraction_artifacts, is_garbage_chunk

_MIN_IMAGE_PIXELS = 100 * 100  # ignore tiny icons/decorations


def extract_text_chunks(pdf_path: Path, max_chars: int = 1500) -> List[Dict[str, Any]]:
    pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    chunks = []
    for page in pages:
        text = fix_extraction_artifacts(page["text"].strip())
        if not text:
            continue
        page_num = page["metadata"]["page"]
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        buf = ""
        for para in paragraphs:
            if len(buf) + len(para) > max_chars and buf:
                if not is_garbage_chunk(buf):
                    chunks.append({
                        "type": "NarrativeText",
                        "text": buf,
                        "metadata": {"page_number": page_num},
                    })
                buf = para
            else:
                buf = (buf + "\n\n" + para).strip() if buf else para
        if buf and not is_garbage_chunk(buf):
            chunks.append({
                "type": "NarrativeText",
                "text": buf,
                "metadata": {"page_number": page_num},
            })
    return chunks


def extract_images(pdf_path: Path) -> List[Dict[str, Any]]:
    doc = fitz.open(str(pdf_path))
    elements = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            try:
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            except Exception:
                continue
            if pil_img.width * pil_img.height < _MIN_IMAGE_PIXELS:
                continue
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            elements.append({
                "type": "Image",
                "text": "",
                "metadata": {
                    "page_number": page_index + 1,
                    "image_base64": img_b64,
                },
            })
    doc.close()
    return elements