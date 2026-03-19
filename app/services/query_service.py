import logging
from typing import List

from app.models.api_models import QueryResultItem
from app.infrastructure.chroma_repository import semantic_search
from app.infrastructure.graphdb_reader import (
    get_entities_from_chunk,
    get_related_chunks_from_entities,
)

logger = logging.getLogger(__name__)


def hybrid_search(
    query: str,
    max_vector_results: int = 3,
    max_graph_results: int = 2,
    max_results_total: int = 5,
) -> List[QueryResultItem]:
    """
    Perform a hybrid search combining vector similarity and graph traversal.
    
    1. Vector search in ChromaDB
    2. Graph traversal via entities to find related chunks
    3. Merge and deduplicate results
    """
    # Step 1: Vector search
    vector_results = semantic_search(query, top_k=max_vector_results)
    logger.info("[QUERY] Vector search returned %d results", len(vector_results))
    
    if not vector_results:
        return []
    
    # Collect all entity URIs from vector results
    all_entity_uris: List[str] = []
    for result in vector_results:
        entities = get_entities_from_chunk(result.id)
        all_entity_uris.extend([e["uri"] for e in entities])
    
    # Deduplicate entity URIs
    all_entity_uris = list(set(all_entity_uris))
    logger.info("[QUERY] Found %d unique entities from vector results", len(all_entity_uris))
    
    # Step 2: Graph traversal - find related chunks
    graph_results: List[QueryResultItem] = []
    
    for rank, result in enumerate(vector_results):
        # Get related chunks for each seed chunk's entities
        related_chunks = get_related_chunks_from_entities(
            entity_uris=all_entity_uris,
            exclude_chunk_id=result.id,
            limit=max_graph_results,
        )
        
        for chunk_idx, chunk_data in enumerate(related_chunks):
            # Simple score: 1.0 / (1.0 + rank_position)
            # rank_position combines the vector result rank and the graph traversal position
            rank_position = rank * max_graph_results + chunk_idx + 1
            graph_score = 1.0 / (1.0 + rank_position)
            
            item = QueryResultItem(
                id=chunk_data["chunk_id"],
                text=chunk_data["text"],
                score=graph_score,
                metadata={"chunk_id": chunk_data["chunk_id"]},
                source="graph",
            )
            graph_results.append(item)
    
    logger.info("[QUERY] Graph traversal returned %d results", len(graph_results))
    
    # Step 3: Deduplicate - keep vector results if chunk_id matches
    vector_chunk_ids = {r.id for r in vector_results}
    deduplicated_graph = [
        r for r in graph_results
        if r.id not in vector_chunk_ids
    ]
    
    # Step 4: Merge and sort by score
    # Vector results keep their embedding distance score (lower is better for Chroma)
    # Graph results use the calculated graph_score (higher is better)
    # To make them comparable: convert Chroma distance to similarity (1 - distance)
    for r in vector_results:
        r.score = 1.0 - r.score  # Convert distance to similarity
    
    merged_results = vector_results + deduplicated_graph
    merged_results.sort(key=lambda x: x.score, reverse=True)
    
    # Step 5: Cap at max_results_total
    final_results = merged_results[:max_results_total]
    
    logger.info(
        "[QUERY] Hybrid search complete: %d vector, %d graph (after dedup), %d final",
        len(vector_results),
        len(deduplicated_graph),
        len(final_results),
    )
    
    return final_results
