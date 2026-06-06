"""Evaluation pipeline entrypoint.

Runs four phases in sequence:
  1. Ingest dataset passages into the KI4KMU pipeline
  2. Retrieve contexts with both hybrid and vector-only pipelines
  3. Generate answers with Gemma 4 E2B
  4. Score with DeepEval and push to Confident AI

Each phase is independently resumable:
  - Phases 1-3 use JSONL checkpoints (one line per item, fsynced immediately).
  - Phase 4 uses DeepEval's built-in use_cache=True via Confident AI.

Set EVAL_START_PHASE env var to skip earlier phases (e.g. "3" to jump
directly to generation after retrieval is already checkpointed).
"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _load_dataset():
    from datasets import load_dataset
    from config import DATASET_NAME, DATASET_SPLIT
    logger.info("Loading dataset %s / %s ...", DATASET_NAME, DATASET_SPLIT)
    return load_dataset(DATASET_NAME, split=DATASET_SPLIT, trust_remote_code=True)


def main() -> None:
    start_phase = int(os.environ.get("EVAL_START_PHASE", "1"))

    dataset = None
    if start_phase <= 2:
        dataset = _load_dataset()

    if start_phase <= 1:
        logger.info("=== PHASE 1: Ingestion ===")
        from phases.phase1_ingest import run as run_phase1
        run_phase1(dataset)

    if start_phase <= 2:
        logger.info("=== PHASE 2: Retrieval ===")
        from phases.phase2_retrieve import run as run_phase2
        run_phase2(dataset)

    if start_phase <= 3:
        logger.info("=== PHASE 3: Generation ===")
        from phases.phase3_generate import run as run_phase3
        run_phase3()

    if start_phase <= 4:
        logger.info("=== PHASE 4: Scoring ===")
        from phases.phase4_score import run as run_phase4
        run_phase4()

    logger.info("=== Evaluation pipeline complete ===")


if __name__ == "__main__":
    main()
