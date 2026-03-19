import dataclasses
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import langextract as lx

from dotenv import load_dotenv
from examples_manager import _default_examples

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY     = os.environ["LANGEXTRACT_API_KEY"]
MODEL_ID    = os.environ["LANGEXTRACT_MODEL_ID"]
PROMPT_PATH = os.environ["LANGEXTRACT_PROMPT_PATH"]
BASE_URL    = os.environ.get("LANGEXTRACT_BASE_URL")

MAX_CHAR_BUFFER = 10_000_000

def _load_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()

@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_prompt()
    logger.info("LangExtract service ready — model=%s  base_url=%s", MODEL_ID, BASE_URL or "<openai default>")
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
            max_char_buffer=MAX_CHAR_BUFFER,
            show_progress=False,
            fence_output=True,
            use_schema_constraints=False,
        )
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    docs = result if isinstance(result, list) else [result]
    extractions = [
        dataclasses.asdict(ann)
        for doc in docs
        for ann in (doc.extractions or [])
        if ann is not None
    ]
    return ExtractResponse(extractions=extractions)

@app.get("/health")
def health():
    return {"status": "ok"}
