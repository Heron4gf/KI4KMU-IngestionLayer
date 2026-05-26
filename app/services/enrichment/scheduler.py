import asyncio
import logging

from app.services.enrichment.enrichment_store import EnrichmentJobStore, EnrichmentJobStatus
from app.services.enrichment.pipeline import run_enrichment_pipeline

logger = logging.getLogger(__name__)

_ingesting: int = 0
_querying: int = 0
_store = EnrichmentJobStore()


def on_ingestion_start() -> None:
    global _ingesting
    _ingesting += 1


def on_ingestion_end() -> None:
    global _ingesting
    _ingesting = max(0, _ingesting - 1)


def on_query_start() -> None:
    global _querying
    _querying += 1


def on_query_end() -> None:
    global _querying
    _querying = max(0, _querying - 1)


def is_idle() -> bool:
    return _ingesting == 0 and _querying == 0


def enqueue_enrichment(document_id: str) -> None:
    _store.enqueue(document_id)
    logger.info("[ENRICHMENT] Queued enrichment for document %s", document_id)


async def idle_loop(poll_interval: int = 15) -> None:
    """Background coroutine. Started once on app startup via lifespan."""
    logger.info("[ENRICHMENT] Idle-loop started (poll=%ds)", poll_interval)
    while True:
        await asyncio.sleep(poll_interval)
        if not is_idle():
            continue
        pending = _store.pop_pending()
        if not pending:
            continue
        doc_id, job_id = pending
        logger.info("[ENRICHMENT] Starting enrichment job %s for document %s", job_id, doc_id)
        _store.set_status(job_id, EnrichmentJobStatus.PROCESSING)
        try:
            await run_enrichment_pipeline(doc_id)
            _store.set_status(job_id, EnrichmentJobStatus.COMPLETED)
            logger.info("[ENRICHMENT] Job %s completed for document %s", job_id, doc_id)
        except Exception as e:
            _store.set_status(job_id, EnrichmentJobStatus.FAILED, error=str(e))
            logger.error("[ENRICHMENT] Job %s failed for document %s: %s", job_id, doc_id, e)
