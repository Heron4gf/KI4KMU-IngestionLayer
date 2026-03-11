import asyncio
import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from app.services.unstructured_service import extract_images_with_unstructured
from app.infrastructure.ml.captioner import captioner

logger = logging.getLogger(__name__)


async def process_images_pipeline(pdf_path: Path) -> List[Dict[str, Any]]:
    image_elements = await extract_images_with_unstructured(pdf_path)

    if not image_elements:
        return []

    async def caption_image(element: Dict[str, Any]) -> Dict[str, Any] | None:
        raw_metadata = element.get("metadata") or {}
        image_b64 = raw_metadata.get("image_base64")

        if not image_b64:
            return None

        try:
            img_data = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
        except Exception:
            return None

        try:
            caption = await asyncio.to_thread(captioner.caption, img)
            if not caption:
                return None

            element["metadata"]["image_caption"] = caption
            return element
        except Exception:
            return None

    caption_tasks = [caption_image(elem) for elem in image_elements]
    captioned_results = await asyncio.gather(*caption_tasks)

    captioned_images = [r for r in captioned_results if r is not None]

    return captioned_images