"""
ML Services module for machine learning inference.

This module contains ML-related services that are used by the business logic:
- Captioner: VLM-based image captioning

This separation ensures that:
1. Storage layer (chroma_manager) remains free of ML inference
2. ML services are centralized and reusable
3. Business logic (services) can orchestrate ML operations
"""

import logging
import os
from typing import Any

from PIL import Image
from openai import OpenAI

from utils import image_to_b64


logger = logging.getLogger(__name__)

LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://host.docker.internal:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "lmstudio-community/Qwen3.5-0.8B-GGUF")
CAPTION_MAX_TOKENS = int(os.getenv("CAPTION_MAX_TOKENS", "256"))


class Captioner:
    """
    Image captioning service using a Vision Language Model (VLM).
    
    This class provides VLM-based image captioning. It is used by the
    service layer to generate captions for extracted images.
    
    The storage layer does NOT use this class - captions must be
    pre-computed before storage.
    """
    def __init__(
        self,
        base_url: str = LMSTUDIO_URL,
        model: str = LMSTUDIO_MODEL,
        max_tokens: int = CAPTION_MAX_TOKENS,
    ):
        self._client = OpenAI(base_url=base_url, api_key="dummy")
        self._model = model
        self._max_tokens = max_tokens

    def caption(self, image: Image.Image) -> str:
        """
        Generate a caption for an image using the VLM.
        
        Args:
            image: PIL Image to caption
            
        Returns:
            Generated caption as a string
        """
        b64 = image_to_b64(image)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in detail. If it contains charts, tables, or diagrams, explain what they show.",
                        },
                    ],
                }
            ],
            max_tokens=self._max_tokens,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()


# Singleton instance for use across the application
captioner = Captioner()