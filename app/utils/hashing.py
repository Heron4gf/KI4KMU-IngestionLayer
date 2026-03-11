import hashlib
from pathlib import Path

def string_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def file_md5(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()