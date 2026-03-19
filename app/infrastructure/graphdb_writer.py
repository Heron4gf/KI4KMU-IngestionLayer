import os
import re
import logging
import unicodedata
from urllib.parse import quote
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST

from app.utils.string_similarity import are_strings_similar
from app.core.config import GRAPHDB_URL, GRAPHDB_REPO, PREFIXES, BASE_NS

logger = logging.getLogger(__name__)

_ENTITY_CACHE = {}

def _get_sparql_client(is_read=False) -> SPARQLWrapper:
    endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    if not is_read:
        endpoint += "/statements"
    sparql = SPARQLWrapper(endpoint)
    if not is_read:
        sparql.setMethod(POST)
    sparql.setReturnFormat(JSON)
    user = os.getenv("GRAPHDB_USER")
    password = os.getenv("GRAPHDB_PASSWORD")
    if user and password:
        sparql.setHTTPAuth(DIGEST)
        sparql.setCredentials(user, password)
    return sparql

_SPARQL_READ = _get_sparql_client(is_read=True)
_SPARQL_WRITE = _get_sparql_client(is_read=False)

def _canonical_id(raw: str) -> str:
    nfd = unicodedata.normalize("NFD", raw)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_str.lower()).strip("_")
    return re.sub(r"_+", "_", slug)

def _run_update(query: str) -> None:
    _SPARQL_WRITE.setQuery(query)
    _SPARQL_WRITE.query()

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

def _load_cache_for_class(class_uri: str) -> None:
    if class_uri in _ENTITY_CACHE:
        return
    query = f"{PREFIXES}\nSELECT ?entity ?label WHERE {{ ?entity rdf:type {class_uri} . ?entity rdfs:label ?label . }}"
    try:
        _SPARQL_READ.setQuery(query)
        results = _SPARQL_READ.query().convert()
        _ENTITY_CACHE[class_uri] = {
            r["label"]["value"].lower(): r["entity"]["value"]
            for r in results["results"]["bindings"]
        }
    except Exception as e:
        logger.error("Cache load failed: %s", e)
        _ENTITY_CACHE[class_uri] = {}

def _find_duplicate_entity(label: str, class_uri: str) -> str | None:
    _load_cache_for_class(class_uri)
    cache = _ENTITY_CACHE[class_uri]
    
    lower_label = label.lower()
    
    # We achieve O(1) time complexity here through a Hash Map (dictionary) lookup.
    # By mapping the lowercase labels to URIs when we load the cache, 
    # we can check if the current label exists directly via its hash.
    # This bypasses the need to iterate through the entire dataset O(n).
    if lower_label in cache:
        return cache[lower_label]
        
    for existing_lower_label, uri in cache.items():
        if are_strings_similar(lower_label, existing_lower_label):
            return uri
            
    return None

def _class_uri(class_name: str) -> str:
    return f"<{BASE_NS}{class_name.strip().capitalize()}>"

def insert_chunk(chunk_id: str, metadata: dict) -> None:
    chunk_uri = _uri(chunk_id)
    meta_triples = "\n    ".join(f"{chunk_uri} {_uri(k)} {_literal(v)} ." for k, v in metadata.items() if v is not None)
    query = f"{PREFIXES}\nINSERT DATA {{\n    {chunk_uri} rdf:type pi:Chunk .\n    {chunk_uri} rdfs:label \"{chunk_id}\" .\n    {meta_triples}\n}}"
    _run_update(query)

def _merge_mention(existing_uri_full: str, chunk_id: str) -> None:
    chunk_uri = _uri(chunk_id)
    existing_uri = f"<{existing_uri_full}>"
    query = f"{PREFIXES}\nINSERT DATA {{\n    {existing_uri} pi:mentionedIn {chunk_uri} .\n}}"
    _run_update(query)

def insert_typed_entity(extraction: dict, chunk_id: str) -> None:
    if not extraction:
        return
        
    raw_class = extraction.get("extraction_class", "").strip().lower()
    extraction_text = extraction.get("extraction_text", "").strip()
    attributes = extraction.get("attributes") or {}
    
    raw_id = attributes.get("id") or extraction_text
    entity_id = _canonical_id(raw_id)
    
    if not entity_id or not extraction_text or raw_class == "relationship":
        return
        
    class_triple_uri = _class_uri(raw_class)
    
    duplicate_uri = _find_duplicate_entity(extraction_text, class_triple_uri)
    if duplicate_uri:
        _merge_mention(duplicate_uri, chunk_id)
        return

    entity_uri = _uri(entity_id)
    chunk_uri = _uri(chunk_id)
    attr_triples = "\n    ".join(f"{entity_uri} {_uri(k)} {_literal(v)} ." for k, v in attributes.items() if v is not None and k != "id")
    
    clean_text = extraction_text.replace("\\", "\\\\").replace('"', '\\"')
    query = f"{PREFIXES}\nINSERT DATA {{\n    {entity_uri} rdf:type {class_triple_uri} .\n    {entity_uri} rdfs:label \"{clean_text}\" .\n    {entity_uri} pi:mentionedIn {chunk_uri} .\n    {attr_triples}\n}}"
    
    _run_update(query)
    
    clean_uri = entity_uri.replace("pi:", f"{BASE_NS}").strip("<>")
    _ENTITY_CACHE.setdefault(class_triple_uri, {})[extraction_text.lower()] = clean_uri

def insert_relationship(extraction: dict, chunk_id: str) -> None:
    if not extraction or extraction.get("extraction_class", "").strip().lower() != "relationship":
        return
        
    attrs = extraction.get("attributes") or {}
    rel_type = attrs.get("type", "").strip()
    subject_id = _canonical_id(attrs.get("subject_id", "").strip())
    object_id = _canonical_id(attrs.get("object_id", "").strip())
    context = attrs.get("context", "")
    
    if not (rel_type and subject_id and object_id):
        return
        
    rel_id = f"rel_{subject_id}_{rel_type}_{object_id}"
    rel_uri = _uri(rel_id)
    subj_uri = _uri(subject_id)
    obj_uri = _uri(object_id)
    chunk_uri = _uri(chunk_id)
    
    context_triple = f'{rel_uri} pi:context {_literal(context)} .' if context else ""
    
    query = f"{PREFIXES}\nINSERT DATA {{\n    {rel_uri} rdf:type pi:Relationship .\n    {rel_uri} pi:type \"{rel_type}\" .\n    {rel_uri} pi:subject {subj_uri} .\n    {rel_uri} pi:object {obj_uri} .\n    {rel_uri} pi:mentionedIn {chunk_uri} .\n    {context_triple}\n    {subj_uri} {_uri(rel_type)} {obj_uri} .\n}}"
    _run_update(query)