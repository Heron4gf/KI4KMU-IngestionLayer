import logging
import os
from typing import List

import torch
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

from app.core.config import TEXT_MODEL, HF_TOKEN, EMBEDDING_MODEL_PATH

logger = logging.getLogger(__name__)


class TextEmbedder:
    def __init__(self, model_id: str = TEXT_MODEL):
        if not (os.path.isdir(EMBEDDING_MODEL_PATH) and os.listdir(EMBEDDING_MODEL_PATH)):
            logger.info(f"Downloading model {model_id} to {EMBEDDING_MODEL_PATH}")
            snapshot_download(
                repo_id=model_id,
                local_dir=EMBEDDING_MODEL_PATH,
                token=HF_TOKEN or None,
            )

        logger.info(f"Loading model from {EMBEDDING_MODEL_PATH}")
        self._model = SentenceTransformer(EMBEDDING_MODEL_PATH, trust_remote_code=True)
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
