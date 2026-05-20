import os
import uuid
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models import ExtractRequest, SectionExtraction, SectionExtractionWithUUID, SectionExtractionResponse

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("EXTRACTOR_API_KEY")
MODEL_ID = os.getenv("EXTRACTOR_MODEL_ID")
BASE_URL = os.getenv("EXTRACTOR_BASE_URL")
PROMPT_PATH = os.getenv("EXTRACTOR_PROMPT_PATH", "/prompts/extract.md")


def _load_system_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()


# LangChain setup with structured output - uses clean model without UUID
llm = ChatOpenAI(
    model=MODEL_ID,
    api_key=API_KEY,
    base_url=BASE_URL,
)
structured_chain = llm.with_structured_output(SectionExtractionResponse, include_raw=True)


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

    try:
        result = structured_chain.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=req.text),
        ])
        if result.get("parsed") is not None:
            # Convert LLM output to response with UUIDs
            llm_sections = result["parsed"].sections
            sections_with_uuid = [
                SectionExtractionWithUUID(
                    section_id=s.section_id,
                    label=s.label,
                    texts=s.texts,
                    concepts=s.concepts,
                    uuid=str(uuid.uuid4()),
                )
                for s in llm_sections
            ]
            return SectionExtractionResponse(sections=sections_with_uuid)
    except Exception as e:
        logger.warning("Section extraction failed: %s — returning empty", e)

    return SectionExtractionResponse(sections=[])


@app.get("/health")
def health():
    return {"status": "ok"}
