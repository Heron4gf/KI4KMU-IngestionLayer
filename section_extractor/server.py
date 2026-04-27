import json
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai import OpenAI
from dotenv import load_dotenv

from models import ExtractRequest, SectionExtractionResponse

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.environ["LANGEXTRACT_API_KEY"]
MODEL_ID = os.environ["LANGEXTRACT_MODEL_ID"]
BASE_URL = os.environ.get("LANGEXTRACT_BASE_URL")  # None = default OpenAI
PROMPT_PATH = os.environ.get("LANGEXTRACT_PROMPT_PATH", "/prompts/section_extract.md")


def _load_system_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()


client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_system_prompt()
    logger.info(
        "Section Extractor service ready — model=%s  base_url=%s",
        MODEL_ID,
        BASE_URL or "<openai default>",
    )
    yield


app = FastAPI(title="Section Extractor Service", lifespan=lifespan)


@app.post("/extract-sections", response_model=SectionExtractionResponse)
def extract_sections(req: ExtractRequest):
    if not req.text or not req.text.strip():
        return SectionExtractionResponse(sections=[])

    system_prompt = _load_system_prompt()

    # Primary path: try structured output via parse()
    try:
        response = client.beta.chat.completions.parse(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.text},
            ],
            response_format=SectionExtractionResponse,
        )
        result: SectionExtractionResponse = response.choices[0].message.parsed
        if result is not None:
            return result
    except (AttributeError, NotImplementedError):
        # parse() not supported by this provider — fall back below
        logger.info("Structured output parse() not available, falling back to json_object mode")
    except Exception as e:
        logger.warning("Structured output parse() failed, falling back: %s", e)

    # Fallback path: json_object mode + manual validation
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.text},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        result = SectionExtractionResponse.model_validate_json(content)
        return result
    except Exception as e:
        logger.warning("Section extraction fallback failed: %s — returning empty", e)
        return SectionExtractionResponse(sections=[])


@app.get("/health")
def health():
    return {"status": "ok"}