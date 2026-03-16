from typing import Any, Dict, Optional

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