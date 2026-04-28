import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import v1_router
from .core.log_config import setup_logging
from .infrastructure.graphdb_writer import ensure_ontology_loaded

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_ontology_loaded()
    except Exception as e:
        logger.warning("[STARTUP] Ontology loading failed (GraphDB may not be ready yet): %s", e)
    yield


app = FastAPI(title="KI-4-KMU Ingestion API", lifespan=lifespan)
app.include_router(v1_router)