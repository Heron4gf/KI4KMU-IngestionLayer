import hashlib
import base64
from PIL import Image
from io import BytesIO
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import UploadFile


def cast_to_str(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def sanitize_metadata(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    clean: Dict[str, Any] = {}

    for key, value in raw.items():
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            if all(isinstance(v, (str, int, float, bool)) for v in value):
                clean[key] = value
            else:
                clean[key] = str(value)
        elif value is None:
            continue
        else:
            clean[key] = str(value)

    return clean


def get_image_path(element: Dict[str, Any]) -> Optional[str]:
    return (
        element.get("image_path")
        or (element.get("metadata") or {}).get("image_path")
        or (element.get("metadata") or {}).get("file_path")
    )


def image_to_b64(img: Image.Image) -> str:
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

async def save_upload_to_disk(file: UploadFile) -> Path:
    temp_dir = Path("/tmp/ingestion")
    temp_dir.mkdir(parents=True, exist_ok=True)
    target_path = temp_dir / file.filename
    with target_path.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)
    return target_path


def string_md5(text: str) -> str:
    """Calculate MD5 hash of a string."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def file_md5(file_path: Path) -> str:
    """Calculate MD5 hash of a file by reading it in chunks."""
    hash_md5 = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
