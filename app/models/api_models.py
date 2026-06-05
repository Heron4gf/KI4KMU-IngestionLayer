from typing import Any, Dict, List, Optional
from pydantic import BaseModel, model_validator


class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
    max_vector_results: int = 3
    max_graph_results: int = 2
    max_results_total: int = 5
    use_graph: bool = True

    @model_validator(mode="after")
    def apply_top_k(self) -> "QueryRequest":
        if self.top_k is not None:
            self.max_results_total = self.top_k
        return self


class QueryResultItem(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    query: str
    results: List[QueryResultItem]
