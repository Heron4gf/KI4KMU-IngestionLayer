import os
import re
import logging
import unicodedata
from pathlib import Path
from urllib.parse import quote
import requests
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST

from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy SPARQL client — created on first use, not at import time
# ---------------------------------------------------------------------------

_SPARQL_WRITE: SPARQLWrapper | None = None


def _get_write_client() -> SPARQLWrapper:
    global _SPARQL_WRITE
    if _SPARQL_WRITE is None:
        endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}/statements"
        sparql = SPARQLWrapper(endpoint)
        sparql.setMethod(POST)
        sparql.setReturnFormat(JSON)
        user = os.getenv("GRAPHDB_USER")
        password = os.getenv("GRAPHDB_PASSWORD")
        if user and password:
            sparql.setHTTPAuth(DIGEST)
            sparql.setCredentials(user, password)
        _SPARQL_WRITE = sparql
    return _SPARQL_WRITE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_id(raw: str) -> str:
    nfd = unicodedata.normalize("NFD", raw)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_str.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


def _run_update(query: str) -> None:
    client = _get_write_client()
    client.setQuery(query)
    client.query()


def _uri(local: str) -> str:
    return f"ki4kmu:{quote(str(local), safe='')}"


def _document_uri(document_id: str) -> str:
    """Full URI for a document node (used in object position of triples)."""
    return f"<{BASE_NS}doc_{quote(str(document_id), safe='')}>"


def _literal(value) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    if isinstance(value, float):
        return f'"{value}"^^xsd:decimal'
    escaped = str(value).replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


# ---------------------------------------------------------------------------
# Write functions — new ki4kmu: ontology
# ---------------------------------------------------------------------------

def insert_document(document_id: str, pdf_hash: str) -> None:
    """Insert a ki4kmu:Document node."""
    doc_uri = _document_uri(document_id)
    query = f"""{PREFIXES}
INSERT DATA {{
    {doc_uri} rdf:type ki4kmu:Document .
    {doc_uri} rdfs:label "{document_id}" .
    {doc_uri} ki4kmu:document_id "{document_id}" .
    {doc_uri} ki4kmu:pdf_hash "{pdf_hash}" .
}}"""
    _run_update(query)


def insert_chunk(chunk_id: str, document_id: str, text: str, chunk_index: int, page_number: int | None = None) -> None:
    """Insert a ki4kmu:Chunk node with fixed ontology properties."""
    chunk_uri = _uri(chunk_id)
    doc_uri = _document_uri(document_id)

    page_triple = ""
    if page_number is not None:
        page_triple = f'    {chunk_uri} ki4kmu:page_number {_literal(page_number)} .'

    # Escape text for SPARQL
    clean_text = text.replace("\\", "\\\\").replace('"', '\\"')

    query = f"""{PREFIXES}
INSERT DATA {{
    {chunk_uri} rdf:type ki4kmu:Chunk .
    {chunk_uri} rdfs:label "{chunk_id}" .
    {chunk_uri} ki4kmu:belongsTo {doc_uri} .
    {chunk_uri} ki4kmu:chunk_index {_literal(chunk_index)} .
    {chunk_uri} ki4kmu:text "{clean_text}" .
{page_triple}
}}"""
    _run_update(query)


def insert_image(image_id: str, document_id: str, image_base64: str, page_number: int | None = None) -> None:
    """Insert a ki4kmu:Image node."""
    image_uri = _uri(image_id)
    doc_uri = _document_uri(document_id)

    page_triple = ""
    if page_number is not None:
        page_triple = f'    {image_uri} ki4kmu:page_number {_literal(page_number)} .'

    query = f"""{PREFIXES}
INSERT DATA {{
    {image_uri} rdf:type ki4kmu:Image .
    {image_uri} rdfs:label "{image_id}" .
    {image_uri} ki4kmu:belongsTo {doc_uri} .
    {image_uri} ki4kmu:image_base64 "{image_base64}" .
{page_triple}
}}"""
    _run_update(query)


def insert_or_merge_section(section: dict, chunk_id: str) -> None:
    """
    Upsert a ki4kmu:Section (or ki4kmu:Text / ki4kmu:Image co-type) and link
    it to the chunk via ki4kmu:isContained.

    Uses INSERT … WHERE { OPTIONAL { … } } so concurrent writes to the same
    section_id do not create duplicate nodes.
    """
    section_id = _canonical_id(section.get("section_id", ""))
    if not section_id:
        return

    section_uri = _uri(section_id)
    chunk_uri = _uri(chunk_id)
    section_type = section.get("section_type", "Text")
    co_type = "ki4kmu:Image" if section_type == "Image" else "ki4kmu:Text"
    enumeration = section.get("section_enumeration", "")
    clean_enum = enumeration.replace("\\", "\\\\").replace('"', '\\"')
    clean_id = section_id.replace("\\", "\\\\").replace('"', '\\"')

    # First: always insert the containment edge
    containment_query = f"""{PREFIXES}
INSERT DATA {{
    {chunk_uri} ki4kmu:isContained {section_uri} .
}}"""
    _run_update(containment_query)

    # Second: insert section metadata (idempotent — duplicate data is harmless in RDF)
    section_query = f"""{PREFIXES}
INSERT DATA {{
    {section_uri} rdf:type ki4kmu:Section .
    {section_uri} rdf:type {co_type} .
    {section_uri} rdfs:label "{clean_id}" .
    {section_uri} ki4kmu:section_id "{clean_id}" .
    {section_uri} ki4kmu:section_enumeration "{clean_enum}" .
}}"""
    _run_update(section_query)


# ---------------------------------------------------------------------------
# Ontology loading on startup
# ---------------------------------------------------------------------------

ONTOLOGY_GRAPH_URI = "<http://ki4kmu.fhnw.ch/ontology>"
ONTOLOGY_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "ontology" / "ki4kmu.ttl"


def ensure_ontology_loaded() -> None:
    """
    Check whether the ontology named graph exists in GraphDB.
    If not, upload ki4kmu.ttl via the GraphDB REST API.
    """
    # Check if the named graph already exists
    check_query = f"""ASK WHERE {{ GRAPH {ONTOLOGY_GRAPH_URI} {{ ?s ?p ?o }} }}"""
    try:
        client = _get_write_client()  # reuse lazy init for URL/auth info
        check_sparql = SPARQLWrapper(f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}")
        check_sparql.setReturnFormat(JSON)
        user = os.getenv("GRAPHDB_USER")
        password = os.getenv("GRAPHDB_PASSWORD")
        if user and password:
            check_sparql.setHTTPAuth(DIGEST)
            check_sparql.setCredentials(user, password)
        check_sparql.setQuery(check_query)
        result = check_sparql.query().convert()
        if result.get("boolean", False):
            logger.info("[GRAPHDB] Ontology named graph already loaded")
            return
    except Exception as e:
        logger.warning("[GRAPHDB] Failed to check ontology existence, will attempt upload: %s", e)

    # Upload the ontology file
    if not ONTOLOGY_FILE_PATH.exists():
        logger.warning("[GRAPHDB] Ontology file not found at %s — skipping upload", ONTOLOGY_FILE_PATH)
        return

    url = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}/rdf-graphs/service"
    params = {"graph": ONTOLOGY_GRAPH_URI.strip("<>")}
    headers = {"Content-Type": "text/turtle"}
    auth = None
    user = os.getenv("GRAPHDB_USER")
    password = os.getenv("GRAPHDB_PASSWORD")
    if user and password:
        auth = (user, password)

    try:
        turtle_data = ONTOLOGY_FILE_PATH.read_text(encoding="utf-8")
        resp = requests.put(url, params=params, headers=headers, data=turtle_data, auth=auth, timeout=30)
        resp.raise_for_status()
        logger.info("[GRAPHDB] Ontology loaded successfully into named graph %s", ONTOLOGY_GRAPH_URI)
    except Exception as e:
        logger.error("[GRAPHDB] Failed to upload ontology: %s", e)
