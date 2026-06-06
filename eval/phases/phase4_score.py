"""Phase 4 — Score with DeepEval and push results to Confident AI.

Builds LLMTestCase lists for both pipelines, then calls deepeval.evaluate()
twice (once per pipeline) with use_cache=True so Confident AI handles
resume automatically — already-scored test cases are not re-evaluated.

The judge LLM is the same Gemma 4 E2B instance used for generation,
provided via a thin OpenAIModel wrapper pointing at the custom endpoint.
"""
import logging

import deepeval
from deepeval import evaluate
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRecallMetric,
    ContextualPrecisionMetric,
)

from checkpoint import load_records
from config import (
    CONFIDENT_AI_KEY,
    GEMMA_BASE_URL,
    GEMMA_API_KEY,
    GEMMA_MODEL,
    CHECKPOINT_GENERATE,
)

logger = logging.getLogger(__name__)


def _build_test_cases(records: list[dict], pipeline: str) -> list[LLMTestCase]:
    context_key = f"{pipeline}_contexts"
    answer_key = f"{pipeline}_answer"
    cases = []
    for rec in records:
        answer = rec.get(answer_key, "").strip()
        if not answer:
            continue  # skip rows where generation errored
        cases.append(
            LLMTestCase(
                input=rec["question"],
                actual_output=answer,
                expected_output=rec["expected_answer"],
                retrieval_context=rec.get(context_key, []),
            )
        )
    return cases


def run() -> None:
    records = load_records(CHECKPOINT_GENERATE)
    if not records:
        raise RuntimeError("[PHASE4] No generation records found — run phase 3 first.")

    logger.info("[PHASE4] Logging into Confident AI...")
    deepeval.login_with_confident_ai(api_key=CONFIDENT_AI_KEY)

    judge = OpenAIModel(
        model=GEMMA_MODEL,
        base_url=GEMMA_BASE_URL,
        api_key=GEMMA_API_KEY,
    )

    metrics = [
        AnswerRelevancyMetric(model=judge, threshold=0.5),
        FaithfulnessMetric(model=judge, threshold=0.5),
        ContextualRecallMetric(model=judge, threshold=0.5),
        ContextualPrecisionMetric(model=judge, threshold=0.5),
    ]

    for pipeline in ("hybrid", "vector"):
        test_cases = _build_test_cases(records, pipeline)
        if not test_cases:
            logger.warning("[PHASE4] No valid test cases for pipeline '%s', skipping", pipeline)
            continue

        logger.info(
            "[PHASE4] Evaluating pipeline '%s' — %d test cases",
            pipeline, len(test_cases),
        )

        evaluate(
            test_cases=test_cases,
            metrics=metrics,
            run_async=False,
            use_cache=True,
            identifier=f"ki4kmu-{pipeline}",
        )

        logger.info("[PHASE4] Pipeline '%s' evaluation pushed to Confident AI", pipeline)

    logger.info("[PHASE4] Scoring complete")
