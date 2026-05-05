import os
import logging
import unicodedata
import re
from pathlib import Path
from urllib.parse import quote
import requests
from requests.auth import HTTPDigestAuth
from SPARQLWrapper import SPARQLWrapper, JSON, DIGEST

from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS
from app.infrastructure.sparql import load_and_parse
from app.utils.text_normalization import extract_keyphrases

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SPARQL write via requests (avoids SPARQLWrapper 415 content-type bug)
# ---------------------------------------------------------------------------

def _run_update(query: str) -> None:
    url = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}/statements"
    headers = {"Content-Type": "application/sparql-update"}
    user = os.getenv("GRAPHDB_USER")
    password = os.getenv("GRAPHDB_PASSWORD")
    auth = HTTPDigestAuth(user, password) if user and password else None
    resp = requests.post(url, data=query.encode("utf-8"), headers=headers, auth=auth, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"GraphDB update failed ({resp.status_code}): {resp.text[:200]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_id(raw):
    nfd = unicodedata.normalize("NFD", raw)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_str.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


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
    query = load_and_parse(
        "insert_document.sparql",
        PREFIXES=PREFIXES,
        doc_uri=doc_uri,
        document_id=document_id,
        pdf_hash=pdf_hash,
    )
    _run_update(query)


def insert_chunk(chunk_id, document_id, text, chunk_index, page_number=None):
    chunk_uri = _uri(chunk_id)
    doc_uri = _uri(f"doc_{document_id}")

    page_triple = ""
    if page_number is not None:
        page_triple = f"    {chunk_uri} ki4kmu:page_number {_literal(page_number)} ."

    query = load_and_parse(
        "insert_chunk.sparql",
        PREFIXES=PREFIXES,
        chunk_uri=chunk_uri,
        chunk_id=chunk_id,
        doc_uri=doc_uri,
        chunk_index=chunk_index,
        text=text,
        page_triple=page_triple,
    )
    _run_update(query)


def insert_image(image_id, document_id, image_base64, section_uri, page_number=None):
    image_uri = _uri(image_id)
    doc_uri = _uri(f"doc_{document_id}")

    page_triple = ""
    if page_number is not None:
        page_triple = f"    {image_uri} ki4kmu:page_number {_literal(page_number)} ."

    query = load_and_parse(
        "insert_image.sparql",
        PREFIXES=PREFIXES,
        image_uri=image_uri,
        image_id=image_id,
        doc_uri=doc_uri,
        image_base64=image_base64,
        section_uri=section_uri,
        page_triple=page_triple,
    )
    _run_update(query)


def insert_or_merge_section(section, chunk_id):
    """Insert or merge a section into the graph. Uses section UUID as the primary identifier."""
    section_uuid = section.get("uuid")
    if not section_uuid:
        logger.warning("[GRAPHDB] Section missing UUID, skipping: %s", section.get("section_id"))
        return

    section_id = _canonical_id(section.get("section_id", ""))
    section_uri = _uri(section_uuid)  # Use UUID as URI
    section_type = section.get("section_type", "Text")
    co_type = "ki4kmu:Image" if section_type == "Image" else "ki4kmu:Text"
    label = section.get("label", section_id)

    # Only insert containment triple if chunk_id is provided (not empty for image sections)
    if chunk_id:
        chunk_uri = _uri(chunk_id)
        containment_query = load_and_parse(
            "insert_section_containment.sparql",
            PREFIXES=PREFIXES,
            chunk_uri=chunk_uri,
            section_uri=section_uri,
        )
        _run_update(containment_query)

    section_query = load_and_parse(
        "insert_section.sparql",
        PREFIXES=PREFIXES,
        section_uri=section_uri,
        section_type=co_type,
        label=label,
        section_id=section_id,
        section_uuid=section_uuid,
    )
    _run_update(section_query)

    # Insert Text instances + Keyphrases (batched)
    texts = section.get("texts", [])
    for idx, text_obj in enumerate(texts):
        text_content = text_obj.get("content", "")
        if text_content:
            text_id = f"{section_uuid}_text_{idx}"
            text_uri = _uri(text_id)
            text_query = load_and_parse(
                "insert_text.sparql",
                PREFIXES=PREFIXES,
                text_uri=text_uri,
                text_id=text_id,
                text_content=_literal(text_content),
                section_uri=section_uri,
            )
            _run_update(text_query)

            # Batch insert all keyphrases for this text in a single SPARQL call
            keyphrases = extract_keyphrases(text_content)
            if keyphrases:
                kp_triples = ""
                for kp_idx, kp in enumerate(keyphrases):
                    kp_id = _canonical_id(kp)
                    kp_uri = _uri(f"kp_{section_uuid}_{idx}_{kp_idx}_{kp_id}")
                    kp_triples += f"    {text_uri} ki4kmu:hasKeyphrase {kp_uri} .\n"
                    kp_triples += f"    {kp_uri} rdf:type ki4kmu:Keyphrase .\n"
                    kp_triples += f"    {kp_uri} rdfs:label {_literal(kp)} .\n"
                
                batch_query = f"{PREFIXES}\nINSERT DATA {{\n{kp_triples}}}"
                _run_update(batch_query)

    # Batch insert all tags for this section in a single SPARQL call
    tags = section.get("tags", [])
    if tags:
        tag_triples = ""
        for tag_obj in tags:
            tag_label = tag_obj.get("label", "")
            if tag_label:
                tag_id = _canonical_id(tag_label)
                tag_uri = _uri(tag_id)
                tag_triples += f"    {tag_uri} rdf:type ki4kmu:Tag .\n"
                tag_triples += f"    {tag_uri} rdfs:label {_literal(tag_label)} .\n"
                tag_triples += f"    {section_uri} ki4kmu:hasTag {tag_uri} .\n"
        
        if tag_triples:
            batch_query = f"{PREFIXES}\nINSERT DATA {{\n{tag_triples}}}"
            _run_update(batch_query)


def insert_text(text_id, text_content, section_uri):
    text_uri = _uri(text_id)
    query = load_and_parse(
        "insert_text.sparql",
        PREFIXES=PREFIXES,
        text_uri=text_uri,
        text_id=text_id,
        text_content=_literal(text_content),
        section_uri=section_uri,
    )
    _run_update(query)


def insert_tag(tag_label, section_uri):
    tag_id = _canonical_id(tag_label)
    tag_uri = _uri(tag_id)
    query = load_and_parse(
        "insert_tag.sparql",
        PREFIXES=PREFIXES,
        tag_uri=tag_uri,
        tag_id=tag_id,
        tag_label=_literal(tag_label),
        section_uri=section_uri,
    )
    _run_update(query)


# ---------------------------------------------------------------------------
# Ontology loading
# ---------------------------------------------------------------------------

ONTOLOGY_GRAPH_URI = "<http://ki4kmu.fhnw.ch/ontology>"
ONTOLOGY_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "ontology" / "ontology.ttl"


def ensure_ontology_loaded():
    check_query = load_and_parse(
        "check_ontology_loaded.sparql",
        graph_uri=ONTOLOGY_GRAPH_URI,
    )
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