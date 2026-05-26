import asyncio
import logging

from app.infrastructure.graphdb_reader import get_chunks_for_document
from app.services.enrichment.discovery import discover_raw_patterns
from app.services.enrichment.schema_curator import SchemaCurator
from app.services.enrichment.extractor import constrained_extraction
from app.services.enrichment.disambiguator import Disambiguator
from app.services.enrichment.reconciler import write_entity_triples

logger = logging.getLogger(__name__)

_curator = SchemaCurator()
_disambiguator = Disambiguator()


async def run_enrichment_pipeline(document_id: str) -> None:
    """Full enrichment pipeline for a single document, run after ingestion."""
    chunks = await asyncio.to_thread(get_chunks_for_document, document_id)
    if not chunks:
        logger.warning("[PIPELINE] No chunks found for document %s, skipping enrichment", document_id)
        return

    texts = [c["text"] for c in chunks]
    chunk_ids = [c["chunk_id"] for c in chunks]

    # Stage 1 — open discovery: GLiNER with broad label set
    logger.info("[PIPELINE] Stage 1: open discovery (%d chunks)", len(texts))
    raw_patterns = await asyncio.to_thread(discover_raw_patterns, texts)

    # Stage 2 — schema curation: merge new patterns into versioned schema
    logger.info("[PIPELINE] Stage 2: schema curation (%d raw patterns)", len(raw_patterns))
    schema = await _curator.evolve(raw_patterns)

    # Stage 3 — constrained extraction: GLiNER with schema-aligned labels
    logger.info("[PIPELINE] Stage 3: constrained extraction")
    triples = await asyncio.to_thread(
        constrained_extraction, texts, chunk_ids, schema
    )
    logger.info("[PIPELINE] Extracted %d raw triples", len(triples))

    # Stage 4 — disambiguation + reconciliation
    logger.info("[PIPELINE] Stage 4: disambiguate + write to GraphDB")
    merged_triples = await asyncio.to_thread(_disambiguator.merge, triples)
    await asyncio.to_thread(write_entity_triples, merged_triples, document_id)

    logger.info("[PIPELINE] Enrichment complete for document %s", document_id)
