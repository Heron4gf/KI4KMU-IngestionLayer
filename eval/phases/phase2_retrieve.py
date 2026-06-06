"""Phase 2 — Retrieve context for every sample using both pipelines.

For each dataset row calls:
  POST /v1/query        -> hybrid (graph + vector) pipeline
  POST /v1/query/vector -> vector-only baseline

Checkpoint: one record per sample written to CHECKPOINT_RETRIEVE.
  {
    "idx": int,
    "question": str,
    "expected_answer": str,
    "hybrid_contexts": [str, ...],
    "vector_contexts": [str, ...],
  }
"""
import logging

import httpx

from checkpoint import count_lines, append_record, load_records
from config import (
    INGESTION_API_URL,
    CHECKPOINT_RETRIEVE,
    EVAL_LIMIT,
    TOP_K,
)

logger = logging.getLogger(__name__)


def _query(client: httpx.Client, endpoint: str, question: str) -> list[str]:
    try:
        resp = client.post(
            f"{INGESTION_API_URL}{endpoint}",
            json={"query": question, "max_results_total": TOP_K},
            timeout=60,
        )
        resp.raise_for_status()
        return [r["text"] for r in resp.json().get("results", [])]
    except Exception as e:
        logger.warning("[PHASE2] Query error (%s) for '%s': %s", endpoint, question[:60], e)
        return []


def run(dataset) -> None:
    rows = list(dataset)
    if EVAL_LIMIT > 0:
        rows = rows[:EVAL_LIMIT]

    already_done = count_lines(CHECKPOINT_RETRIEVE)
    logger.info("[PHASE2] %d samples total, %d already done", len(rows), already_done)

    with httpx.Client(timeout=90) as client:
        for idx, row in enumerate(rows):
            if idx < already_done:
                continue

            question = (
                row.get("query")
                or row.get("question")
                or row.get("instruction")
                or ""
            ).strip()
            expected = (
                row.get("answer")
                or row.get("response")
                or row.get("output")
                or ""
            ).strip()

            hybrid_contexts = _query(client, "/v1/query", question)
            vector_contexts = _query(client, "/v1/query/vector", question)

            append_record(CHECKPOINT_RETRIEVE, {
                "idx": idx,
                "question": question,
                "expected_answer": expected,
                "hybrid_contexts": hybrid_contexts,
                "vector_contexts": vector_contexts,
            })

            if (idx + 1) % 10 == 0:
                logger.info("[PHASE2] %d/%d done", idx + 1, len(rows))

    logger.info("[PHASE2] Retrieval complete")
