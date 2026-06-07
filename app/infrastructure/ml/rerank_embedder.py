import logging
import os
import threading
from typing import List

import torch
from huggingface_hub import snapshot_download
from openrouter import OpenRouter
from sentence_transformers import CrossEncoder

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


def _model_is_cached(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, f)) for f in WEIGHT_FILES)


class LocalRerankEmbedder:
    """Local reranker using cross-encoder/ettin-reranker-17m-v1 via sentence-transformers."""

    def __init__(self, model_id: str = RERANK_MODEL):
        if not _model_is_cached(RERANKER_MODEL_PATH):
            logger.info("Downloading reranker model %s to %s", model_id, RERANKER_MODEL_PATH)
            snapshot_download(
                repo_id=model_id,
                local_dir=RERANKER_MODEL_PATH,
                token=HF_TOKEN or None,
            )

        logger.info("Loading reranker model from %s", RERANKER_MODEL_PATH)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = "bfloat16" if device == "cuda" else "float32"

        self._model = CrossEncoder(
            RERANKER_MODEL_PATH,
            model_kwargs={"torch_dtype": dtype},
            tokenizer_args={"use_fast": False},
            device=device,
        )
        logger.info("Local CrossEncoder reranker ready on %s", device)

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[float]:
        if not documents:
            return []
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs)
        return scores.tolist()


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