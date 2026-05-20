# REST API Reference

> **Base URL:** `http://localhost:8001`
>
> **API Version:** 1.0.0

The KI-4-KMU Ingestion Layer exposes a RESTful API for document ingestion, job monitoring, and hybrid search. All endpoints are prefixed with `/v1`.

---

## Table of Contents

- [OpenAPI Specification](#openapi-specification)
- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [Health Check](#1-get-v1health)
  - [Ingest Document](#2-post-v1documents)
  - [Poll Job Status](#3-get-v1jobsjob_id)
  - [Hybrid Search](#4-post-v1query)
  - [Streamed Retrieval (SSE)](#5-get-v1querystream)
- [Ingestion Flow](#ingestion-flow)
- [Error Handling](#error-handling)
- [Job Status Enum](#job-status-enum)
- [Job Stage Enum](#job-stage-enum)

---

## OpenAPI Specification

A complete [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0) specification is available at [`docs/openapi.yml`](../docs/openapi.yml). It can be used to:

- **Auto-generate client code** with tools like [OpenAPI Generator](https://openapi-generator.tech/) or [Orval](https://orval.dev/)
- **Import into Postman** (see below)
- **View interactive docs** at `http://localhost:8001/docs` (Swagger UI, served automatically by FastAPI)
- **View ReDoc** at `http://localhost:8001/redoc`

### Importing into Postman

1. Open Postman and click the **Import** button (top-left)
2. Choose one of the following methods:

   **Method A — File Upload:**
   - Select the **Upload** tab
   - Drag and drop `docs/openapi.yml` (or browse to it)

   **Method B — Link:**
   - Select the **Link** tab
   - Paste the raw file URL or local path

3. Postman will parse the spec and create a new collection named **KI-4-KMU Ingestion API** with all endpoints organized by path
4. Create a new environment (or use Variables) and set:

   | Variable     | Value                   |
   |--------------|-------------------------|
   | `base_url`   | `http://localhost:8001` |
   | `job_id`     | *(empty — auto-filled)* |

5. Select the environment in the top-right dropdown before sending requests

### Importing into Other Tools

| Tool | Instructions |
|------|-------------|
| **Insomnia** | File > Import > Select `docs/openapi.yml` |
| **curl** | Use the spec with `openapi-cli` to generate SDKs |
| **Swagger UI** | Navigate to `http://localhost:8001/docs` when the server is running |

---

## Authentication

This API does not require authentication in development mode. For production deployments, authentication should be configured at the reverse proxy level (e.g., API Gateway, OAuth2).

---

## Endpoints

### 1. GET /v1/health

Returns a simple status indicator to verify the service is running.

**Request**

No request body or parameters.

**Response**

| Status Code | Description |
|-------------|-------------|
| `200 OK` | Service is healthy |
| `503 Service Unavailable` | Service is unhealthy or dependencies are unavailable |

**Example Response**

```json
{
  "status": "ok"
}
```

---

### 2. POST /v1/documents

Upload a PDF for asynchronous ingestion. The endpoint returns immediately with a `job_id` that can be used to poll the processing status.

**Request**

- **Content-Type:** `multipart/form-data`
- **Body:** Single field `file` containing the PDF

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string (binary) | Yes | PDF file to ingest |

**Response**

| Status Code | Description |
|-------------|-------------|
| `202 Accepted` | Acceptance acknowledged; job queued for processing |
| `400 Bad Request` | The uploaded file is not a PDF |
| `422 Unprocessable Entity` | Validation error — no file provided |

**Headers**

| Header | Description | Example |
|--------|-------------|---------|
| `Location` | URL to poll for job status | `/v1/jobs/550e8400-e29b-41d4-a716-446655440000` |

**Example Request**

```bash
curl -X POST http://localhost:8001/v1/documents \
  -F "file=@manual.pdf"
```

**Example Response (202)**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

**Ingestion Pipeline**

When a PDF is uploaded, the system performs the following steps:

1. **PDF Parsing** — PyMuPDF4LLM extracts raw text and images from each page
2. **Section Extraction** — Gemma-4-E4B (SLM) identifies logical sections within each chunk
3. **Text Embedding** — pplx-embed-v1-0.6B generates embeddings for each chunk
4. **Concept Extraction** — SLM assigns retrieval labels (e.g., `"compression"`, `"GDPR"`)
5. **Keyphrase Extraction** — Lemmatized keywords are algorithmically extracted
6. **Co-occurrence Building** — Pairs of co-occurring concepts on the same section are linked
7. **Storage** — Vectors go to ChromaDB; structured data goes to GraphDB

---

### 3. GET /v1/jobs/{job_id}

Poll this endpoint until the job `status` is `completed` or `failed`. A 2–5 second polling interval is recommended.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string (UUID) | Unique identifier of the ingestion job |

**Response**

| Status Code | Description |
|-------------|-------------|
| `200 OK` | Job status retrieved successfully |
| `404 Not Found` | Job not found |

**Example Request**

```bash
curl http://localhost:8001/v1/jobs/550e8400-e29b-41d4-a716-446655440000
```

**Example Response (200 — Completed)**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "stage": "completed",
  "filename": "manual.pdf",
  "document_id": "aabbccdd-1234-5678-abcd-000000000000",
  "num_chunks": 15,
  "error": null
}
```

**Example Response (200 — Processing)**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "stage": "extracting_sections",
  "filename": "manual.pdf",
  "document_id": null,
  "num_chunks": null,
  "error": null
}
```

**Example Response (200 — Failed)**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "stage": "writing_graphdb",
  "filename": "manual.pdf",
  "document_id": null,
  "num_chunks": null,
  "error": "Connection refused to GraphDB"
}
```

---

### 4. POST /v1/query

Execute a hybrid search across both ChromaDB (vector semantic search) and GraphDB (keyword / concept / co-occurrence traversal). Results from both arms are merged, deduplicated, and reranked by Qwen3-Reranker-0.6B.

**Retrieval Pipeline**

| Stage | Source | Description |
|-------|--------|-------------|
| 1 | ChromaDB | Embedding-similar sections (up to `max_vector_results`) |
| 2 | GraphDB | Concept/keyphrase keyword match (up to `max_graph_results`) |
| 3 | GraphDB | 2-hop concept traversal — sections sharing concepts |
| 4 | GraphDB | 3-hop co-occurrence traversal — thematically adjacent sections |
| 5 | Reranker | Qwen3-Reranker-0.6B ranks merged pool to `max_results_total` |

**Request Body**

- **Content-Type:** `application/json`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | **required** | The search query string |
| `top_k` | integer \| null | `null` | Number of final results. Shorthand for `max_results_total` |
| `max_vector_results` | integer | `3` | Maximum candidates from ChromaDB vector search |
| `max_graph_results` | integer | `2` | Maximum candidates from GraphDB keyword search |
| `max_results_total` | integer | `5` | Final number of results after merging and reranking |

**Response**

| Status Code | Description |
|-------------|-------------|
| `200 OK` | Search results returned successfully |
| `400 Bad Request` | Query is empty or whitespace only |
| `422 Unprocessable Entity` | Validation error — no query provided |

**Example Request**

```bash
curl -X POST http://localhost:8001/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "engine compression ratio",
    "top_k": 5
  }'
```

**Example Response (200)**

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
        "section_id": "section-uuid",
        "page_number": 3,
        "source_document": "manual.pdf"
      }
    },
    {
      "id": "doc-uuid_chunk_7",
      "text": "Engine specifications include a compression ratio of 2.0 bars...",
      "score": 0.87,
      "metadata": {
        "chunk_id": "doc-uuid_chunk_7",
        "section_id": "section-uuid-2",
        "page_number": 5,
        "source_document": "manual.pdf"
      }
    }
  ]
}
```

---

### 5. GET /v1/query/stream

Stream the hybrid retrieval pipeline step-by-step using Server-Sent Events (SSE). This endpoint is used by the [Graph Retrieval Visualizer](http://localhost:8001/static/graph_viz.html) to show each retrieval stage in real time.

**Query Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | **required** | Search query string |
| `top_k` | integer | `5` | Number of final results to return after reranking (1–100) |

**Response**

| Status Code | Description |
|-------------|-------------|
| `200 OK` | SSE stream started |
| `400 Bad Request` | Query is empty |

**Event Types**

| Event | Data |
|-------|------|
| `vector_results` | Top sections from ChromaDB vector search |
| `graph_keyword` | Chunks matched by GraphDB keyword search |
| `vector_chunks` | Text chunks resolved from vector sections |
| `traversal` | Chunks discovered via graph traversal |
| `rerank_done` | Final top-k results after reranking |

**Example Request**

```bash
curl -N http://localhost:8001/v1/query/stream?query=engine+compression+ratio\&top_k=5
```

**Example SSE Output**

```
event: vector_results
data: {"nodes": [{"id": "doc-uuid_chunk_3", "label": "doc-uuid_ch", "type": "section", "score": 0.94}]}

event: graph_keyword
data: {"nodes": [{"id": "doc-uuid_chunk_7", "label": "doc-uuid_ch", "type": "kw_chunk"}], "edges": []}

event: vector_chunks
data: {"nodes": [{"id": "doc-uuid_chunk_3", "label": "doc-uuid_ch", "type": "v_chunk"}], "edges": [{"id": "vc_doc-uuid_ch", "source": "section-uuid", "target": "doc-uuid_chunk_3", "via": "contains"}]}

event: traversal
data: {"nodes": [{"id": "doc-uuid_chunk_12", "label": "doc-uuid_ch", "type": "t_chunk"}], "edges": [{"id": "tr_doc-uuid_ch", "source": "doc-uuid_chunk_3", "target": "doc-uuid_chunk_12", "via": "traversal"}]}

event: rerank_done
data: {"top_k": [{"id": "doc-uuid_chunk_3", "score": 0.94, "text_preview": "The compression ratio..."}], "all_ids": [...], "top_ids": ["doc-uuid_chunk_3"]}
```

---

## Ingestion Flow

```
1. POST /v1/documents       → 202 Accepted  { job_id, status_url }
2. GET  /v1/jobs/{job_id}   → poll until status = "completed" or "failed"
3. POST /v1/query           → hybrid search results
4. GET  /v1/query/stream    → SSE events for graph visualizer
```

---

## Error Handling

All error responses follow a consistent format:

```json
{
  "detail": "Human-readable error description"
}
```

For validation errors (422), the format follows FastAPI's standard:

```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

---

## Job Status Enum

| Value | Description |
|-------|-------------|
| `pending` | Job has been created but not yet started |
| `processing` | Job is currently being processed |
| `completed` | Job finished successfully |
| `failed` | Job encountered an error |

---

## Job Stage Enum

| Value | Description |
|-------|-------------|
| `upload_received` | File upload acknowledged |
| `chunking_text` | Text extraction from PDF pages |
| `extracting_images` | Image extraction from PDF pages |
| `storing_chunks` | Storing text chunks in ChromaDB |
| `extracting_sections` | Running SLM section extraction |
| `writing_graphdb` | Writing structured data to GraphDB |
| `completed` | All stages finished successfully |
| `failed` | A stage encountered an error |
