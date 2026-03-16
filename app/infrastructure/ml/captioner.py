from app.core.config import LMSTUDIO_URL, LMSTUDIO_MODEL, CAPTION_MAX_TOKENS, CAPTIONER_PROMPT_PATH
from app.utils.files import read_file, image_to_b64
from openai import OpenAI
from PIL import Image

class Captioner:
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
                            "text": read_file(CAPTIONER_PROMPT_PATH),
                        },
                    ],
                }
            ],
            max_tokens=self._max_tokens,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()

captioner = Captioner()