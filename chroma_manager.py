import os
from typing import Any, Dict, List, Optional

import torch
import chromadb
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoProcessor

from models import QueryResultItem
from utils import cast_to_str, sanitize_metadata, image_to_b64, get_image_path


CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

TEXT_COLLECTION = os.getenv("CHROMA_TEXT_COLLECTION", "documents_text")
IMAGE_COLLECTION = os.getenv("CHROMA_IMAGE_COLLECTION", "documents_image")

TEXT_MODEL = os.getenv("TEXT_EMBEDDING_MODEL", "perplexity-ai/pplx-embed-v1-0.6b")
IMAGE_MODEL = os.getenv("IMAGE_EMBEDDING_MODEL", "google/siglip2-so400m-patch14-384")


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


class ImageEmbedder:
    def __init__(self, model_id: str = IMAGE_MODEL):
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModel.from_pretrained(model_id).eval()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)

    def embed_images(self, images: List[Image.Image]) -> List[List[float]]:
        inputs = self._processor(images=images, return_tensors="pt").to(self._device)
        with torch.no_grad():
            output = self._model.get_image_features(**inputs)
            features = output if isinstance(output, torch.Tensor) else output.pooler_output
        features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features.cpu().tolist()


text_embedder = TextEmbedder()
image_embedder = ImageEmbedder()

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

text_collection = chroma_client.get_or_create_collection(name=TEXT_COLLECTION)
image_collection = chroma_client.get_or_create_collection(name=IMAGE_COLLECTION)


def document_already_ingested(pdf_hash: str) -> bool:
    res_text = text_collection.get(where={"pdf_hash": pdf_hash}, limit=1)
    if len(res_text.get("ids", [])) > 0:
        return True
    res_image = image_collection.get(where={"pdf_hash": pdf_hash}, limit=1)
    return len(res_image.get("ids", [])) > 0


def build_chroma_payload(
    elements: List[Dict[str, Any]], document_id: str, pdf_hash: str
) -> Dict[str, Dict[str, List[Any]]]:
    text_ids: List[str] = []
    text_metadatas: List[Dict] = []
    text_documents: List[str] = []
    texts_to_embed: List[str] = []

    image_ids: List[str] = []
    image_metadatas: List[Dict] = []
    image_documents: List[str] = []
    images_to_embed: List[Image.Image] = []

    for idx, element in enumerate(elements):
        element_type = cast_to_str(element.get("type", ""))
        raw_metadata = element.get("metadata") or {}
        metadata = sanitize_metadata(raw_metadata)
        metadata["document_id"] = document_id
        metadata["element_type"] = element_type
        metadata["pdf_hash"] = pdf_hash

        if element_type == "Image":
            image_path = get_image_path(element)
            if not image_path:
                continue
            try:
                img = Image.open(image_path).convert("RGB")
            except Exception:
                continue
            metadata["modality"] = "image"
            image_ids.append(f"{document_id}-{idx}")
            image_metadatas.append(metadata)
            image_documents.append(image_to_b64(img))
            images_to_embed.append(img)
        else:
            text = cast_to_str(element.get("text"))
            if not text:
                continue
            metadata["modality"] = "text"
            text_ids.append(f"{document_id}-{idx}")
            text_metadatas.append(metadata)
            text_documents.append(text)
            texts_to_embed.append(text)

    text_embeddings: List[List[float]] = []
    image_embeddings: List[List[float]] = []

    if texts_to_embed:
        text_embeddings = text_embedder.embed_texts(texts_to_embed)

    if images_to_embed:
        image_embeddings = image_embedder.embed_images(images_to_embed)

    return {
        "text": {
            "ids": text_ids,
            "embeddings": text_embeddings,
            "documents": text_documents,
            "metadatas": text_metadatas,
        },
        "image": {
            "ids": image_ids,
            "embeddings": image_embeddings,
            "documents": image_documents,
            "metadatas": image_metadatas,
        },
    }


def store_chunks_in_chroma(
    elements: List[Dict[str, Any]], document_id: str, pdf_hash: str
) -> int:
    payload = build_chroma_payload(elements, document_id, pdf_hash)

    text_payload = payload["text"]
    image_payload = payload["image"]

    total = 0

    if text_payload["ids"]:
        text_collection.add(
            ids=text_payload["ids"],
            embeddings=text_payload["embeddings"],
            documents=text_payload["documents"],
            metadatas=text_payload["metadatas"],
        )
        total += len(text_payload["ids"])

    if image_payload["ids"]:
        image_collection.add(
            ids=image_payload["ids"],
            embeddings=image_payload["embeddings"],
            documents=image_payload["documents"],
            metadatas=image_payload["metadatas"],
        )
        total += len(image_payload["ids"])

    return total


def semantic_search(
    query: str,
    top_k: int,
    query_image_path: Optional[str] = None,
) -> List[QueryResultItem]:
    if top_k <= 0:
        top_k = 5

    results: List[QueryResultItem] = []

    if query_image_path:
        img = Image.open(query_image_path).convert("RGB")
        query_embeddings = image_embedder.embed_images([img])
        raw_image = image_collection.query(
            query_embeddings=query_embeddings,
            n_results=top_k,
        )
        image_documents = raw_image.get("documents", [[]])[0]
        image_metadatas = raw_image.get("metadatas", [[]])[0]
        image_distances = raw_image.get("distances", [[]])[0]

        for doc, meta, dist in zip(image_documents, image_metadatas, image_distances):
            item = QueryResultItem(
                id=str(meta.get("document_id", "")),
                text="[image]",
                score=float(dist),
                metadata=meta or {},
            )
            results.append(item)
    else:
        query_embeddings = text_embedder.embed_texts([query])
        raw_text = text_collection.query(
            query_embeddings=query_embeddings,
            n_results=top_k,
        )

        text_documents = raw_text.get("documents", [[]])[0]
        text_metadatas = raw_text.get("metadatas", [[]])[0]
        text_distances = raw_text.get("distances", [[]])[0]

        for doc, meta, dist in zip(text_documents, text_metadatas, text_distances):
            item = QueryResultItem(
                id=str(meta.get("document_id", "")),
                text=str(doc),
                score=float(dist),
                metadata=meta or {},
            )
            results.append(item)

    return results
