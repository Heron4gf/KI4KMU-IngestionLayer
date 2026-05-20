import logging
import os
import threading
from typing import List

import torch
from huggingface_hub import snapshot_download
from openrouter import OpenRouter
from transformers import AutoTokenizer, AutoModelForCausalLM

from app.core.config import (
    RERANK_MODEL,
    RERANKER_MODEL_PATH,
    HF_TOKEN,
    USE_LOCAL_RERANKER,
    OPENROUTER_API_KEY,
    OPENROUTER_RERANK_MODEL,
)

logger = logging.getLogger(__name__)

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")

_SYSTEM_PROMPT = (
    "Judge whether the following [document] is helpful for answering the [query]. "
    "Only reply with 'yes' or 'no'."
)


# ── Local reranker ────────────────────────────────────────────────────────────

def _model_is_cached(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, f)) for f in WEIGHT_FILES)


def _format_input(tokenizer: AutoTokenizer, query: str, document: str) -> str:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"[query]: {query}\n[document]: {document}"},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


class LocalRerankEmbedder:
    """Local reranker using Qwen/Qwen3-Reranker-0.6B."""

    def __init__(self, model_id: str = RERANK_MODEL):
        if not _model_is_cached(RERANKER_MODEL_PATH):
            logger.info("Downloading reranker model %s to %s", model_id, RERANKER_MODEL_PATH)
            snapshot_download(
                repo_id=model_id,
                local_dir=RERANKER_MODEL_PATH,
                token=HF_TOKEN or None,
            )

        logger.info("Loading reranker model from %s", RERANKER_MODEL_PATH)
        self._tokenizer = AutoTokenizer.from_pretrained(
            RERANKER_MODEL_PATH, padding_side="left"
        )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._model = AutoModelForCausalLM.from_pretrained(
            RERANKER_MODEL_PATH,
            torch_dtype=dtype,
            device_map=self._device,
        )
        self._model.eval()

        self._yes_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._no_id = self._tokenizer.convert_tokens_to_ids("no")
        logger.info(
            "Local reranker ready on %s (yes_id=%d, no_id=%d)",
            self._device, self._yes_id, self._no_id,
        )

    @torch.inference_mode()
    def _score_batch(self, inputs: List[str]) -> List[float]:
        encoded = self._tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self._device)

        logits = self._model(**encoded).logits[:, -1, :]
        yes_no_logits = logits[:, [self._yes_id, self._no_id]]
        probs = torch.softmax(yes_no_logits, dim=-1)
        return probs[:, 0].tolist()

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[float]:
        if not documents:
            return []
        inputs = [_format_input(self._tokenizer, query, doc) for doc in documents]
        return self._score_batch(inputs)


# ── OpenRouter reranker ───────────────────────────────────────────────────────

class OpenRouterRerankEmbedder:
    """Reranker backed by OpenRouter's rerank API (cohere/rerank-4-fast)."""

    def __init__(self):
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self._client = OpenRouter(api_key=OPENROUTER_API_KEY)
        self._model = OPENROUTER_RERANK_MODEL
        logger.info("OpenRouter reranker ready (model=%s)", self._model)

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[float]:
        if not documents:
            return []

        response = self._client.rerank.rerank(
            model=self._model,
            query=query,
            documents=documents,
            top_n=len(documents),
        )

        scores_by_index = {r.index: r.relevance_score for r in response.results}
        return [scores_by_index.get(i, 0.0) for i in range(len(documents))]

# ── Singleton factory ─────────────────────────────────────────────────────────

_instance: "LocalRerankEmbedder | OpenRouterRerankEmbedder | None" = None
_lock = threading.Lock()


def get_rerank_embedder() -> "LocalRerankEmbedder | OpenRouterRerankEmbedder":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                if USE_LOCAL_RERANKER:
                    logger.info("Using LOCAL reranker")
                    _instance = LocalRerankEmbedder()
                else:
                    logger.info("Using OpenRouter reranker")
                    _instance = OpenRouterRerankEmbedder()
    return _instance