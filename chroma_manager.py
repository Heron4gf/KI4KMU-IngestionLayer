import logging
import os
from typing import Any, Dict, List, Optional

import torch
import chromadb
from PIL import Image
from sentence_transformers import SentenceTransformer
from openai import OpenAI

from models import QueryResultItem
from utils import cast_to_str, sanitize_metadata, image_to_b64, get_image_path
import base64
import io


logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

TEXT_MODEL = os.getenv("TEXT_EMBEDDING_MODEL", "perplexity-ai/pplx-embed-v1-0.6b")

LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://host.docker.internal:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "lmstudio-community/Qwen3.5-0.8B-GGUF")
CAPTION_MAX_TOKENS = int(os.getenv("CAPTION_MAX_TOKENS", "256"))


class TextEmbedder:
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


class Captioner:
    def __init__(self):
        self._client = OpenAI(base_url=LMSTUDIO_URL, api_key="dummy")

    def caption(self, image: Image.Image) -> str:
        b64 = image_to_b64(image)
        response = self._client.chat.completions.create(
            model=LMSTUDIO_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in detail. If it contains charts, tables, or diagrams, explain what they show.",
                        },
                    ],
                }
            ],
            max_tokens=CAPTION_MAX_TOKENS,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()


text_embedder = TextEmbedder()
captioner = Captioner()

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
collection = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)


def document_already_ingested(pdf_hash: str) -> bool:
    res = collection.get(where={"pdf_hash": pdf_hash}, limit=1)
    return len(res.get("ids", [])) > 0


def build_chroma_payload(
    text_elements: List[Dict[str, Any]],
    image_elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> Dict[str, List[Any]]:
    """
    Build payload for Chroma from text chunks and image elements.
    
    Args:
        text_elements: List of text chunk elements from Unstructured
        image_elements: List of raw image elements from Unstructured (with base64)
        document_id: Unique identifier for the document
        pdf_hash: MD5 hash of the PDF file
    
    Returns:
        Dictionary with ids, embeddings, documents, metadatas ready for Chroma
    """
    ids: List[str] = []
    metadatas: List[Dict] = []
    documents: List[str] = []
    texts_to_embed: List[str] = []
    
    idx_counter = 0
    
    # Process text elements first
    logger.info(f"[CHROMA] Processing {len(text_elements)} text chunks")
    for element in text_elements:
        element_type = cast_to_str(element.get("type", ""))
        raw_metadata = element.get("metadata") or {}
        metadata = sanitize_metadata(raw_metadata)
        metadata["document_id"] = document_id
        metadata["element_type"] = element_type
        metadata["pdf_hash"] = pdf_hash
        
        text = cast_to_str(element.get("text"))
        if not text:
            logger.warning(f"[CHROMA] Text element missing text content, skipping")
            continue
        
        metadata["modality"] = "text"
        
        ids.append(f"{document_id}-{idx_counter}")
        metadatas.append(metadata)
        documents.append(text)
        texts_to_embed.append(text)
        idx_counter += 1
    
    logger.info(f"[CHROMA] Added {len(text_elements)} text chunks to payload")
    
    # Process image elements
    logger.info(f"[CHROMA] Processing {len(image_elements)} raw images")
    images_with_caption = 0
    images_skipped = 0
    
    for element in image_elements:
        element_type = cast_to_str(element.get("type", ""))
        raw_metadata = element.get("metadata") or {}
        metadata = sanitize_metadata(raw_metadata)
        metadata["document_id"] = document_id
        metadata["element_type"] = element_type
        metadata["pdf_hash"] = pdf_hash
        
        # Get base64 from metadata (provided by extract_images_with_unstructured)
        image_b64 = raw_metadata.get("image_base64")
        
        if not image_b64:
            logger.warning(f"[CHROMA] Image element missing image_base64, skipping")
            images_skipped += 1
            continue
        
        # Decode base64 to image
        try:
            img_data = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
        except Exception as e:
            logger.warning(f"[CHROMA] Failed to decode image base64: {e}, skipping")
            images_skipped += 1
            continue
        
        # Generate caption using VLM
        try:
            caption = captioner.caption(img)
            if not caption:
                logger.warning(f"[CHROMA] Caption generation returned empty, skipping image")
                images_skipped += 1
                continue
            logger.debug(f"[CHROMA] Generated caption: {caption[:100]}...")
        except Exception as e:
            logger.warning(f"[CHROMA] Caption generation failed: {e}, skipping image")
            images_skipped += 1
            continue
        
        # Image successfully processed
        metadata["modality"] = "image"
        metadata["image_b64"] = image_b64
        
        ids.append(f"{document_id}-{idx_counter}")
        metadatas.append(metadata)
        documents.append(caption)  # Caption becomes the document text
        texts_to_embed.append(caption)  # Embed the caption, not the raw image
        idx_counter += 1
        images_with_caption += 1
    
    logger.info(
        f"[CHROMA] Added {images_with_caption} images with captions to payload"
    )
    logger.info(
        f"[CHROMA] Images skipped: {images_skipped} (no base64: {images_skipped > 0})"
    )
    
    # Generate embeddings for all texts (both text chunks and image captions)
    embeddings: List[List[float]] = []
    if texts_to_embed:
        logger.info(f"[CHROMA] Generating embeddings for {len(texts_to_embed)} texts")
        embeddings = text_embedder.embed_texts(texts_to_embed)
    
    total_elements = len(ids)
    logger.info(
        f"[CHROMA] Total payload: {total_elements} elements "
        f"({len(text_elements)} text + {images_with_caption} images)"
    )
    
    return {
        "ids": ids,
        "embeddings": embeddings,
        "documents": documents,
        "metadatas": metadatas,
    }


def store_chunks_in_chroma(
    text_elements: List[Dict[str, Any]],
    image_elements: List[Dict[str, Any]],
    document_id: str,
    pdf_hash: str,
) -> int:
    """
    Store text chunks and images in Chroma collection.
    
    This function:
    1. Builds payload from both text and image elements
    2. Embeds everything with text_embedder (pplx-embed)
    3. Stores in a single collection
    4. Returns total number of stored elements
    """
    logger.info(f"[CHROMA] Starting storage for document: {document_id}")
    
    payload = build_chroma_payload(
        text_elements, image_elements, document_id, pdf_hash
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