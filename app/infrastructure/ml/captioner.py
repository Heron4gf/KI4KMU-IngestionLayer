import logging
import os
import threading

import torch
from huggingface_hub import snapshot_download
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

from app.core.config import (
    USE_LOCAL_CAPTIONER,
    CAPTIONER_MODEL_PATH,
    FLORENCE2_MODEL_ID,
    HF_TOKEN,
    CAPTIONING_AI_BASE_URL,
    CAPTIONING_AI_MODEL,
    CAPTIONING_AI_API_KEY,
    CAPTION_MAX_TOKENS,
    CAPTIONER_PROMPT_PATH,
)
from app.utils.files import read_file, image_to_b64

logger = logging.getLogger(__name__)

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def _model_is_cached(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, f)) for f in WEIGHT_FILES)


class LocalCaptioner:
    """Local captioner using Florence-2 via transformers."""

    def __init__(self):
        if not _model_is_cached(CAPTIONER_MODEL_PATH):
            logger.info("Downloading Florence-2 model %s to %s", FLORENCE2_MODEL_ID, CAPTIONER_MODEL_PATH)
            snapshot_download(
                repo_id=FLORENCE2_MODEL_ID,
                local_dir=CAPTIONER_MODEL_PATH,
                token=HF_TOKEN or None,
            )

        logger.info("Loading Florence-2 from %s", CAPTIONER_MODEL_PATH)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        self._device = device
        self._model = AutoModelForCausalLM.from_pretrained(
            CAPTIONER_MODEL_PATH,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(device)
        self._processor = AutoProcessor.from_pretrained(
            CAPTIONER_MODEL_PATH,
            trust_remote_code=True,
        )
        logger.info("Florence-2 ready on %s", device)

    def caption(self, image: Image.Image) -> str:
        task = "<MORE_DETAILED_CAPTION>"
        inputs = self._processor(text=task, images=image, return_tensors="pt").to(self._device)
        ids = self._model.generate(**inputs, max_new_tokens=256)
        raw = self._processor.batch_decode(ids, skip_special_tokens=False)[0]
        return self._processor.post_process_generation(
            raw, task=task, image_size=image.size
        )[task].strip()


class RemoteCaptioner:
    """Remote captioner using any OpenAI-compatible VLM via API."""

    def __init__(self):
        self._prompt = read_file(CAPTIONER_PROMPT_PATH)
        self._llm = ChatOpenAI(
            model=CAPTIONING_AI_MODEL,
            api_key=CAPTIONING_AI_API_KEY,
            base_url=CAPTIONING_AI_BASE_URL,
            max_tokens=CAPTION_MAX_TOKENS,
            temperature=0.1,
        )
        logger.info("Remote captioner ready (model=%s)", CAPTIONING_AI_MODEL)

    def caption(self, image: Image.Image) -> str:
        b64 = image_to_b64(image)
        response = self._llm.invoke([
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": self._prompt},
            ])
        ])
        return response.content.strip()


_instance: "LocalCaptioner | RemoteCaptioner | None" = None
_lock = threading.Lock()


def get_captioner() -> "LocalCaptioner | RemoteCaptioner":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                if USE_LOCAL_CAPTIONER:
                    logger.info("Using LOCAL captioner (Florence-2)")
                    _instance = LocalCaptioner()
                else:
                    logger.info("Using REMOTE captioner")
                    _instance = RemoteCaptioner()
    return _instance