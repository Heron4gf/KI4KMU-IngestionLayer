from typing import Any, Dict, List, Literal
from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    max_vector_results: int = 3
    max_graph_results: int = 2
    max_results_total: int = 5


class QueryResultItem(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]
    source: Literal["vector", "graph"] = "vector"


class QueryResponse(BaseModel):
    query: str
    results: List[QueryResultItem]
