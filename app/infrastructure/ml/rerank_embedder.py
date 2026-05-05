import logging
import os
from typing import List

import torch
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

from app.core.config import RERANK_MODEL, RERANK_MODEL_PATH

logger = logging.getLogger(__name__)

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def _model_is_cached(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, f)) for f in WEIGHT_FILES)


class RerankEmbedder:
    """Embedder used for reranking chunks against a query."""

    def __init__(self, model_id: str = RERANK_MODEL):
        if not _model_is_cached(RERANK_MODEL_PATH):
            logger.info(f"Downloading reranker model {model_id} to {RERANK_MODEL_PATH}")
            snapshot_download(
                repo_id=model_id,
                local_dir=RERANK_MODEL_PATH,
                token=os.getenv("HF_TOKEN") or None,
            )

        logger.info(f"Loading reranker model from {RERANK_MODEL_PATH}")
        self._model = SentenceTransformer(RERANK_MODEL_PATH, trust_remote_code=True)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=False,
            device=self._device,
            normalize_embeddings=True,
        )
        return [e.tolist() for e in embeddings]

    def compute_similarities(
        self, query_embedding: List[float], candidate_embeddings: List[List[float]]
    ) -> List[float]:
        """Compute cosine similarity between query and each candidate."""
        import torch.nn.functional as F

        q = torch.tensor(query_embedding, device=self._device)
        scores = []
        for cand in candidate_embeddings:
            c = torch.tensor(cand, device=self._device)
            sim = F.cosine_similarity(q.unsqueeze(0), c.unsqueeze(0), dim=1)
            scores.append(float(sim.item()))
        return scores


rerank_embedder = RerankEmbedder()
