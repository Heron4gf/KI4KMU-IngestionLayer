# KI-4-KMU Ingestion Layer

This project is part of the [KI-4-KMU initiative](https://www.ki-zentrum.ch/2025/07/03/fhnw-ki-praxisleitfaden-und-ki-canvas-ki-4-kmu-methode/) developed at FHNW, which aims to provide SMEs with practical AI tooling and methodology. This ingestion layer powers the knowledge platform behind the project, enabling document-grounded question answering over domain-specific PDFs.

A Hybrid RAG system combining a Vector Database ([ChromaDB](https://www.trychroma.com/)) and a Knowledge Graph ([GraphDB](https://graphdb.ontotext.com/)) to achieve better retrieval accuracy than traditional single-approach RAG systems. The two approaches complement each other's weaknesses, and results are merged and reranked before being returned. The system prioritizes local deployment and open-weight models wherever possible.

## Architecture

![Architecture](./images/architecture.jpg)

## Why Hybrid?

Neither vector search nor graph search is sufficient on its own:

| | Vector DB | Knowledge Graph |
|---|---|---|
| ✅ Strengths | Semantic understanding, natural language queries | Keyword & keyphrase matching, structured traversal |
| ❌ Weaknesses | Domain-specific terms, exact keyword lookup | Semantic ranking, cross-lingual queries |

A query like *"Give me the engine compression ratio of Chassis 3413GT"* benefits from both: the vector search finds semantically similar sections, while graph traversal retrieves chunks linked to nodes with concepts `chassis` or `compression`. The two result sets are merged and reranked — so the final output is both semantically coherent and keyword-precise. Crucially, the reranker can be swapped at any time without re-ingesting documents.

## Features

- **Async PDF Ingestion**: Upload PDFs and poll for results — no blocking on long-running processing
- **Hybrid Search**: Vector semantic search + graph keyword traversal, merged and reranked
- **Graph Traversal**: Multi-hop concept traversal and concept co-occurrence expansion enrich retrieval beyond what vector search alone can reach
- **Large Candidate Pool**: Each retrieval arm independently fetches up to 50 candidates (tunable via `VECTOR_TOP_K`), then the full merged pool is reranked down to `top_k`
- **Multilingual**: Both the text embedder and reranker support multilingual input
- **Observability**: Full tracing and evaluation support via [Langfuse](https://langfuse.com/)
- **Local-first**: Designed to run fully on-premise using open-weight models; external APIs can be swapped with local inference via [LM Studio](https://lmstudio.ai/) for fully air-gapped deployments.
- **RESTful API**: Clean, versioned REST API with async job conventions
- **Docker**: Fully containerized via Docker Compose

Edges visually connect traversal chunks back to their seed vector sections, telling the multi-hop retrieval story.

## Graph Retrieval Visualizer

A live, step-by-step visualization of the hybrid retrieval pipeline is available at:

**http://localhost:8001/static/graph_viz.html**

After starting the services, enter a query and press **Run** to watch each stage unfold in real time via SSE:

1. **Vector search** — sections with highest embedding similarity
2. **Graph keyword** — chunks matched by concept/keyphrase lookup
3. **Resolve chunks** — vector sections resolved to their constituent text chunks
4. **Graph traversal** — chunks discovered via 2-hop concept and 3-hop co-occurrence hops
5. **Rerank** — final top-k results highlighted in the graph

#### Demo

https://github.com/user-attachments/assets/25fc481c-ed59-4811-9182-c78dda041a5f


## Technologies

| Component | Technology |
|---|---|
| API | [FastAPI](https://fastapi.tiangolo.com/) |
| Vector DB | [ChromaDB](https://www.trychroma.com/) |
| Knowledge Graph | [GraphDB (Ontotext)](https://graphdb.ontotext.com/) |
| Text Embedding | [pplx-embed-v1-0.6B](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b) |
| Section Extraction SLM | [Gemma-4-E4B](https://huggingface.co/google/gemma-4-E4B) |
| Reranking | [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) |
| Observability | [Langfuse](https://langfuse.com/) |
| PDF Parsing | [PyMuPDF4LLM](https://github.com/pymupdf/RAG) |

## Ontology

The system uses a custom RDF/OWL ontology (`ontology/ontology.ttl`) to represent document knowledge in GraphDB. See the full [Ontology Reference](docs/ontology.md) for class definitions, relationships, datatype properties, and example RDF triples.

## Graph Traversal

Concept nodes are **global hubs**: every section across all documents that receives the same concept points to the same single Concept node in GraphDB. This enables two traversal strategies that run on top of vector search results. See the full [Graph Traversal](docs/graph-traversal.md) page for details on 2-hop concept traversal, 3-hop co-occurrence expansion, the retrieval pipeline, and SPARQL query patterns.

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

The API supports PDF ingestion (async with job polling), hybrid search, and SSE-streamed retrieval visualization. See the full [REST API Reference](docs/restapi.md) for detailed endpoint documentation, request/response schemas, and Postman import instructions.

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
