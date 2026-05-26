import logging
import os
import threading

from gliner import GLiNER

logger = logging.getLogger(__name__)

GLINER_MODEL_ID = os.getenv("GLINER_MODEL_ID", "urchade/gliner_medium-v2.1")
GLINER_MODEL_PATH = os.getenv("GLINER_MODEL_PATH", "/ki4kmu_data/gliner-model")

_instance: "GLiNER | None" = None
_lock = threading.Lock()


def get_gliner() -> GLiNER:
    """Return the singleton GLiNER instance (thread-safe, lazy)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                logger.info("[GLINER] Loading model from %s (fallback: %s)", GLINER_MODEL_PATH, GLINER_MODEL_ID)
                try:
                    _instance = GLiNER.from_pretrained(GLINER_MODEL_PATH)
                except Exception:
                    logger.warning("[GLINER] Local path failed, downloading from HuggingFace: %s", GLINER_MODEL_ID)
                    _instance = GLiNER.from_pretrained(GLINER_MODEL_ID)
    return _instance
