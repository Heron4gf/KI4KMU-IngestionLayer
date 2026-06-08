"""Phase 4 — Score with DeepEval and push results to Confident AI.

Builds LLMTestCase lists for both pipelines, then calls deepeval.evaluate()
in chunks of CHUNK_SIZE to stay under DeepEval's 1800s gather timeout.
After each chunk the scored records are appended to a JSONL checkpoint so
the phase can resume from where it left off on restart.

The judge LLM is the same Gemma 4 E2B instance used for generation,
provided via RobustJudgeModel — a GPTModel subclass that repairs malformed
JSON before deepeval's own parser sees it.
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import re

from pydantic import ValidationError

from deepeval import evaluate
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRecallMetric,
    ContextualPrecisionMetric,
)
from deepeval.evaluate import AsyncConfig, CacheConfig

from checkpoint import load_records, append_record
from config import (
    CONFIDENT_AI_KEY,
    GEMMA_BASE_URL,
    GEMMA_API_KEY,
    GEMMA_MODEL,
    CHECKPOINT_GENERATE,
    CHECKPOINT_SCORE_HYBRID,
    CHECKPOINT_SCORE_VECTOR,
)
from robust_judge import RobustJudgeModel

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3          # small chunks to stay well under DeepEval's 1800s gather timeout
MAX_JSON_RETRIES = 3    # retries per LLM call when output is malformed or schema-invalid

CHECKPOINT_BY_PIPELINE = {
    "hybrid": CHECKPOINT_SCORE_HYBRID,
    "vector": CHECKPOINT_SCORE_VECTOR,
}


# ---------------------------------------------------------------------------
# Robust judge wrapper — retries on malformed JSON *and* Pydantic validation
# errors (e.g. Gemma returns {"reason": "..."} but omits required "verdict")
# ---------------------------------------------------------------------------

class _RobustJudgeLLM(DeepEvalBaseLLM):
    """Wraps any DeepEvalBaseLLM and retries generation when the response is
    either not valid JSON (schema=None path) or fails Pydantic schema
    validation (schema!=None path).  Both sync and async paths are covered
    because DeepEval metrics run with async_mode=True."""

    def __init__(self, inner: DeepEvalBaseLLM) -> None:
        self._inner = inner

    # --- DeepEvalBaseLLM interface -----------------------------------------

    def get_model_name(self) -> str:
        return self._inner.get_model_name()

    def load_model(self):
        return self._inner.load_model()

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _is_valid_json(text: str) -> bool:
        """Return True if *text* contains a parseable JSON object or array."""
        try:
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", str(text).strip(), flags=re.DOTALL
            )
            json.loads(cleaned)
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    # --- sync --------------------------------------------------------------

    def generate(self, prompt: str, schema=None):
        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(1, MAX_JSON_RETRIES + 1):
            try:
                result, cost = self._inner.generate(prompt, schema=schema)
                # schema=None → DeepEval expects a raw string; validate JSON ourselves
                if schema is None and not self._is_valid_json(result):
                    raise ValueError(f"Response is not valid JSON: {str(result)[:120]}")
                # schema!=None → DeepEval already called schema.model_validate()
                # inside _inner.generate; if it raised ValidationError it bubbles here
                return result, cost
            except (ValidationError, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "[RobustJudge] Invalid output on attempt %d/%d (sync): %s — retrying",
                    attempt, MAX_JSON_RETRIES, exc,
                )
        logger.error(
            "[RobustJudge] All %d retries exhausted (sync) — re-raising", MAX_JSON_RETRIES
        )
        raise last_exc

    # --- async -------------------------------------------------------------

    async def a_generate(self, prompt: str, schema=None):
        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(1, MAX_JSON_RETRIES + 1):
            try:
                result, cost = await self._inner.a_generate(prompt, schema=schema)
                if schema is None and not self._is_valid_json(result):
                    raise ValueError(f"Response is not valid JSON: {str(result)[:120]}")
                return result, cost
            except (ValidationError, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "[RobustJudge] Invalid output on attempt %d/%d (async): %s — retrying",
                    attempt, MAX_JSON_RETRIES, exc,
                )
        logger.error(
            "[RobustJudge] All %d retries exhausted (async) — re-raising", MAX_JSON_RETRIES
        )
        raise last_exc


# ---------------------------------------------------------------------------
# Test-case builder
# ---------------------------------------------------------------------------

def _build_test_cases(records: list[dict], pipeline: str) -> list[LLMTestCase]:
    context_key = f"{pipeline}_contexts"
    answer_key  = f"{pipeline}_answer"
    cases = []
    for rec in records:
        answer = rec.get(answer_key, "").strip()
        if not answer:
            continue
        cases.append(
            LLMTestCase(
                input=rec["question"],
                actual_output=answer,
                expected_output=rec["expected_answer"],
                retrieval_context=rec.get(context_key, []),
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> None:
    records = load_records(CHECKPOINT_GENERATE)
    if not records:
        raise RuntimeError("[PHASE4] No generation records found — run phase 3 first.")

    logger.info("[PHASE4] Logging into Confident AI...")
    confident_key = os.environ.get("CONFIDENT_AI_KEY", "")
    logger.info(
        "[PHASE4] Confident AI key (first 10 chars): '%s'",
        confident_key[:10] if confident_key else "EMPTY",
    )

    judge = RobustJudgeModel(
        model=GEMMA_MODEL,
        base_url=GEMMA_BASE_URL,
        api_key=GEMMA_API_KEY,
    )
    judge = _RobustJudgeLLM(_inner_judge)

    metrics = [
        AnswerRelevancyMetric(model=judge, threshold=0.5),
        FaithfulnessMetric(model=judge, threshold=0.5),
        ContextualRecallMetric(model=judge, threshold=0.5),
        ContextualPrecisionMetric(model=judge, threshold=0.5),
    ]

    for pipeline in ("hybrid", "vector"):
        test_cases = _build_test_cases(records, pipeline)
        if not test_cases:
            logger.warning(
                "[PHASE4] No valid test cases for pipeline '%s', skipping", pipeline
            )
            continue

        checkpoint_path = CHECKPOINT_BY_PIPELINE[pipeline]
        done_records    = load_records(checkpoint_path)
        done_inputs     = {r["input"] for r in done_records}

        # Enumerate with stable original index so checkpoint idx never shifts
        # when we resume from a partial run.
        indexed_remaining = [
            (orig_idx, tc)
            for orig_idx, tc in enumerate(test_cases)
            if tc.input not in done_inputs
        ]

        logger.info(
            "[PHASE4] Pipeline '%s' — %d already scored, %d remaining",
            pipeline, len(done_inputs), len(indexed_remaining),
        )

        if not indexed_remaining:
            logger.info("[PHASE4] Pipeline '%s' already complete, skipping", pipeline)
            continue

        total_chunks = -(-len(remaining) // CHUNK_SIZE)
        for chunk_i, start in enumerate(range(0, len(remaining), CHUNK_SIZE), 1):
            chunk = remaining[start : start + CHUNK_SIZE]
            logger.info(
                "[PHASE4] %s chunk %d/%d (%d cases)",
                pipeline, chunk_i, total_chunks, len(chunk_tcs),
            )

            results = evaluate(
                test_cases=chunk_tcs,
                metrics=metrics,
                identifier=f"ki4kmu-{pipeline}",
                async_config=AsyncConfig(max_concurrent=1, throttle_value=5),
                cache_config=CacheConfig(use_cache=True),
            )

            # Map input → original index for stable checkpoint writing
            input_to_idx = {tc.input: idx for idx, tc in chunk_pairs}

            for r in results.test_results:
                append_record(checkpoint_path, {
                    "idx":           input_to_idx.get(r.input, -1),
                    "input":         r.input,
                    "actual_output": r.actual_output,
                    "metrics": {
                        m.name: m.score for m in (r.metrics_data or [])
                    },
                })
            done_inputs.update(r.input for r in results.test_results)
            logger.info(
                "[PHASE4] %s chunk %d/%d saved to checkpoint",
                pipeline, chunk_i, total_chunks,
            )

        logger.info("[PHASE4] Pipeline '%s' evaluation complete", pipeline)

    logger.info("[PHASE4] Scoring complete")