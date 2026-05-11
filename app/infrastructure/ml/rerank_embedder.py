import logging
import threading
from typing import List

import httpx

from app.core.config import OPENROUTER_API_KEY, RERANK_MODEL

logger = logging.getLogger(__name__)


class RerankEmbedder:
    """Reranker using OpenRouter /rerank endpoint."""

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

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[float]:
        """
        Call OpenRouter /rerank and return a relevance score list
        aligned to the original documents order.
        """
        # top_n must be >= 1 and <= len(documents)
        clamped_top_n = max(1, min(top_n, len(documents)))

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_id,
            "query": query,
            "documents": documents,
            "top_n": clamped_top_n,
        }
        response = await self._client.post(
            f"{self._base_url}/rerank",
            json=payload,
            headers=headers,
        )

        if response.status_code != 200:
            logger.error(
                "[RERANK] API error %d: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        data = response.json()
        scores = [0.0] * len(documents)
        for result in data.get("results", []):
            scores[result["index"]] = float(result["relevance_score"])
        return scores


_instance: "RerankEmbedder | None" = None
_lock = threading.Lock()


def get_rerank_embedder() -> "RerankEmbedder":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RerankEmbedder()
    return _instance
