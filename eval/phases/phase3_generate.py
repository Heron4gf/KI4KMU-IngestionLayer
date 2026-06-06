"""Phase 3 — Generate answers with Gemma 4 E2B for both pipelines.

For each retrieved sample calls the LLM twice (hybrid context, vector context)
using a simple RAG prompt. Errors are recorded and skipped gracefully.

Checkpoint: one record per sample written to CHECKPOINT_GENERATE.
  {
    "idx": int,
    "question": str,
    "expected_answer": str,
    "hybrid_contexts": [str, ...],
    "vector_contexts": [str, ...],
    "hybrid_answer": str,
    "vector_answer": str,
  }
"""
import logging

from openai import OpenAI

from checkpoint import count_lines, append_record, load_records
from config import (
    GEMMA_BASE_URL,
    GEMMA_API_KEY,
    GEMMA_MODEL,
    CHECKPOINT_RETRIEVE,
    CHECKPOINT_GENERATE,
)

logger = logging.getLogger(__name__)

_RAG_PROMPT = """You are a helpful assistant. Answer the question using ONLY the context below.
If the context does not contain enough information, say "I don't know".

Answer very briefly, if possible the answer should be straightforward, very few words, if you are doubtful about different alternative answers you can output multiple of them.

Context:
{context}

Question: {question}

Answer:"""


def _generate(client: OpenAI, question: str, contexts: list[str]) -> str:
    context_text = "\n\n".join(contexts) if contexts else "(no context retrieved)"
    prompt = _RAG_PROMPT.format(context=context_text, question=question)
    try:
        resp = client.chat.completions.create(
            model=GEMMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
            extra_body={
        "thinking": {
            "type": "enabled",
            "budget_tokens": 256   # reasoning gets at most 256, answer gets the rest
        }
    }
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("[PHASE3] LLM call failed for '%s': %s", question[:60], e)
        return ""


def run() -> None:
    retrieve_records = load_records(CHECKPOINT_RETRIEVE)
    if not retrieve_records:
        raise RuntimeError("[PHASE3] No retrieval records found — run phase 2 first.")

    already_done = count_lines(CHECKPOINT_GENERATE)
    logger.info("[PHASE3] %d samples to generate, %d already done", len(retrieve_records), already_done)

    client = OpenAI(base_url=GEMMA_BASE_URL, api_key=GEMMA_API_KEY)

    for i, rec in enumerate(retrieve_records):
        if i < already_done:
            continue

        hybrid_answer = _generate(client, rec["question"], rec["hybrid_contexts"])
        vector_answer = _generate(client, rec["question"], rec["vector_contexts"])

        append_record(CHECKPOINT_GENERATE, {
            "idx": rec["idx"],
            "question": rec["question"],
            "expected_answer": rec["expected_answer"],
            "hybrid_contexts": rec["hybrid_contexts"],
            "vector_contexts": rec["vector_contexts"],
            "hybrid_answer": hybrid_answer,
            "vector_answer": vector_answer,
        })

        if (i + 1) % 10 == 0:
            logger.info("[PHASE3] %d/%d done", i + 1, len(retrieve_records))

    logger.info("[PHASE3] Generation complete")
