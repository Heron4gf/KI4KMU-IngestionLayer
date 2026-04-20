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
    
    if not all_entity_uris:
        # No entities found, just return vector results
        return vector_results[:max_results_total]
    
    # Step 2: Graph traversal - find related chunks (once, excluding all seed chunks)
    seed_chunk_ids = [r.id for r in vector_results]
    all_exclude_ids = seed_chunk_ids  # Pass all to exclude in one query
    
    graph_results: List[QueryResultItem] = []
    
    # Call graph traversal once with all seed chunk IDs to exclude
    related_chunks = get_related_chunks_from_entities(
        entity_uris=all_entity_uris,
        exclude_chunk_ids=all_exclude_ids,
        limit=max_graph_results,
    )
    
    for chunk_idx, chunk_data in enumerate(related_chunks):
        # Simple score: 1.0 / (1.0 + rank_position)
        rank_position = chunk_idx + 1

        # TODO: let's recalculate the graph score with a proper formula
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
    # Vector results: convert Chroma L2 distance to similarity using 1/(1+distance)
    # Graph results: already using 1/(1+rank_position)
    for r in vector_results:
        r.score = 1.0 / (1.0 + r.score)  # Convert distance to similarity
    
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
