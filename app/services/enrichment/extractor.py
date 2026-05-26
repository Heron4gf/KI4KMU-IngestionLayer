import logging
from typing import Any

from app.services.enrichment._gliner import get_gliner

logger = logging.getLogger(__name__)


def constrained_extraction(
    texts: list[str],
    chunk_ids: list[str],
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Stage 3: run GLiNER with the curated schema entity_types as the label set.
    Produces ontology-aligned entity mentions tagged to their source chunk.

    Each triple entry:
    {
        "subject": str,       # surface form
        "subject_type": str,  # canonical entity type
        "chunk_id": str,
        "score": float,
    }
    """
    entity_types = schema.get("entity_types", [])
    if not entity_types:
        logger.warning("[EXTRACTOR] Schema has no entity types — skipping constrained extraction")
        return []

    model = get_gliner()
    triples: list[dict[str, Any]] = []

    for text, chunk_id in zip(texts, chunk_ids):
        if not text.strip():
            continue
        try:
            entities = model.predict_entities(text, entity_types, threshold=0.45)
            for ent in entities:
                triples.append({
                    "subject": ent["text"],
                    "subject_type": ent["label"],
                    "chunk_id": chunk_id,
                    "score": round(ent["score"], 4),
                })
        except Exception as e:
            logger.warning("[EXTRACTOR] GLiNER constrained pass failed on chunk %s: %s", chunk_id, e)

    logger.info("[EXTRACTOR] Constrained extraction produced %d entity mentions", len(triples))
    return triples
