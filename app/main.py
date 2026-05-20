import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import v1_router
from .core.log_config import setup_logging
from .infrastructure.graphdb_writer import ensure_ontology_loaded
from .infrastructure.ml.text_embedder import get_text_embedder
from .infrastructure.ml.captioner import get_captioner
from .infrastructure.ml.rerank_embedder import get_rerank_embedder

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_ontology_loaded()
    except Exception as e:
        logger.warning("[STARTUP] Ontology loading failed (GraphDB may not be ready yet): %s", e)

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=3) as pool:
        await asyncio.gather(
            loop.run_in_executor(pool, get_text_embedder),
            loop.run_in_executor(pool, get_captioner),
            loop.run_in_executor(pool, get_rerank_embedder),
            return_exceptions=True,
        )
    logger.info("[STARTUP] ML models loaded (text embedder, captioner, reranker)")

    yield


app = FastAPI(title="KI-4-KMU Ingestion API", lifespan=lifespan)
app.include_router(v1_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
