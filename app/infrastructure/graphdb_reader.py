import logging
import os
from typing import List

from SPARQLWrapper import SPARQLWrapper, JSON, DIGEST
from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS
from app.infrastructure.sparql import load_and_parse

logger = logging.getLogger(__name__)

_SPARQL_READ: SPARQLWrapper | None = None


def _get_read_client() -> SPARQLWrapper:
    global _SPARQL_READ
    if _SPARQL_READ is None:
        endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
        sparql = SPARQLWrapper(endpoint)
        sparql.setReturnFormat(JSON)
        user = os.getenv("GRAPHDB_USER")
        password = os.getenv("GRAPHDB_PASSWORD")
        if user and password:
            sparql.setHTTPAuth(DIGEST)
            sparql.setCredentials(user, password)
        _SPARQL_READ = sparql
    return _SPARQL_READ


def _uri(local: str) -> str:
    return f"<{BASE_NS}{local}>"


def _sparql_str(value: str) -> str:
    """Escape a string value for safe inline use as a SPARQL plain literal."""
    escaped = (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _execute_and_parse(query: str) -> list[dict]:
    try:
        client = _get_read_client()
        client.setQuery(query)
        results = client.query().convert()
        return results.get("results", {}).get("bindings", [])
    except Exception as e:
        logger.warning("[READER] SPARQL query failed: %s", e)
        return []


def get_chunks_for_document(document_id: str) -> list[dict]:
    doc_uri = f"<{BASE_NS}doc_{document_id}>"
    query = f"""
{PREFIXES}
SELECT ?chunk ?text ?index WHERE {{
    ?chunk ki4kmu:belongsTo {doc_uri} .
    ?chunk rdf:type ki4kmu:Chunk .
    ?chunk ki4kmu:text ?text .
    ?chunk ki4kmu:chunk_index ?index .
}}
ORDER BY ?index
"""
    bindings = _execute_and_parse(query)
    chunks = []
    for row in bindings:
        chunk_uri = row["chunk"]["value"]
        chunk_id = chunk_uri.replace(BASE_NS, "")
        chunks.append({
            "chunk_id": chunk_id,
            "text": row["text"]["value"],
            "chunk_index": int(row["index"]["value"]),
        })
    return chunks


def get_chunks_for_section(section_id: str) -> list[dict]:
    section_uri = _uri(section_id)
    query = f"""
{PREFIXES}
SELECT ?chunk ?text WHERE {{
    {section_uri} ki4kmu:isContained ?chunk .
    ?chunk rdf:type ki4kmu:Chunk .
    ?chunk ki4kmu:text ?text .
}}
"""
    bindings = _execute_and_parse(query)
    chunks = []
    for row in bindings:
        chunk_uri = row["chunk"]["value"]
        chunk_id = chunk_uri.replace(BASE_NS, "")
        chunks.append({
            "chunk_id": chunk_id,
            "text": row["text"]["value"],
        })
    return chunks


def get_section_for_chunk(chunk_id: str) -> str | None:
    chunk_uri = _uri(chunk_id)
    query = f"""
{PREFIXES}
SELECT ?section WHERE {{
    ?section ki4kmu:isContained {chunk_uri} .
    ?section rdf:type ki4kmu:Section .
}}
LIMIT 1
"""
    bindings = _execute_and_parse(query)
    if bindings:
        section_uri = bindings[0]["section"]["value"]
        return section_uri.replace(BASE_NS, "")
    return None


def search_chunks_by_tags(keywords: List[str]) -> List[dict]:
    all_chunks = []
    seen = set()
    for keyword in keywords:
        query = load_and_parse(
            "search_tags.sparql",
            PREFIXES=PREFIXES,
            keyword_sparql=_sparql_str(keyword),
        )
        bindings = _execute_and_parse(query)
        for row in bindings:
            chunk_uri = row["chunk"]["value"]
            chunk_id = chunk_uri.replace(BASE_NS, "")
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            all_chunks.append({
                "chunk_id": chunk_id,
                "text": row["text"]["value"],
                "chunk_index": int(row["index"]["value"]),
                "section_id": row["section"]["value"].replace(BASE_NS, ""),
            })
    return all_chunks


def search_chunks_by_keyphrases(keywords: List[str]) -> List[dict]:
    all_chunks = []
    seen = set()
    for keyword in keywords:
        query = load_and_parse(
            "search_keyphrases.sparql",
            PREFIXES=PREFIXES,
            keyword_sparql=_sparql_str(keyword),
        )
        bindings = _execute_and_parse(query)
        for row in bindings:
            chunk_uri = row["chunk"]["value"]
            chunk_id = chunk_uri.replace(BASE_NS, "")
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            all_chunks.append({
                "chunk_id": chunk_id,
                "text": row["text"]["value"],
                "chunk_index": int(row["index"]["value"]),
                "section_id": row["section"]["value"].replace(BASE_NS, ""),
            })
    return all_chunks
