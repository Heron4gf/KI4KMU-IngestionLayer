import logging
from typing import List

import torch
from sentence_transformers import SentenceTransformer

from app.core.config import TEXT_MODEL, HF_TOKEN, EMBEDDING_MODEL_PATH
import os

logger = logging.getLogger(__name__)


class TextEmbedder:
    """
    Text embedding service using SentenceTransformer.
    
    This class is responsible solely for generating text embeddings.
    It does not handle any image processing or ML inference beyond embeddings.
    """
    def __init__(self, model_id: str = TEXT_MODEL):
        if os.path.isdir(EMBEDDING_MODEL_PATH) and os.listdir(EMBEDDING_MODEL_PATH):
            self._model = SentenceTransformer(EMBEDDING_MODEL_PATH, trust_remote_code=True)
        else:
            kwargs = {"trust_remote_code": True}
            if HF_TOKEN:
                kwargs["token"] = HF_TOKEN
            self._model = SentenceTransformer(model_id, **kwargs)
            self._model.save(EMBEDDING_MODEL_PATH)
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


text_embedder = TextEmbedder()