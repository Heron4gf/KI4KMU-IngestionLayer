# KI-4-KMU Ingestion Layer

This project is part of the [KI-4-KMU initiative](https://www.ki-zentrum.ch/2025/07/03/fhnw-ki-praxisleitfaden-und-ki-canvas-ki-4-kmu-methode/) developed at FHNW, which aims to provide SMEs with practical AI tooling and methodology. This ingestion layer powers the knowledge platform behind the project, enabling document-grounded question answering over domain-specific PDFs.

A Hybrid RAG system combining a Vector Database ([ChromaDB](https://www.trychroma.com/)) and a Knowledge Graph ([GraphDB](https://graphdb.ontotext.com/)) to achieve better retrieval accuracy than traditional single-approach RAG systems. The two approaches complement each other's weaknesses, and results are merged and reranked before being returned. The system prioritizes local deployment and open-weight models wherever possible.

## Architecture

![Architecture](./images/ingestion_layer_structure.png)

## Why Hybrid?

Neither vector search nor graph search is sufficient on its own:

| | Vector DB | Knowledge Graph |
|---|---|---|
| ✅ Strengths | Semantic understanding, natural language queries | Keyword & keyphrase matching, structured traversal |
| ❌ Weaknesses | Domain-specific terms, exact keyword lookup | Semantic ranking, cross-lingual queries |

A query like *"Give me the engine compression ratio of Chassis 3413GT"* benefits from both: the vector search finds semantically similar sections, while graph traversal retrieves chunks linked to nodes tagged with `chassis` or `compression`. The two result sets are merged and reranked by `cohere/rerank-4-pro` — a larger, multilingual embedding model than the one used for ingestion — so the final output is both semantically coherent and keyword-precise. Crucially, the reranker can be swapped at any time without re-ingesting documents.

### Retrieval Examples

![Tag Example](./images/tag_example.png)
![Keyphrase Example](./images/keyphrase_example.png)

## Features

- **Async PDF Ingestion**: Upload PDFs and poll for results — no blocking on long-running processing
- **Hybrid Search**: Vector semantic search + graph keyword traversal, merged and reranked
- **Multilingual Reranking**: `cohere/rerank-4-pro` via OpenRouter handles cross-lingual queries
- **Observability**: Full tracing and evaluation support via [Langfuse](https://langfuse.com/)
- **Local-first**: Designed to run fully on-premise using open-weight models; external APIs are optional and swappable
- **RESTful API**: Clean, versioned REST API with async job conventions
- **Docker**: Fully containerized via Docker Compose

## Technologies

| Component | Technology |
|---|---|
| API | [FastAPI](https://fastapi.tiangolo.com/) |
| Vector DB | [ChromaDB](https://www.trychroma.com/) |
| Knowledge Graph | [GraphDB (Ontotext)](https://graphdb.ontotext.com/) |
| Text Embedding | [pplx-embed-v1-0.6B](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b) |
| Section Extraction SLM | [Gemma-4-9B](https://huggingface.co/google/gemma-4-9b) |
| Reranking | [cohere/rerank-4-pro](https://openrouter.ai/cohere/rerank-4-pro) via OpenRouter |
| Observability | [Langfuse](https://langfuse.com/) |
| PDF Parsing | [PyMuPDF4LLM](https://github.com/pymupdf/RAG) |

> **Note:** The image captioning pipeline supports local inference via [LM Studio](https://lmstudio.ai/) for fully air-gapped deployments.

## Ontology

The system uses a custom RDF/OWL ontology (`ontology/ontology.ttl`) to represent document knowledge in GraphDB.

**Classes:**
- `Document` — an ingested PDF
- `Chunk` — a raw text chunk extracted from a document page
- `Section` — a logical section identified by the SLM within a chunk (subclasses: `Text`, `Image`)
- `Tag` — a retrieval label assigned to a section by the SLM (e.g. `"compression"`, `"GDPR"`)
- `Keyphrase` — a lemmatized keyword algorithmically extracted from section text

**Key relationships:**
- `Chunk` → `belongsTo` → `Document`
- `Section` → `isContained` → `Chunk`
- `Section` → `hasTag` → `Tag`
- `Text` → `hasKeyphrase` → `Keyphrase`

This structure means a query can reach relevant text chunks either by traversing tags/keyphrases (graph path) or by finding the section in the vector DB and then fetching its parent chunk (vector path).

## Installation

### Prerequisites
- [Docker](https://www.docker.com/) and Docker Compose

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd KI4KMU-IngestionLayer
   ```

2. Copy and fill in the environment file:
   ```bash
   cp .env.example .env
   ```

3. Start all services:
   ```bash
   docker-compose up --build
   ```

The API will be available at `http://localhost:8001`. Interactive docs at `http://localhost:8001/docs`.

## REST API

Base URL: `http://localhost:8001/v1`

### `GET /health`
Returns `{ "status": "ok" }` — use this to check the service is up.

---

### `POST /documents` — Ingest a PDF

Upload a PDF for async ingestion. Returns immediately with a job reference.

**Request:** `multipart/form-data`, field `file` (PDF only)

**Response `202 Accepted`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

---

### `GET /jobs/{job_id}` — Poll Job Status

Poll until `status` is `completed` or `failed`. A 2–5 second interval is reasonable.

**Response `200 OK`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "filename": "document.pdf",
  "document_id": "aabbccdd-1234-5678-abcd-000000000000",
  "num_chunks": 15,
  "error": null
}
```

---

### `POST /query` — Hybrid Search

**Request body:**
```json
{
  "query": "engine compression ratio",
  "top_k": 5
}
```

**Response `200 OK`:**
```json
{
  "query": "engine compression ratio",
  "results": [
    {
      "id": "doc-uuid_chunk_3",
      "text": "The compression ratio of Chassis 3413GT is 2.1 bars...",
      "score": 0.94,
      "metadata": {
        "chunk_id": "doc-uuid_chunk_3",
        "section_id": "section-uuid"
      }
    }
  ]
}
```

---

## Ingestion Flow

```
1. POST /v1/documents       → 202 Accepted  { job_id, status_url }
2. GET  /v1/jobs/{job_id}   → poll until status = "completed"
3. POST /v1/query           → hybrid search results
```

## Testing

```bash
# Unit and slice tests
pytest

# All tests including smoke tests (requires running Docker services)
pytest --run-smoke
```
