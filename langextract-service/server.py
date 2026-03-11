import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import langextract as lx
from langextract import factory

logger = logging.getLogger(__name__)

# ── Config from env ───────────────────────────────────────────────────────────
BASE_URL    = os.environ["LANGEXTRACT_BASE_URL"]      # es. http://lmstudio:1234/v1
API_KEY     = os.getenv("LANGEXTRACT_API_KEY", "lm-studio")
MODEL_ID    = os.environ["LANGEXTRACT_MODEL_ID"]      # es. openai/gpt-4o
PROMPT_PATH = os.environ["LANGEXTRACT_PROMPT_PATH"]   # es. /prompts/extract.txt

# Disabilita chunking: passa l'intero testo in un unico "chunk"
MAX_CHAR_BUFFER = 10000000


def _load_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eager check at startup
    _load_prompt()
    logger.info("LangExtract service ready — model=%s base_url=%s", MODEL_ID, BASE_URL)
    yield


app = FastAPI(title="LangExtract Service", lifespan=lifespan)


# ── Request / Response ────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    text: str
    examples: list[dict] = []          # opzionale: lista di ExampleData serializzati


class ExtractResponse(BaseModel):
    extractions: list[dict]


# ── Endpoint ──────────────────────────────────────────────────────────────────
@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    prompt = _load_prompt()

    config = factory.ModelConfig(
        model_id=MODEL_ID,
        provider_kwargs={
            "api_key": API_KEY,
            "base_url": BASE_URL,
        },
    )

    try:
        result = lx.extract(
            text_or_documents=req.text,
            prompt_description=prompt,
            examples=req.examples or _default_examples(),
            config=config,
            max_char_buffer=MAX_CHAR_BUFFER,   # chunking interno disattivato
            show_progress=False,
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
    # Placeholder: senza esempi langextract solleva ValueError.
    # Sostituisci con i tuoi ExampleData reali, oppure accettali via API.
    from langextract.core.data import ExampleData, Extraction
    return [
        ExampleData(
            text="Apple Inc. was founded by Steve Jobs.",
            extractions=[Extraction(name="Steve Jobs", label="PERSON")],
        )
    ]
