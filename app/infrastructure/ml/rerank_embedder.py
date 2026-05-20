import logging
import os
import threading
from typing import List

import torch
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, AutoModelForCausalLM

from app.core.config import RERANK_MODEL, RERANKER_MODEL_PATH, HF_TOKEN

logger = logging.getLogger(__name__)

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")

_SYSTEM_PROMPT = (
    "Judge whether the following [document] is helpful for answering the [query]. "
    "Only reply with 'yes' or 'no'."
)


def _model_is_cached(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, f)) for f in WEIGHT_FILES)


def _format_input(tokenizer: AutoTokenizer, query: str, document: str) -> str:
    """Format a query-document pair using the Qwen3-Reranker instruction template."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"[query]: {query}\n[document]: {document}",
        },
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


class RerankEmbedder:
    """
    Local reranker using Qwen/Qwen3-Reranker-0.6B.

    Scores each (query, document) pair by computing the log-probability
    of the 'yes' token from the model's next-token distribution,
    following the official Qwen3-Reranker inference pattern.
    """

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
        self._model = AutoModelForCausalLM.from_pretrained(
            RERANKER_MODEL_PATH, torch_dtype=torch.float16
        )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)
        self._model.eval()

        # Resolve token IDs for 'yes' and 'no' once at init
        self._yes_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._no_id = self._tokenizer.convert_tokens_to_ids("no")
        logger.info(
            "Reranker ready on %s (yes_id=%d, no_id=%d)",
            self._device, self._yes_id, self._no_id,
        )

    @torch.inference_mode()
    def _score_batch(self, inputs: List[str]) -> List[float]:
        """
        Tokenize a batch of pre-formatted prompt strings and return
        the probability of the 'yes' token for each.
        """
        encoded = self._tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self._device)

        logits = self._model(**encoded).logits[:, -1, :]  # (batch, vocab)
        yes_no_logits = logits[:, [self._yes_id, self._no_id]]
        probs = torch.softmax(yes_no_logits, dim=-1)
        return probs[:, 0].tolist()  # probability of 'yes'

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[float]:
        """
        Score all documents against the query and return a relevance score
        list aligned to the original document order.
        top_n is accepted for API compatibility but all scores are returned;
        slicing is handled by the caller.
        """
        if not documents:
            return []

        inputs = [
            _format_input(self._tokenizer, query, doc) for doc in documents
        ]
        # Run synchronously — caller is responsible for wrapping in run_in_executor
        # if this is called from an async context with a large batch.
        scores = self._score_batch(inputs)
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