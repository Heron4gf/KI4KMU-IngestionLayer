import asyncio
import logging
import os
import threading
from typing import List

import httpx

from app.core.config import OPENROUTER_API_KEY, RERANK_MODEL

logger = logging.getLogger(__name__)


class RerankEmbedder:
    """Embedder that uses OpenRouter API for reranking embeddings."""

    def __init__(
        self,
        model_id: str = RERANK_MODEL,
        api_key: str = OPENROUTER_API_KEY,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self._model_id = model_id
        self._api_key = api_key
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def _embed_single(self, text: str, input_type: str = None) -> List[float]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "http://localhost:8001",
            "X-OpenRouter-Title": "KI-4-KMU Ingestion API",
        }
        payload = {
            "input": text,
            "model": self._model_id,
        }
        if input_type:
            payload["input_type"] = input_type

        response = await self._client.post(
            f"{self._base_url}/embeddings",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        tasks = [self._embed_single(t) for t in texts]
        return await asyncio.gather(*tasks)

    async def compute_similarities(
        self, query_embedding: List[float], candidate_embeddings: List[List[float]]
    ) -> List[float]:
        """Compute cosine similarity between query and each candidate."""
        import math

        q = query_embedding
        scores = []
        for cand in candidate_embeddings:
            dot = sum(a * b for a, b in zip(q, cand))
            q_norm = math.sqrt(sum(a * a for a in q))
            c_norm = math.sqrt(sum(b * b for b in cand))
            sim = dot / (q_norm * c_norm) if q_norm and c_norm else 0.0
            scores.append(float(sim))
        return scores


_instance: "RerankEmbedder | None" = None
_lock = threading.Lock()


def get_rerank_embedder() -> "RerankEmbedder":
    """Return the singleton RerankEmbedder instance (thread-safe, lazy)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RerankEmbedder()
    return _instance
