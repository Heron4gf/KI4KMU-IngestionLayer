import os
import logging
from urllib.parse import quote
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST
from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES


logger = logging.getLogger(__name__)


def _get_sparql_client() -> SPARQLWrapper:
    endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}/statements"
    sparql = SPARQLWrapper(endpoint)
    sparql.setMethod(POST)
    sparql.setReturnFormat(JSON)

    user = os.getenv("GRAPHDB_USER")
    password = os.getenv("GRAPHDB_PASSWORD")
    if user and password:
        sparql.setHTTPAuth(DIGEST)
        sparql.setCredentials(user, password)

    return sparql


def _run_update(query: str) -> None:
    sparql = _get_sparql_client()
    sparql.setQuery(query)
    sparql.query()

def _uri(local: str) -> str:
    """Builds a full URI in the base namespace."""
    return f"pi:{quote(local, safe='')}"


def _literal(value) -> str:
    """Serializes a Python value to a typed SPARQL literal."""
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    if isinstance(value, float):
        return f'"{value}"^^xsd:decimal'
    # Default: plain string — escape quotes
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

def insert_chunk(chunk_id: str, metadata: dict) -> None:
    """
    Inserts a Chunk node into GraphDB with all key-value metadata as datatype properties.

    Triples created:
        pi:<chunk_id>  rdf:type          pi:Chunk
        pi:<chunk_id>  rdfs:label        "<chunk_id>"
        pi:<chunk_id>  pi:<key>          <typed literal>   (one per metadata entry)
    """
    chunk_uri = _uri(chunk_id)

    # Build one triple per metadata field
    meta_triples = "\n    ".join(
        f"{chunk_uri} {_uri(k)} {_literal(v)} ."
        for k, v in metadata.items()
        if v is not None
    )

    query = f"""
{PREFIXES}
INSERT DATA {{
    {chunk_uri} rdf:type pi:Chunk .
    {chunk_uri} rdfs:label "{chunk_id}" .
    {meta_triples}
}}
"""
    try:
        _run_update(query)
        logger.info("insert_chunk OK  chunk_id=%s  meta_keys=%s", chunk_id, list(metadata.keys()))
    except Exception as e:
        logger.error("insert_chunk FAILED  chunk_id=%s  error=%s", chunk_id, e)
        raise


def insert_entity(entity: str, chunk_id: str) -> None:
    """
    Inserts an Entity node and links it to a Chunk via pi:mentionedIn.

    Triples created:
        pi:<entity>    rdf:type          pi:Entity
        pi:<entity>    rdfs:label        "<entity>"
        pi:<entity>    pi:mentionedIn    pi:<chunk_id>
    """
    entity_uri = _uri(entity)
    chunk_uri  = _uri(chunk_id)

    query = f"""
{PREFIXES}
INSERT DATA {{
    {entity_uri} rdf:type       pi:Entity .
    {entity_uri} rdfs:label     "{entity}" .
    {entity_uri} pi:mentionedIn {chunk_uri} .
}}
"""
    try:
        _run_update(query)
        logger.info("insert_entity OK  entity=%s  chunk_id=%s", entity, chunk_id)
    except Exception as e:
        logger.error("insert_entity FAILED  entity=%s  chunk_id=%s  error=%s", entity, chunk_id, e)
        raise
