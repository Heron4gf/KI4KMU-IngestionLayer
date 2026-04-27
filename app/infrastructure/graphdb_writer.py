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
# Lazy SPARQL client
# ---------------------------------------------------------------------------

_SPARQL_WRITE = None


def _get_write_client():
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

def _canonical_id(raw):
    nfd = unicodedata.normalize("NFD", raw)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_str.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


def _run_update(query):
    client = _get_write_client()
    client.setQuery(query)
    client.query()


def _uri(local):
    return f"<{BASE_NS}{quote(str(local), safe='')}>"

def _literal(value):
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    if isinstance(value, float):
        return f'"{value}"^^xsd:decimal'
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"""{escaped}"""'


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def insert_document(document_id, pdf_hash):
    doc_uri = _uri(f"doc_{document_id}")
    query = f"""{PREFIXES}
INSERT DATA {{
    {doc_uri} rdf:type ki4kmu:Document .
    {doc_uri} rdfs:label {_literal(document_id)} .
    {doc_uri} ki4kmu:document_id {_literal(document_id)} .
    {doc_uri} ki4kmu:pdf_hash {_literal(pdf_hash)} .
}}"""
    _run_update(query)


def insert_chunk(chunk_id, document_id, text, chunk_index, page_number=None):
    chunk_uri = _uri(chunk_id)
    doc_uri = _uri(f"doc_{document_id}")

    page_triple = ""
    if page_number is not None:
        page_triple = f"    {chunk_uri} ki4kmu:page_number {_literal(page_number)} ."

    query = f"""{PREFIXES}
INSERT DATA {{
    {chunk_uri} rdf:type ki4kmu:Chunk .
    {chunk_uri} rdfs:label {_literal(chunk_id)} .
    {chunk_uri} ki4kmu:belongsTo {doc_uri} .
    {chunk_uri} ki4kmu:chunk_index {_literal(chunk_index)} .
    {chunk_uri} ki4kmu:text {_literal(text)} .
{page_triple}
}}"""
    _run_update(query)


def insert_image(image_id, document_id, image_base64, page_number=None):
    image_uri = _uri(image_id)
    doc_uri = _uri(f"doc_{document_id}")

    page_triple = ""
    if page_number is not None:
        page_triple = f"    {image_uri} ki4kmu:page_number {_literal(page_number)} ."

    query = f"""{PREFIXES}
INSERT DATA {{
    {image_uri} rdf:type ki4kmu:Image .
    {image_uri} rdfs:label {_literal(image_id)} .
    {image_uri} ki4kmu:belongsTo {doc_uri} .
    {image_uri} ki4kmu:image_base64 {_literal(image_base64)} .
{page_triple}
}}"""
    _run_update(query)


def insert_or_merge_section(section, chunk_id):
    section_id = _canonical_id(section.get("section_id", ""))
    if not section_id:
        return

    section_uri = _uri(section_id)
    chunk_uri = _uri(chunk_id)
    section_type = section.get("section_type", "Text")
    co_type = "ki4kmu:Image" if section_type == "Image" else "ki4kmu:Text"
    enumeration = section.get("section_enumeration", "")
    label = section.get("label", section_id)

    containment_query = f"""{PREFIXES}
INSERT DATA {{
    {chunk_uri} ki4kmu:isContained {section_uri} .
}}"""
    _run_update(containment_query)

    section_query = f"""{PREFIXES}
INSERT DATA {{
    {section_uri} rdf:type ki4kmu:Section .
    {section_uri} rdf:type {co_type} .
    {section_uri} rdfs:label {_literal(label)} .
    {section_uri} ki4kmu:section_id {_literal(section_id)} .
    {section_uri} ki4kmu:section_enumeration {_literal(enumeration)} .
}}"""
    _run_update(section_query)


# ---------------------------------------------------------------------------
# Ontology loading
# ---------------------------------------------------------------------------

ONTOLOGY_GRAPH_URI = "<http://ki4kmu.fhnw.ch/ontology>"
ONTOLOGY_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "ontology" / "ki4kmu.ttl"


def ensure_ontology_loaded():
    check_query = f"ASK WHERE {{ GRAPH {ONTOLOGY_GRAPH_URI} {{ ?s ?p ?o }} }}"
    try:
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
            logger.info("[GRAPHDB] Ontology already loaded")
            return
    except Exception as e:
        logger.warning("[GRAPHDB] Check failed, will attempt upload: %s", e)

    if not ONTOLOGY_FILE_PATH.exists():
        logger.warning("[GRAPHDB] Ontology file not found at %s", ONTOLOGY_FILE_PATH)
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
        logger.info("[GRAPHDB] Ontology loaded into %s", ONTOLOGY_GRAPH_URI)
    except Exception as e:
        logger.error("[GRAPHDB] Failed to upload ontology: %s", e)
