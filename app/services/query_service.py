import logging
from typing import List

from app.models.api_models import QueryResultItem
from app.infrastructure.chroma_repository import semantic_search
from app.infrastructure.graphdb_reader import get_section_for_chunk, get_chunks_for_section

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
    2. For each vector result, look up its section in GraphDB
    3. Find other chunks in the same section (graph expansion)
    4. Merge and deduplicate results
    """
    # Step 1: Vector search
    vector_results = semantic_search(query, top_k=max_vector_results)
    logger.info("[QUERY] Vector search returned %d results", len(vector_results))

    if not vector_results:
        return []

    # Step 2: Graph expansion — find sibling chunks via section containment
    vector_chunk_ids = {r.id for r in vector_results}
    graph_results: List[QueryResultItem] = []
    seen_section_ids: set[str] = set()

    for result in vector_results:
        try:
            section_id = get_section_for_chunk(result.id)
        except Exception as e:
            logger.warning("[QUERY] Graph lookup failed for chunk %s: %s", result.id, e)
            continue

        if not section_id or section_id in seen_section_ids:
            continue
        seen_section_ids.add(section_id)

        try:
            section_chunks = get_chunks_for_section(section_id)
        except Exception as e:
            logger.warning("[QUERY] Section chunks lookup failed for %s: %s", section_id, e)
            continue

        for chunk_data in section_chunks:
            if chunk_data["chunk_id"] in vector_chunk_ids:
                continue  # Skip seeds
            rank_position = len(graph_results) + 1
            graph_score = 1.0 / (1.0 + rank_position)
            item = QueryResultItem(
                id=chunk_data["chunk_id"],
                text=chunk_data["text"],
                score=graph_score,
                metadata={"chunk_id": chunk_data["chunk_id"], "section_id": section_id},
                source="graph",
            )
            graph_results.append(item)

            if len(graph_results) >= max_graph_results:
                break
        if len(graph_results) >= max_graph_results:
            break

    logger.info("[QUERY] Graph traversal returned %d results", len(graph_results))

    # Step 3: Convert Chroma L2 distance to similarity
    for r in vector_results:
        r.score = 1.0 / (1.0 + r.score)

    # Step 4: Merge and sort by score
    merged_results = vector_results + graph_results
    merged_results.sort(key=lambda x: x.score, reverse=True)

    # Step 5: Cap at max_results_total
    final_results = merged_results[:max_results_total]

    logger.info(
        "[QUERY] Hybrid search complete: %d vector, %d graph, %d final",
        len(vector_results),
        len(graph_results),
        len(final_results),
    )

    return final_results