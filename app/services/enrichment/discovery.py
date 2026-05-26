import logging
from typing import Any

from app.services.enrichment._gliner import get_gliner

logger = logging.getLogger(__name__)

# Broad open-domain labels for Stage 1 discovery.
# These intentionally cover many types — we are harvesting raw patterns,
# not yet constrained to the ki4kmu schema.
DISCOVERY_LABELS = [
    "machine",
    "component",
    "material",
    "process",
    "standard",
    "organization",
    "location",
    "measurement",
    "specification",
    "person",
    "product",
    "technology",
    "event",
]


def discover_raw_patterns(texts: list[str]) -> list[dict[str, Any]]:
    """
    Run GLiNER on all chunk texts with the broad discovery label set.
    Returns a list of raw entity mentions with type, surface form, and source text index.

    Each entry: {"type": str, "text": str, "score": float, "chunk_index": int}
    """
    model = get_gliner()
    patterns: list[dict[str, Any]] = []

    for idx, text in enumerate(texts):
        if not text.strip():
            continue
        try:
            entities = model.predict_entities(text, DISCOVERY_LABELS, threshold=0.4)
            for ent in entities:
                patterns.append({
                    "type": ent["label"],
                    "text": ent["text"],
                    "score": round(ent["score"], 4),
                    "chunk_index": idx,
                })
        except Exception as e:
            logger.warning("[DISCOVERY] GLiNER failed on chunk %d: %s", idx, e)

    logger.info("[DISCOVERY] Found %d raw entity mentions across %d chunks", len(patterns), len(texts))
    return patterns
