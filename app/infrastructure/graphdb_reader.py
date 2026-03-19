import logging
import os
from urllib.parse import quote
from SPARQLWrapper import SPARQLWrapper, JSON, DIGEST

from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS

logger = logging.getLogger(__name__)


def _get_sparql_client() -> SPARQLWrapper:
    endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    sparql = SPARQLWrapper(endpoint)
    sparql.setReturnFormat(JSON)
    user = os.getenv("GRAPHDB_USER")
    password = os.getenv("GRAPHDB_PASSWORD")
    if user and password:
        sparql.setHTTPAuth(DIGEST)
        sparql.setCredentials(user, password)
    return sparql


_SPARQL_READ = _get_sparql_client()


def _uri(local: str) -> str:
    return f"pi:{quote(str(local), safe='')}"


def get_entities_from_chunk(chunk_id: str) -> list[dict]:
    """
    Query all entities that have pi:mentionedIn pointing to the given chunk.
    Returns a list of dicts with keys: uri, label, type
    """
    chunk_uri = _uri(chunk_id)
    query = f"""
{PREFIXES}
SELECT ?entity ?label ?type WHERE {{
    ?entity pi:mentionedIn {chunk_uri} .
    ?entity rdfs:label ?label .
    ?entity rdf:type ?type .
}}
"""
    try:
        _SPARQL_READ.setQuery(query)
        results = _SPARQL_READ.query().convert()
        entities = []
        for row in results.get("results", {}).get("bindings", []):
            entities.append({
                "uri": row["entity"]["value"],
                "label": row["label"]["value"],
                "type": row["type"]["value"],
            })
        return entities
    except Exception as e:
        logger.warning("[READER] Failed to get entities for chunk %s: %s", chunk_id, e)
        return []


def get_related_chunks_from_entities(
    entity_uris: list[str],
    exclude_chunk_id: str,
    limit: int,
) -> list[dict]:
    """
    Given a list of entity URIs, find all other Chunk nodes that those entities
    are mentioned in, excluding the seed chunk.
    Returns a list of dicts with keys: chunk_id, text
    """
    if not entity_uris:
        return []

    # Build VALUES clause for entity URIs
    entity_values = " ".join(f'"{uri}"' for uri in entity_uris)
    exclude_uri = _uri(exclude_chunk_id)

    query = f"""
{PREFIXES}
SELECT DISTINCT ?chunk ?text WHERE {{
    ?entity pi:mentionedIn ?chunk .
    ?chunk rdf:type pi:Chunk .
    ?chunk rdfs:label ?chunk_id .
    ?chunk pi:text ?text .
    FILTER (?chunk != {exclude_uri})
    VALUES ?entity {{ {entity_values} }}
}}
LIMIT {limit}
"""
    try:
        _SPARQL_READ.setQuery(query)
        results = _SPARQL_READ.query().convert()
        chunks = []
        for row in results.get("results", {}).get("bindings", []):
            # Extract chunk_id from the full URI (e.g., pi:doc-id_chunk_0 -> doc-id_chunk_0)
            chunk_uri = row["chunk"]["value"]
            chunk_id = chunk_uri.replace("pi:", "")
            chunks.append({
                "chunk_id": chunk_id,
                "text": row["text"]["value"],
            })
        return chunks
    except Exception as e:
        logger.warning("[READER] Failed to get related chunks: %s", e)
        return []
