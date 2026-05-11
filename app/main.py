import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import v1_router
from .core.log_config import setup_logging
from .infrastructure.graphdb_writer import ensure_ontology_loaded
from .infrastructure.ml.text_embedder import get_text_embedder
from .infrastructure.ml.captioner import get_captioner

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Ontology (existing)
    try:
        ensure_ontology_loaded()
    except Exception as e:
        logger.warning("[STARTUP] Ontology loading failed (GraphDB may not be ready yet): %s", e)

    # 2. Pre-load ML models in thread pool (port is already bound)
    # Note: rerank_embedder uses OpenRouter API, no local model to load
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=2) as pool:
        await asyncio.gather(
            loop.run_in_executor(pool, get_text_embedder),
            loop.run_in_executor(pool, get_captioner),
            return_exceptions=True,
        )
    logger.info("[STARTUP] ML models loaded (text embedder, captioner)")

    yield


app = FastAPI(title="KI-4-KMU Ingestion API", lifespan=lifespan)
app.include_router(v1_router)