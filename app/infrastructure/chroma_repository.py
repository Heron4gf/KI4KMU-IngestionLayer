import logging
from typing import Any, Dict, List, Optional

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


def delete_document_sections(document_id: str) -> None:
    """Delete all sections for a document from Chroma."""
    collection = get_chroma_collection()
    results = collection.get(where={"document_id": document_id})
    ids = results.get("ids", [])
    if ids:
        collection.delete(ids=ids)
        logger.info("[CHROMA] Rolled back %d sections for document %s", len(ids), document_id)


def _build_section_metadata(
    section: Dict[str, Any],
    document_id: str,
    pdf_hash: str,
    chunk_id: str,
) -> Dict[str, Any]:
    """Build metadata for a section entry in Chroma."""
    raw_metadata = section.get("metadata") or {}
    metadata = sanitize_metadata(raw_metadata)
    metadata["document_id"] = document_id
    metadata["pdf_hash"] = pdf_hash
    metadata["chunk_id"] = chunk_id
    metadata["section_id"] = section.get("section_id", "")
    metadata["section_uuid"] = section.get("uuid", "")
    metadata["section_label"] = section.get("label", "")
    metadata["section_type"] = section.get("section_type", "Text")
    return metadata


def _process_sections(
    sections: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
    chunk_id: str,
) -> tuple[List[str], List[Dict], List[str], List[str]]:
    """Process sections and return Chroma-compatible payload components."""
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []

    for section in sections:
        section_uuid = section.get("uuid")
        if not section_uuid:
            logger.warning("[CHROMA] Section without UUID, skipping: %s", section.get("section_id"))
            continue

        # Build combined text from all texts in the section
        texts = section.get("texts", [])
        combined_text = " ".join(t.get("content", "") for t in texts if t.get("content"))
        
        if not combined_text:
            logger.warning("[CHROMA] Section %s has no text content, skipping", section_uuid)
            continue

        # Use section UUID as the Chroma ID
        section_id = section_uuid
        metadata = _build_section_metadata(section, document_id, pdf_hash, chunk_id)
        metadata["modality"] = "text"

        ids.append(section_id)
        metadatas.append(metadata)
        documents.append(combined_text)
        texts_to_embed.append(combined_text)

    return ids, metadatas, documents, texts_to_embed


def _process_captioned_images(
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> tuple[List[str], List[Dict], List[str], List[str], int, int]:
    """Process captioned images and return Chroma-compatible payload components."""
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    images_added = 0
    images_skipped = 0

    for idx, element in enumerate(captioned_images):
        raw_metadata = element.get("metadata") or {}
        caption = raw_metadata.get("image_caption")
        image_b64 = raw_metadata.get("image_base64")

        if not caption or not image_b64:
            images_skipped += 1
            continue

        image_id = f"{document_id}_image_{idx}"
        metadata = sanitize_metadata(raw_metadata)
        metadata["document_id"] = document_id
        metadata["pdf_hash"] = pdf_hash
        metadata["image_id"] = image_id
        metadata["modality"] = "image"
        metadata["image_b64"] = image_b64

        ids.append(image_id)
        metadatas.append(metadata)
        documents.append(caption)
        texts_to_embed.append(caption)
        images_added += 1

    return ids, metadatas, documents, texts_to_embed, images_added, images_skipped


def build_chroma_payload(
    sections: List[Dict[str, Any]],
    chunk_id: str,
    document_id: str,
    pdf_hash: str,
    captioned_images: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, List[Any]]:
    """Build Chroma payload from sections and optional images."""
    section_ids, section_metadatas, section_documents, section_texts_to_embed = _process_sections(
        sections, document_id, pdf_hash, chunk_id
    )

    image_ids: List[str] = []
    image_metadatas: List[Dict] = []
    image_documents: List[str] = []
    image_texts_to_embed: List[str] = []

    if captioned_images:
        (
            image_ids,
            image_metadatas,
            image_documents,
            image_texts_to_embed,
            _,
            _,
        ) = _process_captioned_images(captioned_images, document_id, pdf_hash)

    ids = section_ids + image_ids
    metadatas = section_metadatas + image_metadatas
    documents = section_documents + image_documents
    texts_to_embed = section_texts_to_embed + image_texts_to_embed

    embeddings = text_embedder.embed_texts(texts_to_embed) if texts_to_embed else []

    return {
        "ids": ids,
        "embeddings": embeddings,
        "documents": documents,
        "metadatas": metadatas,
    }


def store_sections_in_chroma(
    sections: List[Dict[str, Any]],
    chunk_id: str,
    document_id: str,
    pdf_hash: str,
    captioned_images: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Store sections (and optionally images) in Chroma. Returns number of items stored."""
    payload = build_chroma_payload(sections, chunk_id, document_id, pdf_hash, captioned_images)

    if not payload["ids"]:
        return 0

    collection = get_chroma_collection()
    collection.upsert(
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
    for item_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        is_image = meta.get("modality") == "image"
        item = QueryResultItem(
            id=str(item_id),
            text=str(doc) if not is_image else "[image]",
            score=float(dist),
            metadata=meta or {},
            source="vector",
        )
        results.append(item)

    return results
