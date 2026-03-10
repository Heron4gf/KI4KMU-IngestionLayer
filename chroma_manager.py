import logging
import os
from typing import Any, Dict, List, Optional

import torch
import chromadb
from sentence_transformers import SentenceTransformer

from models import QueryResultItem
from utils import cast_to_str, sanitize_metadata


logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

TEXT_MODEL = os.getenv("TEXT_EMBEDDING_MODEL", "perplexity-ai/pplx-embed-v1-0.6b")


class TextEmbedder:
    """
    Text embedding service using SentenceTransformer.
    
    This class is responsible solely for generating text embeddings.
    It does not handle any image processing or ML inference beyond embeddings.
    """
    def __init__(self, model_id: str = TEXT_MODEL):
        self._model = SentenceTransformer(model_id, trust_remote_code=True)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=False,
            device=self._device,
            normalize_embeddings=True,
        )
        return [e.tolist() for e in embeddings]


text_embedder = TextEmbedder()

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
collection = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)


def document_already_ingested(pdf_hash: str) -> bool:
    res = collection.get(where={"pdf_hash": pdf_hash}, limit=1)
    return len(res.get("ids", [])) > 0


def _build_element_metadata(
    element: Dict[str, Any],
    document_id: str,
    pdf_hash: str,
) -> Dict[str, Any]:
    """
    Build base metadata dictionary for a text or image element.
    
    Args:
        element: The element dictionary from Unstructured
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
    
    Returns:
        Sanitized metadata dictionary with document_id, element_type, and pdf_hash
    """
    element_type = cast_to_str(element.get("type", ""))
    raw_metadata = element.get("metadata") or {}
    metadata = sanitize_metadata(raw_metadata)
    metadata["document_id"] = document_id
    metadata["element_type"] = element_type
    metadata["pdf_hash"] = pdf_hash
    return metadata


def _process_text_elements(
    text_elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
    start_index: int,
) -> tuple[List[str], List[Dict], List[str], List[str], int]:
    """
    Process text chunk elements and build payload components.
    
    Args:
        text_elements: List of text chunk elements from Unstructured
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
        start_index: Starting index for ID counter
    
    Returns:
        Tuple of (ids, metadatas, documents, texts_to_embed, new_index)
    """
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    idx_counter = start_index
    
    logger.info(f"[CHROMA] Processing {len(text_elements)} text chunks")
    
    for element in text_elements:
        metadata = _build_element_metadata(element, document_id, pdf_hash)
        metadata["modality"] = "text"
        
        text = cast_to_str(element.get("text"))
        if not text:
            logger.warning(f"[CHROMA] Text element missing text content, skipping")
            continue
        
        ids.append(f"{document_id}-{idx_counter}")
        metadatas.append(metadata)
        documents.append(text)
        texts_to_embed.append(text)
        idx_counter += 1
    
    logger.info(f"[CHROMA] Added {len(ids)} text chunks to payload")
    return ids, metadatas, documents, texts_to_embed, idx_counter


def _process_captioned_images(
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
    start_index: int,
) -> tuple[List[str], List[Dict], List[str], List[str], int, int, int]:
    """
    Process pre-captioned image elements and build payload components.
    
    Args:
        captioned_images: List of image elements with pre-computed captions
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
        start_index: Starting index for ID counter
    
    Returns:
        Tuple of (ids, metadatas, documents, texts_to_embed, images_added, images_skipped, new_index)
    """
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    idx_counter = start_index
    images_added = 0
    images_skipped = 0
    
    logger.info(f"[CHROMA] Processing {len(captioned_images)} captioned images")
    
    for element in captioned_images:
        metadata = _build_element_metadata(element, document_id, pdf_hash)
        
        # Get pre-computed caption from metadata
        raw_metadata = element.get("metadata") or {}
        caption = raw_metadata.get("image_caption")
        image_b64 = raw_metadata.get("image_base64")
        
        if not caption:
            logger.warning(f"[CHROMA] Image element missing caption, skipping")
            images_skipped += 1
            continue
        
        if not image_b64:
            logger.warning(f"[CHROMA] Image element missing image_base64, skipping")
            images_skipped += 1
            continue
        
        # Image has pre-computed caption, add to payload
        metadata["modality"] = "image"
        metadata["image_b64"] = image_b64
        
        ids.append(f"{document_id}-{idx_counter}")
        metadatas.append(metadata)
        documents.append(caption)
        texts_to_embed.append(caption)
        idx_counter += 1
        images_added += 1
    
    logger.info(f"[CHROMA] Added {images_added} captioned images to payload")
    if images_skipped > 0:
        logger.warning(f"[CHROMA] Skipped {images_skipped} images (missing caption or base64)")
    
    return ids, metadatas, documents, texts_to_embed, images_added, images_skipped, idx_counter


def _generate_embeddings(texts_to_embed: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.
    
    Args:
        texts_to_embed: List of text strings to embed
    
    Returns:
        List of embedding vectors
    """
    embeddings: List[List[float]] = []
    if texts_to_embed:
        logger.info(f"[CHROMA] Generating embeddings for {len(texts_to_embed)} texts")
        embeddings = text_embedder.embed_texts(texts_to_embed)
    return embeddings


def build_chroma_payload(
    text_elements: List[Dict[str, Any]],
    captioned_images: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> Dict[str, List[Any]]:
    """
    Build payload for Chroma from text chunks and pre-captioned images.
    
    This function is purely for data transformation - it does NOT perform
    any ML inference. Captions must be pre-computed by the service layer.
    
    Args:
        text_elements: List of text chunk elements from Unstructured
        captioned_images: List of image elements with pre-computed captions
                         (caption stored in metadata["image_caption"])
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
    
    Returns:
        Dictionary with ids, embeddings, documents, metadatas ready for Chroma
    """
    # Process text elements
    text_ids, text_metadatas, text_documents, text_texts_to_embed, idx_counter = (
        _process_text_elements(text_elements, document_id, pdf_hash, start_index=0)
    )
    
    # Process captioned images
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
    
    # Combine all components
    ids = text_ids + image_ids
    metadatas = text_metadatas + image_metadatas
    documents = text_documents + image_documents
    texts_to_embed = text_texts_to_embed + image_texts_to_embed
    
    # Generate embeddings for all texts
    embeddings = _generate_embeddings(texts_to_embed)
    
    total_elements = len(ids)
    text_count = len(text_ids)
    logger.info(
        f"[CHROMA] Total payload: {total_elements} elements "
        f"({text_count} text + {images_added} images)"
    )
    
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
    """
    Store text chunks and pre-captioned images in Chroma collection.
    
    This function is strictly for database operations. It does NOT perform
    any ML inference (captioning, etc.). All captions must be pre-computed
    by the service layer.
    
    Args:
        text_elements: List of text chunk elements from Unstructured
        captioned_images: List of image elements with pre-computed captions
                         (caption stored in metadata["image_caption"])
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
    
    Returns:
        Total number of elements stored in Chroma
    """
    logger.info(f"[CHROMA] Starting storage for document: {document_id}")
    
    payload = build_chroma_payload(
        text_elements, captioned_images, document_id, pdf_hash
    )
    
    if not payload["ids"]:
        logger.warning(f"[CHROMA] No elements to store for document: {document_id}")
        return 0
    
    # Count modalities before adding
    text_count = sum(1 for m in payload["metadatas"] if m.get("modality") == "text")
    image_count = sum(1 for m in payload["metadatas"] if m.get("modality") == "image")
    
    logger.info(
        f"[CHROMA] Storing {len(payload['ids'])} elements in Chroma: "
        f"{text_count} text + {image_count} image"
    )
    
    collection.add(
        ids=payload["ids"],
        embeddings=payload["embeddings"],
        documents=payload["documents"],
        metadatas=payload["metadatas"],
    )
    
    logger.info(f"[CHROMA] Successfully stored {len(payload['ids'])} elements in Chroma")
    
    return len(payload["ids"])


def semantic_search(
    query: str,
    top_k: int,
) -> List[QueryResultItem]:
    if top_k <= 0:
        top_k = 5

    query_embeddings = text_embedder.embed_texts([query])
    raw = collection.query(
        query_embeddings=query_embeddings,
        n_results=top_k,
    )

    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    results: List[QueryResultItem] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        is_image = meta.get("modality") == "image"
        item = QueryResultItem(
            id=str(meta.get("document_id", "")),
            text=str(doc) if not is_image else "[image]",
            score=float(dist),
            metadata=meta or {},
        )
        results.append(item)

    return results