import logging
from typing import Any, Dict, List, Tuple

import chromadb

from app.models.api_models import QueryResultItem
from app.utils.files import cast_to_str, sanitize_metadata
from app.core.config import CHROMA_COLLECTION, CHROMA_HOST, CHROMA_PORT
from app.infrastructure.ml.text_embedder import text_embedder

logger = logging.getLogger(__name__)

def get_chroma_collection():
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection(name=CHROMA_COLLECTION)

def document_already_ingested(pdf_hash: str) -> bool:
    collection = get_chroma_collection()
    res = collection.get(where={"pdf_hash": pdf_hash}, limit=1)
    return len(res.get("ids", [])) > 0

def _build_element_metadata(
    element: Dict[str, Any],
    document_id: str,
    pdf_hash: str,
    chunk_id: str,
) -> Dict[str, Any]:
    element_type = cast_to_str(element.get("type", ""))
    raw_metadata = element.get("metadata") or {}
    metadata = sanitize_metadata(raw_metadata)
    metadata["document_id"] = document_id
    metadata["element_type"] = element_type
    metadata["pdf_hash"] = pdf_hash
    metadata["chunk_id"] = chunk_id
    return metadata

def _process_text_elements(
    text_elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
    start_index: int,
) -> Tuple[List[str], List[Dict], List[str], List[str], int]:
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    idx_counter = start_index

    for element in text_elements:
        text = cast_to_str(element.get("text"))
        if not text:
            continue
        
        chunk_id = f"{document_id}_chunk_{idx_counter}"
        metadata = _build_element_metadata(element, document_id, pdf_hash, chunk_id)
        metadata["modality"] = "text"
            
        ids.append(chunk_id)
        metadatas.append(metadata)
        documents.append(text)
        texts_to_embed.append(text)
        idx_counter += 1

    return ids, metadatas, documents, texts_to_embed, idx_counter

def _process_captioned_images(
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
    start_index: int,
) -> Tuple[List[str], List[Dict], List[str], List[str], int, int, int]:
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    idx_counter = start_index
    images_added = 0
    images_skipped = 0

    for element in captioned_images:
        raw_metadata = element.get("metadata") or {}
        caption = raw_metadata.get("image_caption")
        image_b64 = raw_metadata.get("image_base64")

        if not caption or not image_b64:
            images_skipped += 1
            continue

        chunk_id = f"{document_id}_chunk_{idx_counter}"
        metadata = _build_element_metadata(element, document_id, pdf_hash, chunk_id)
        metadata["modality"] = "image"
        metadata["image_b64"] = image_b64

        ids.append(chunk_id)
        metadatas.append(metadata)
        documents.append(caption)
        texts_to_embed.append(caption)
        idx_counter += 1
        images_added += 1

    return ids, metadatas, documents, texts_to_embed, images_added, images_skipped, idx_counter

def build_chroma_payload(
    text_elements: List[Dict[str, Any]],
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> Dict[str, List[Any]]:
    text_ids, text_metadatas, text_documents, text_texts_to_embed, idx_counter = _process_text_elements(
        text_elements, document_id, pdf_hash, start_index=0
    )

    (
        image_ids,
        image_metadatas,
        image_documents,
        image_texts_to_embed,
        images_added,
        images_skipped,
        _,
    ) = _process_captioned_images(
        captioned_images, document_id, pdf_hash, start_index=idx_counter
    )

    ids = text_ids + image_ids
    metadatas = text_metadatas + image_metadatas
    documents = text_documents + image_documents
    texts_to_embed = text_texts_to_embed + image_texts_to_embed

    embeddings = text_embedder.embed_texts(texts_to_embed) if texts_to_embed else []

    return {
        "ids": ids,
        "embeddings": embeddings,
        "documents": documents,
        "metadatas": metadatas,
    }

def store_chunks_in_chroma(
    text_elements: List[Dict[str, Any]],
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> int:
    payload = build_chroma_payload(text_elements, captioned_images, document_id, pdf_hash)
    
    if not payload["ids"]:
        return 0

    collection = get_chroma_collection()
    collection.add(
        ids=payload["ids"],
        embeddings=payload["embeddings"],
        documents=payload["documents"],
        metadatas=payload["metadatas"],
    )

    return len(payload["ids"])

def semantic_search(query: str, top_k: int = 5) -> List[QueryResultItem]:
    if top_k <= 0:
        top_k = 5

    query_embeddings = text_embedder.embed_texts([query])
    collection = get_chroma_collection()
    
    raw = collection.query(
        query_embeddings=query_embeddings,
        n_results=top_k,
    )

    ids = raw.get("ids", [[]])[0] if raw.get("ids") else []
    documents = raw.get("documents", [[]])[0] if raw.get("documents") else []
    metadatas = raw.get("metadatas", [[]])[0] if raw.get("metadatas") else []
    distances = raw.get("distances", [[]])[0] if raw.get("distances") else []

    results: List[QueryResultItem] = []
    for chunk_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        is_image = meta.get("modality") == "image"
        item = QueryResultItem(
            id=str(chunk_id),
            text=str(doc) if not is_image else "[image]",
            score=float(dist),
            metadata=meta or {},
            source="vector",
        )
        results.append(item)

    return results
