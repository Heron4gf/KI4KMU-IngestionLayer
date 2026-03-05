import os
from pathlib import Path
from typing import Any, Dict, List

import chromadb

from models import QueryResultItem
from utils import cast_to_str, file_md5, sanitize_metadata

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
collection = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)


def document_already_ingested(pdf_hash: str) -> bool:
    """Check if a document with the given pdf_hash already exists in Chroma."""
    res = collection.get(
        where={"pdf_hash": pdf_hash},
        limit=1,
    )
    return len(res.get("ids", [])) > 0


def build_chroma_payload(
    elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> Dict[str, List[Any]]:
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    for idx, element in enumerate(elements):
        text = cast_to_str(element.get("text"))
        if not text:
            continue

        raw_metadata = element.get("metadata") or {}
        metadata = sanitize_metadata(raw_metadata)

        metadata["document_id"] = document_id
        metadata["element_type"] = cast_to_str(element.get("type"))
        metadata["pdf_hash"] = pdf_hash

        documents.append(text)
        metadatas.append(metadata)
        ids.append(f"{document_id}-{idx}")

    return {
        "documents": documents,
        "metadatas": metadatas,
        "ids": ids,
    }


def store_chunks_in_chroma(
    elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> int:
    payload = build_chroma_payload(elements, document_id, pdf_hash)
    if not payload["documents"]:
        return 0
    collection.add(
        documents=payload["documents"],
        metadatas=payload["metadatas"],
        ids=payload["ids"],
    )
    return len(payload["documents"])


def semantic_search(query: str, top_k: int) -> List[QueryResultItem]:
    if top_k <= 0:
        top_k = 5

    raw = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    results: List[QueryResultItem] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        item = QueryResultItem(
            id=str(meta.get("document_id", "")),
            text=str(doc),
            score=float(dist),
            metadata=meta or {},
        )
        results.append(item)

    return results