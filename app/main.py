from fastapi import FastAPI

from .api.routes import v1_router
from .core.log_config import setup_logging

setup_logging()

app = FastAPI(title="PDF Ingestion API")
app.include_router(v1_router)
