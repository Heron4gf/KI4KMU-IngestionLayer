import asyncio
import logging
from typing import List

from langfuse import observe

from app.models.api_models import QueryResultItem
from app.infrastructure.chroma_repository import semantic_search
from app.infrastructure.graphdb_reader import (
    get_chunks_for_section,
    search_chunks_by_tags,
    search_chunks_by_keyphrases,
)
from app.infrastructure.ml.rerank_embedder import get_rerank_embedder
from app.utils.text_normalization import extract_keyphrases

logger = logging.getLogger(__name__)

_VECTOR_FETCH_MULTIPLIER = 2
_GRAPH_FETCH_MULTIPLIER = 2


async def _vector_search_sections(query: str, top_k: int) -> List[QueryResultItem]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, semantic_search, query, top_k * _VECTOR_FETCH_MULTIPLIER
    )


async def _graph_keyword_search_chunks(query: str, top_k: int) -> List[dict]:
    keywords = extract_keyphrases(query)
    if not keywords:
        return []

    loop = asyncio.get_event_loop()
    tag_chunks = await loop.run_in_executor(None, search_chunks_by_tags, keywords)
    kp_chunks = await loop.run_in_executor(None, search_chunks_by_keyphrases, keywords)

    seen = set()
    all_chunks = []
    for chunk in tag_chunks + kp_chunks:
        cid = chunk["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        all_chunks.append(chunk)
        if len(all_chunks) >= top_k * _GRAPH_FETCH_MULTIPLIER:
            break

    return all_chunks


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
                "source": "vector",
            })

    return all_chunks


def _merge_chunks(vector_chunks: List[dict], graph_chunks: List[dict]) -> List[dict]:
    seen = set()
    merged = []
    for chunk in vector_chunks + graph_chunks:
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
    scores = await reranker.rerank(query, texts, top_n=len(texts))

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
                "source": item.get("source", "reranked"),
            },
            source=item.get("source", "reranked"),
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
    vector_task = _vector_search_sections(query, max_vector_results)
    graph_task = _graph_keyword_search_chunks(query, max_graph_results)

    vector_results, graph_chunks = await asyncio.gather(vector_task, graph_task)
    logger.info(
        "[QUERY] Vector sections: %d, Graph chunks: %d",
        len(vector_results), len(graph_chunks),
    )

    vector_chunks = await _resolve_vector_sections_to_chunks(vector_results)
    logger.info("[QUERY] Vector resolved to %d chunks", len(vector_chunks))

    all_chunks = _merge_chunks(vector_chunks, graph_chunks)
    logger.info("[QUERY] Merged unique chunks: %d", len(all_chunks))

    if not all_chunks:
        return []

    final_results = await _rerank_chunks(query, all_chunks, max_results_total)
    logger.info(
        "[QUERY] Hybrid search complete: %d vector chunks, %d graph chunks, %d final",
        len(vector_chunks), len(graph_chunks), len(final_results),
    )

    return final_results
