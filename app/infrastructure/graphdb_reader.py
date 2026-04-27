import logging
import os
from SPARQLWrapper import SPARQLWrapper, JSON, DIGEST
from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy SPARQL client — created on first use, not at import time
# ---------------------------------------------------------------------------

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


def _execute_and_parse(query: str) -> list[dict]:
    """Execute a SELECT query and return the bindings list."""
    try:
        client = _get_read_client()
        client.setQuery(query)
        results = client.query().convert()
        return results.get("results", {}).get("bindings", [])
    except Exception as e:
        logger.warning("[READER] SPARQL query failed: %s", e)
        return []


def get_chunks_for_document(document_id: str) -> list[dict]:
    """
    Retrieve all chunks belonging to a document via ki4kmu:belongsTo.
    Returns list of dicts with keys: chunk_id, text, chunk_index
    """
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
    """
    Retrieve all chunks in a section via ki4kmu:isContained.
    Returns list of dicts with keys: chunk_id, text
    """
    section_uri = _uri(section_id)
    query = f"""
{PREFIXES}
SELECT ?chunk ?text WHERE {{
    ?chunk ki4kmu:isContained {section_uri} .
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
    """
    Get the section_id that a chunk belongs to (if any).
    Returns section_id string or None.
    """
    chunk_uri = _uri(chunk_id)
    query = f"""
{PREFIXES}
SELECT ?section WHERE {{
    {chunk_uri} ki4kmu:isContained ?section .
    ?section rdf:type ki4kmu:Section .
}}
LIMIT 1
"""
    bindings = _execute_and_parse(query)
    if bindings:
        section_uri = bindings[0]["section"]["value"]
        return section_uri.replace(BASE_NS, "")
    return None