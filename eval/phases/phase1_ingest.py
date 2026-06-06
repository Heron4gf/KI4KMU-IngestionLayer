"""Phase 1 — Ingest dataset passages into the pipeline.

Groups dataset rows into batches and calls POST /v1/documents/text on the
ingestion API. Each batch becomes one document_id (eval-batch-NNN).
Polls the job status endpoint until completion before moving to the next batch.

Checkpoint: one record per batch written to CHECKPOINT_INGEST.
  {"idx": batch_idx, "document_id": "eval-batch-NNN", "status": "ok"|"failed"}
"""
import logging
import time

import httpx

from checkpoint import count_lines, append_record
from config import (
    INGESTION_API_URL,
    INGEST_BATCH_SIZE,
    CHECKPOINT_INGEST,
    EVAL_LIMIT,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3   # seconds between job-status polls
_POLL_TIMEOUT  = 300 # seconds before giving up on a job


def _wait_for_job(client: httpx.Client, job_id: str) -> str:
    """Poll /v1/jobs/{job_id} until terminal status. Returns 'completed' or 'failed'."""
    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        resp = client.get(f"{INGESTION_API_URL}/v1/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        st = data.get("status", "")
        if st == "completed":
            return "completed"
        if st == "failed":
            logger.warning("[PHASE1] Job %s failed: %s", job_id, data.get("error"))
            return "failed"
        time.sleep(_POLL_INTERVAL)
    logger.warning("[PHASE1] Job %s timed out", job_id)
    return "failed"


def run(dataset) -> None:
    rows = list(dataset)
    if EVAL_LIMIT > 0:
        rows = rows[:EVAL_LIMIT]

    # Build batches
    batches = [
        rows[i : i + INGEST_BATCH_SIZE]
        for i in range(0, len(rows), INGEST_BATCH_SIZE)
    ]

    already_done = count_lines(CHECKPOINT_INGEST)
    logger.info("[PHASE1] %d batches total, %d already done", len(batches), already_done)

    with httpx.Client(timeout=60) as client:
        for batch_idx, batch in enumerate(batches):
            if batch_idx < already_done:
                continue

            document_id = f"eval-batch-{batch_idx:04d}"

            # Dataset rows vary by split; normalise to {text, title}
            passages = []
            for row in batch:
                text = (
                    row.get("context")
                    or row.get("content")
                    or row.get("text")
                    or ""
                ).strip()
                title = (
                    row.get("query")
                    or row.get("question")
                    or row.get("instruction")
                    or ""
                )[:120]
                if text:
                    passages.append({"text": text, "title": title})

            if not passages:
                logger.warning("[PHASE1] Batch %d has no usable text, skipping", batch_idx)
                append_record(CHECKPOINT_INGEST, {"idx": batch_idx, "document_id": document_id, "status": "skipped"})
                continue

            try:
                resp = client.post(
                    f"{INGESTION_API_URL}/v1/documents/text",
                    json={"passages": passages, "document_id": document_id},
                    timeout=30,
                )
                resp.raise_for_status()
                job_id = resp.json()["job_id"]
                status = _wait_for_job(client, job_id)
            except Exception as e:
                logger.error("[PHASE1] Batch %d ingestion error: %s", batch_idx, e)
                status = "failed"

            append_record(CHECKPOINT_INGEST, {"idx": batch_idx, "document_id": document_id, "status": status})
            logger.info("[PHASE1] Batch %d/%d — %s", batch_idx + 1, len(batches), status)

    logger.info("[PHASE1] Ingestion complete")
