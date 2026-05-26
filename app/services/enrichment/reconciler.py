import logging
from collections import defaultdict
from typing import Any
from urllib.parse import quote

from app.infrastructure.graphdb_writer import _run_update, _canonical_id, _literal
from app.core.config import PREFIXES, BASE_NS

logger = logging.getLogger(__name__)


def _uri(local: str) -> str:
    return f"<{BASE_NS}{quote(str(local), safe='')}>"


def write_entity_triples(
    triples: list[dict[str, Any]],
    document_id: str,
) -> None:
    """
    Write disambiguated entity mentions to GraphDB:
      - Assert each entity as its canonical type node.
      - Link the entity to the chunk it was found in via ki4kmu:mentionedIn.
      - Link the entity to the document via ki4kmu:appearsIn.
      - Cross-document: for entities already present from other documents,
        GraphDB's UPSERT (INSERT WHERE NOT EXISTS) naturally merges them.
    """
    if not triples:
        return

    doc_uri = _uri(f"doc_{document_id}")

    # Group by canonical entity to batch writes
    by_entity: dict[str, dict[str, Any]] = {}
    chunk_links: dict[str, list[str]] = defaultdict(list)

    for t in triples:
        label = t["subject"]
        etype = t["subject_type"]
        chunk_id = t["chunk_id"]
        entity_id = _canonical_id(label)
        by_entity[entity_id] = {"label": label, "type": etype}
        chunk_links[entity_id].append(chunk_id)

    # Build SPARQL INSERT DATA block
    insert_lines: list[str] = []
    for entity_id, info in by_entity.items():
        entity_uri = _uri(f"entity_{entity_id}")
        type_uri = _uri(info["type"])
        insert_lines.append(f"    {entity_uri} rdf:type ki4kmu:Entity .")
        insert_lines.append(f"    {entity_uri} rdf:type {type_uri} .")
        insert_lines.append(f"    {entity_uri} rdfs:label {_literal(info['label'])} .")
        insert_lines.append(f"    {entity_uri} ki4kmu:appearsIn {doc_uri} .")
        for chunk_id in chunk_links[entity_id]:
            chunk_uri = _uri(chunk_id)
            insert_lines.append(f"    {entity_uri} ki4kmu:mentionedIn {chunk_uri} .")

    if not insert_lines:
        return

    # Use INSERT WHERE NOT EXISTS for entity nodes to avoid duplicates (SPARQL 1.1 UPSERT pattern)
    for entity_id, info in by_entity.items():
        entity_uri = _uri(f"entity_{entity_id}")
        type_uri = _uri(info["type"])
        upsert = f"""{PREFIXES}
INSERT {{
    {entity_uri} rdf:type ki4kmu:Entity .
    {entity_uri} rdf:type {type_uri} .
    {entity_uri} rdfs:label {_literal(info['label'])} .
}}
WHERE {{
    FILTER NOT EXISTS {{ {entity_uri} rdf:type ki4kmu:Entity . }}
}}"""
        _run_update(upsert)

    # Batch-insert chunk + document links (idempotent: duplicate triples are no-ops in RDF)
    batch_lines = "\n".join(insert_lines)
    batch_query = f"{PREFIXES}\nINSERT DATA {{\n{batch_lines}\n}}"
    _run_update(batch_query)

    # Cross-document: add ki4kmu:relatedTo between entities from different documents
    # that share the same canonical label (URI collision = same entity = already merged)
    # For entities that co-occur in the same chunk, add a co-mention edge.
    _write_comention_edges(by_entity, chunk_links)

    logger.info(
        "[RECONCILER] Wrote %d entities and chunk links for document %s",
        len(by_entity),
        document_id,
    )


def _write_comention_edges(by_entity: dict, chunk_links: dict[str, list[str]]) -> None:
    """For entities co-occurring in the same chunk, assert ki4kmu:coMentionedWith."""
    chunk_to_entities: dict[str, list[str]] = defaultdict(list)
    for entity_id, chunk_ids in chunk_links.items():
        for cid in chunk_ids:
            chunk_to_entities[cid].append(entity_id)

    edge_lines: list[str] = []
    seen: set[frozenset] = set()
    for entity_ids in chunk_to_entities.values():
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                pair = frozenset([entity_ids[i], entity_ids[j]])
                if pair in seen:
                    continue
                seen.add(pair)
                uri_a = _uri(f"entity_{entity_ids[i]}")
                uri_b = _uri(f"entity_{entity_ids[j]}")
                edge_lines.append(f"    {uri_a} ki4kmu:coMentionedWith {uri_b} .")
                edge_lines.append(f"    {uri_b} ki4kmu:coMentionedWith {uri_a} .")

    if edge_lines:
        query = f"{PREFIXES}\nINSERT DATA {{\n" + "\n".join(edge_lines) + "\n}"
        _run_update(query)
