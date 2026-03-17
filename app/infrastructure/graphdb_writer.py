import os
import re
import logging
import unicodedata
from urllib.parse import quote
from pathlib import Path

import yaml
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST
from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "ontology" / "ki_kmu_schema.yaml"

_ACRONYMS = {"kmu", "fhnw", "ki", "nlp", "ml", "ai", "eu", "erp", "crm", "iot", "api", "kpi"}


def _load_valid_types() -> tuple[set[str], set[str]]:
    try:
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        classes = schema.get("classes", {})
        entity_classes = {
            name.lower() for name, cls in classes.items()
            if not cls.get("abstract", False) and name != "Beziehung"
        }
        rel_types = set(
            schema.get("enums", {})
            .get("BeziehungsTyp", {})
            .get("permissible_values", {})
            .keys()
        )
        return entity_classes, rel_types
    except FileNotFoundError:
        logger.warning("Schema not found at %s — type validation disabled", _SCHEMA_PATH)
        return set(), set()


VALID_ENTITY_CLASSES, VALID_REL_TYPES = _load_valid_types()


def _canonical_id(raw: str) -> str:
    nfd = unicodedata.normalize("NFD", raw)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_str.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if slug in _ACRONYMS:
        return slug.upper()
    return slug


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
    return f"pi:{quote(str(local), safe='')}"


def _literal(value) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    if isinstance(value, float):
        return f'"{value}"^^xsd:decimal'
    escaped = str(value).replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


def _class_uri(class_name: str) -> str:
    label = class_name.strip().capitalize()
    return f"<{BASE_NS}{label}>"


def insert_chunk(chunk_id: str, metadata: dict) -> None:
    chunk_uri = _uri(chunk_id)
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
        logger.info("insert_chunk OK  chunk_id=%s", chunk_id)
    except Exception as e:
        logger.error("insert_chunk FAILED  chunk_id=%s  error=%s", chunk_id, e)
        raise


def insert_typed_entity(extraction: dict, chunk_id: str) -> None:
    if not extraction:
        return

    raw_class = extraction.get("extraction_class", "").strip().lower()
    extraction_text = extraction.get("extraction_text", "").strip()
    attributes = extraction.get("attributes") or {}

    raw_id = attributes.get("id") or extraction_text
    entity_id = _canonical_id(raw_id)

    if not entity_id or not extraction_text:
        logger.debug("Skipping empty extraction: %s", extraction)
        return

    if raw_class == "beziehung":
        return

    if VALID_ENTITY_CLASSES and raw_class not in VALID_ENTITY_CLASSES:
        logger.warning(
            "Unknown extraction_class '%s' — not in ontology schema. Storing as pi:Entity.",
            raw_class,
        )
        class_triple_uri = "pi:Entity"
    else:
        class_triple_uri = _class_uri(raw_class)

    entity_uri = _uri(entity_id)
    chunk_uri  = _uri(chunk_id)

    attr_triples = "\n    ".join(
        f"{entity_uri} {_uri(k)} {_literal(v)} ."
        for k, v in attributes.items()
        if v is not None and k != "id"
    )

    query = f"""
{PREFIXES}
INSERT DATA {{
    {entity_uri} rdf:type          {class_triple_uri} .
    {entity_uri} rdfs:label        "{extraction_text.replace(chr(34), chr(39))}" .
    {entity_uri} pi:mentionedIn    {chunk_uri} .
    {attr_triples}
}}
"""
    try:
        _run_update(query)
        logger.info("insert_typed_entity OK  class=%s  id=%s", raw_class, entity_id)
    except Exception as e:
        logger.error("insert_typed_entity FAILED  id=%s  error=%s", entity_id, e)
        raise


def insert_relationship(extraction: dict, chunk_id: str) -> None:
    if not extraction:
        return

    if extraction.get("extraction_class", "").strip().lower() != "beziehung":
        return

    attrs = extraction.get("attributes") or {}

    rel_typ    = attrs.get("typ", "").strip()
    subjekt_id = _canonical_id(attrs.get("subjekt_id", "").strip())
    objekt_id  = _canonical_id(attrs.get("objekt_id", "").strip())
    kontext    = attrs.get("kontext", "")

    if not (rel_typ and subjekt_id and objekt_id):
        logger.debug("Incomplete beziehung extraction — skipping: %s", attrs)
        return

    if VALID_REL_TYPES and rel_typ not in VALID_REL_TYPES:
        logger.warning("Unknown relationship type '%s' — not in ontology schema.", rel_typ)

    rel_id    = f"rel_{subjekt_id}_{rel_typ}_{objekt_id}"
    rel_uri   = _uri(rel_id)
    subj_uri  = _uri(subjekt_id)
    obj_uri   = _uri(objekt_id)
    chunk_uri = _uri(chunk_id)

    kontext_triple = (
        f'{rel_uri} pi:kontext {_literal(kontext)} .'
        if kontext else ""
    )

    query = f"""
{PREFIXES}
INSERT DATA {{
    {rel_uri}  rdf:type        pi:Beziehung .
    {rel_uri}  pi:typ          "{rel_typ}" .
    {rel_uri}  pi:subjekt      {subj_uri} .
    {rel_uri}  pi:objekt       {obj_uri} .
    {rel_uri}  pi:mentionedIn  {chunk_uri} .
    {kontext_triple}
    {subj_uri} {_uri(rel_typ)} {obj_uri} .
}}
"""
    try:
        _run_update(query)
        logger.info("insert_relationship OK  %s -[%s]-> %s", subjekt_id, rel_typ, objekt_id)
    except Exception as e:
        logger.error("insert_relationship FAILED  rel=%s  error=%s", rel_id, e)
        raise
