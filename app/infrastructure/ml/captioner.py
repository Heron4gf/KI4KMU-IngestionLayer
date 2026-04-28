from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.core.config import CAPTIONING_AI_BASE_URL, CAPTIONING_AI_MODEL, CAPTIONING_AI_API_KEY, CAPTION_MAX_TOKENS, CAPTIONER_PROMPT_PATH
from app.utils.files import read_file, image_to_b64
from PIL import Image

CAPTIONING_PROMPT = read_file(CAPTIONER_PROMPT_PATH)


class Captioner:
    def __init__(
        self,
        base_url: str = CAPTIONING_AI_BASE_URL,
        model: str = CAPTIONING_AI_MODEL,
        api_key: str = CAPTIONING_AI_API_KEY,
        max_tokens: int = CAPTION_MAX_TOKENS,
    ):
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=0.1,
        )

    def caption(self, image: Image.Image) -> str:
        b64 = image_to_b64(image)
        response = self._llm.invoke([
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": CAPTIONING_PROMPT},
            ])
        ])
        return response.content.strip()


captioner = Captioner()
