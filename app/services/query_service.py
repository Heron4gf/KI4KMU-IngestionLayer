import asyncio
import logging
from typing import List

from langfuse import observe

from app.models.api_models import QueryResultItem
from app.infrastructure.chroma_repository import semantic_search
from app.infrastructure.graphdb_reader import (
    get_chunks_for_section,
    search_chunks_by_concepts,
    search_chunks_by_keyphrases,
    get_related_chunks_via_concepts,
    get_related_chunks_via_cooccurrence,
)
from app.infrastructure.ml.rerank_embedder import get_rerank_embedder
from app.utils.text_normalization import extract_keyphrases

logger = logging.getLogger(__name__)

# Each retrieval arm fetches up to this many candidates independently.
# The full pool (up to 3x this across all arms) is then reranked down to top_k.
# 50-100 is the range recommended by recent literature on reranking pipelines.
_CANDIDATE_POOL_SIZE = 64


async def _vector_search_sections(query: str) -> List[QueryResultItem]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, semantic_search, query, _CANDIDATE_POOL_SIZE
    )


async def _graph_keyword_search_chunks(query: str) -> List[dict]:
    keywords = extract_keyphrases(query)
    if not keywords:
        return []

    loop = asyncio.get_event_loop()
    concept_chunks = await loop.run_in_executor(None, search_chunks_by_concepts, keywords)
    kp_chunks = await loop.run_in_executor(None, search_chunks_by_keyphrases, keywords)

    seen = set()
    all_chunks = []
    for chunk in concept_chunks + kp_chunks:
        cid = chunk["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        all_chunks.append(chunk)
        if len(all_chunks) >= _CANDIDATE_POOL_SIZE:
            break

    return all_chunks


async def _graph_traversal_expand_chunks(
    vector_results: List[QueryResultItem],
) -> List[dict]:
    """
    Graph traversal expansion: for each section returned by vector search,
    find structurally related chunks via concept hops and concept co-occurrence.

    - 2-hop: seed_section -> shared Concept <- other_section -> chunk
    - 3-hop: seed_section -> Concept_A -[coOccursWith]-> Concept_B <- other_section -> chunk
    """
    loop = asyncio.get_event_loop()
    seen_sections: set[str] = set()
    seen_chunks: set[str] = set()
    expanded: List[dict] = []

    for result in vector_results:
        section_id = result.metadata.get("section_uuid") or result.id
        if not section_id or section_id in seen_sections:
            continue
        seen_sections.add(section_id)

        try:
            concept_chunks, cooc_chunks = await asyncio.gather(
                loop.run_in_executor(None, get_related_chunks_via_concepts, section_id),
                loop.run_in_executor(None, get_related_chunks_via_cooccurrence, section_id),
            )
        except Exception as e:
            logger.warning("[QUERY] Graph traversal failed for section %s: %s", section_id, e)
            continue

        for chunk in concept_chunks + cooc_chunks:
            cid = chunk["chunk_id"]
            if cid in seen_chunks:
                continue
            seen_chunks.add(cid)
            expanded.append(chunk)
            if len(expanded) >= _CANDIDATE_POOL_SIZE:
                return expanded

    return expanded


async def _resolve_vector_sections_to_chunks(
    vector_results: List[QueryResultItem],
) -> List[dict]:
    all_chunks = []
    seen_sections = set()
    seen_chunks = set()

    for result in vector_results:
        section_id = result.metadata.get("section_uuid") or result.id
        if not section_id or section_id in seen_sections:
            continue
        seen_sections.add(section_id)

        try:
            chunks = get_chunks_for_section(section_id)
        except Exception as e:
            logger.warning("[QUERY] Failed to get chunks for section %s: %s", section_id, e)
            continue

        for chunk in chunks:
            cid = chunk["chunk_id"]
            if cid in seen_chunks:
                continue
            seen_chunks.add(cid)
            all_chunks.append({
                "chunk_id": cid,
                "text": chunk["text"],
                "section_id": section_id,
            })

    return all_chunks


def _merge_chunks(*chunk_lists: List[dict]) -> List[dict]:
    seen = set()
    merged = []
    for chunk in (c for lst in chunk_lists for c in lst):
        cid = chunk["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        merged.append(chunk)
    return merged


async def _rerank_chunks(query: str, chunks: List[dict], top_k: int) -> List[QueryResultItem]:
    if not chunks:
        return []

    texts = [c["text"] for c in chunks]
    reranker = get_rerank_embedder()

    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(
        None, lambda: asyncio.run(reranker.rerank(query, texts, top_n=len(texts)))
    )

    scored = sorted(
        [{**chunk, "score": score} for chunk, score in zip(chunks, scores)],
        key=lambda x: x["score"],
        reverse=True,
    )

    return [
        QueryResultItem(
            id=item["chunk_id"],
            text=item["text"],
            score=item["score"],
            metadata={
                "chunk_id": item["chunk_id"],
                "section_id": item.get("section_id", ""),
            },
        )
        for item in scored[:top_k]
    ]


@observe(name="hybrid_search", as_type="retriever", capture_input=True, capture_output=True)
async def hybrid_search(
    query: str,
    max_vector_results: int = 3,
    max_graph_results: int = 2,
    max_results_total: int = 5,
) -> List[QueryResultItem]:
    vector_task = _vector_search_sections(query)
    graph_task = _graph_keyword_search_chunks(query)

    vector_results, graph_chunks = await asyncio.gather(vector_task, graph_task)
    logger.info(
        "[QUERY] Vector sections: %d, Graph keyword chunks: %d",
        len(vector_results), len(graph_chunks),
    )

    vector_chunks, traversal_chunks = await asyncio.gather(
        _resolve_vector_sections_to_chunks(vector_results),
        _graph_traversal_expand_chunks(vector_results),
    )
    logger.info(
        "[QUERY] Vector resolved: %d chunks, Graph traversal expanded: %d chunks",
        len(vector_chunks), len(traversal_chunks),
    )

    all_chunks = _merge_chunks(vector_chunks, graph_chunks, traversal_chunks)
    logger.info("[QUERY] Merged unique chunks: %d", len(all_chunks))

    if not all_chunks:
        return []

    final_results = await _rerank_chunks(query, all_chunks, max_results_total)
    logger.info(
        "[QUERY] Hybrid search complete: %d vector, %d graph keyword, %d traversal, %d final",
        len(vector_chunks), len(graph_chunks), len(traversal_chunks), len(final_results),
    )

    return final_results
