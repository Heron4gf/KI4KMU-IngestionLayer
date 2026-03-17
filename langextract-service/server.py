import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import langextract as lx

logger = logging.getLogger(__name__)

BASE_URL = os.environ["LANGEXTRACT_BASE_URL"]
API_KEY  = os.getenv("LANGEXTRACT_API_KEY", "lm-studio")
MODEL_ID = os.environ["LANGEXTRACT_MODEL_ID"]
PROMPT_PATH = os.environ["LANGEXTRACT_PROMPT_PATH"]

MAX_CHAR_BUFFER = 10_000_000


def _load_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_prompt()
    logger.info("LangExtract service ready — model=%s base_url=%s", MODEL_ID, BASE_URL)
    yield


app = FastAPI(title="LangExtract Service", lifespan=lifespan)


class ExtractRequest(BaseModel):
    text: str
    examples: list[dict] = []


class ExtractResponse(BaseModel):
    extractions: list[dict]


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    prompt = _load_prompt()

    try:
        result = lx.extract(
            text_or_documents=req.text,
            prompt_description=prompt,
            examples=req.examples or _default_examples(),
            model_id=MODEL_ID,
            api_key=API_KEY,
            base_url=BASE_URL,
            max_char_buffer=MAX_CHAR_BUFFER,
            show_progress=False,
            # Required for OpenAI-compatible providers:
            # schema constraints are not supported, fenced output must be used instead.
            fence_output=True,
            use_schema_constraints=False,
        )
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    docs = result if isinstance(result, list) else [result]
    extractions = [
        ann.__dict__ for doc in docs for ann in (doc.annotations or [])
    ]
    return ExtractResponse(extractions=extractions)


@app.get("/health")
def health():
    return {"status": "ok"}


def _default_examples():
    from langextract.core.data import ExampleData

    return [
        ExampleData(
            text=(
                "Der Data Scientist konzipiert ML-Modelle. "
                "Microsoft Copilot ist in Microsoft 365 integriert. "
                "Der AI Act der EU reguliert KI-Systeme nach Risikoniveau. "
                "Ohne Datenkompetenz keine KI-Kompetenz."
            ),
            extractions=[
                lx.data.Extraction(
                    extraction_class="rolle",
                    extraction_text="Data Scientist",
                    attributes={
                        "verantwortung": "Konzeption von ML-Modellen",
                    }
                ),
                lx.data.Extraction(
                    extraction_class="tool",
                    extraction_text="Microsoft Copilot",
                    attributes={
                        "anbieter": "Microsoft",
                        "einsatzbereich": "Tägliche Büroarbeit",
                    }
                ),
                lx.data.Extraction(
                    extraction_class="rahmenwerk",
                    extraction_text="AI Act",
                    attributes={
                        "herausgeber": "EU",
                        "zweck": "Regulierung von KI-Systemen",
                    }
                ),
                lx.data.Extraction(
                    extraction_class="konzept",
                    extraction_text="Datenkompetenz",
                    attributes={
                        "definition": "Grundvoraussetzung für KI-Kompetenz",
                    }
                ),
            ]
        )
    ]
