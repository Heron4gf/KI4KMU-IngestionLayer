from typing import Any, Dict, List
from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResultItem(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    query: str
    results: List[QueryResultItem]
