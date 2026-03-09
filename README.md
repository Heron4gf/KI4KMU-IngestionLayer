# PDF Ingestion API

A FastAPI-based REST API for ingesting PDF documents and performing semantic search queries using ChromaDB as the vector database.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Building](#building)
- [Running](#running)
- [REST API Endpoints](#rest-api-endpoints)
- [Docker Deployment](#docker-deployment)
- [Project Structure](#project-structure)

## Features

- **PDF Ingestion**: Upload PDF documents that are automatically chunked and stored in a vector database
- **Semantic Search**: Perform semantic queries across ingested documents
- **Duplicate Detection**: Automatically detects and prevents duplicate document ingestion using MD5 hashing
- **RESTful API**: Clean, versioned REST API endpoints
- **Docker Support**: Full Docker and Docker Compose support for easy deployment

## Architecture
![Architecture](./image.png)

### Vector Database Configuration

The system utilizes **two separate vector spaces** in ChromaDB for optimal performance and precision:

| Vector Space | Embedding Model | Purpose |
|--------------|-----------------|---------|
| **Images** | [SigLip 2](https://huggingface.co/blog/siglip2) | Image embeddings for visual content analysis |
| **Text** | [pplx-embed-v1-0.6B](https://huggingface.co/perplexity-ai/pplx-embed-v1-4b) | Text embeddings for semantic search |

This dual-space architecture provides:
- **Scalability**: Independent scaling of image and text processing pipelines
- **Precision**: Specialized embedding models optimized for their respective content types, ensuring the highest accuracy for each modality

## Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- Docker and Docker Compose

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd IngestionLayer
   ```

3. [Build](#building)
4. [Run](#running)


## Building

### Build Docker Image

```bash
# Build the Docker image
docker build -t pdf-ingestion-api .

# Build with specific tag
docker build -t pdf-ingestion-api:latest .
```

### Build Using Docker Compose

```bash
docker-compose build
```

## Running

### Using Docker

```bash
# Run the container
docker run -d -p 8001:8001 -v $(pwd)/chroma-data:/app/chroma-data --name pdf-ingestion-api pdf-ingestion-api
```

### Using Docker Compose

```bash
# Start the services
docker-compose up
```

## REST API Endpoints

Base URL: `http://localhost:8001/v1`

### Health Check

Check if the API is running and healthy.

| Method | Endpoint | Status Code |
|--------|----------|-------------|
| GET | `/health` | 200 OK |


**Example Response:**
```json
{
  "status": "ok"
}
```

---

### Ingest Document

Upload a PDF document for processing and storage in the vector database.

| Method | Endpoint | Status Code |
|--------|----------|-------------|
| POST | `/documents` | 201 Created |


**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | UploadFile | Yes | PDF file to ingest (application/pdf) |

**Success Response (201 Created):**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "num_chunks": 15
}
```

**Error Responses:**

| Status Code | Description |
|-------------|-------------|
| 400 Bad Request | The uploaded file must be a PDF |
| 409 Conflict | This document has already been ingested |
| 422 Unprocessable Entity | No chunks were stored for this document |

**400 Bad Request Example:**
```json
{
  "detail": "The uploaded file must be a PDF."
}
```

**409 Conflict Example:**
```json
{
  "detail": "This document has already been ingested."
}
```

**422 Unprocessable Entity Example:**
```json
{
  "detail": "No chunks were stored for this document."
}
```

---

### Query Documents

Perform semantic search across ingested documents.

| Method | Endpoint | Status Code |
|--------|----------|-------------|
| POST | `/query` | 200 OK |


**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| query | string | Yes | - | The search query text |
| top_k | integer | No | 5 | Number of results to return |

**Success Response (200 OK):**
```json
{
  "query": "machine learning algorithms",
  "results": [
    {
      "id": "chunk-uuid-1",
      "text": "Machine learning is a subset of artificial intelligence...",
      "score": 0.95,
      "metadata": {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "pdf_hash": "abc123def456"
      }
    },
    {
      "id": "chunk-uuid-2",
      "text": "Deep learning algorithms have revolutionized...",
      "score": 0.87,
      "metadata": {
        "document_id": "550e8400-e29b-41d4-a716-446655440000",
        "pdf_hash": "abc123def456"
      }
    }
  ]
}
```

**Error Responses:**

| Status Code | Description |
|-------------|-------------|
| 400 Bad Request | Query must not be empty |

**400 Bad Request Example:**
```json
{
  "detail": "Query must not be empty."
}
```

---

## Docker Deployment

### Dockerfile Configuration

The Dockerfile is configured with:
- Python 3.11 slim base image
- Port 8001 exposed
- Automatic ChromaDB data persistence via volume mounting

### Docker Compose Configuration

The `docker-compose.yml` defines:
- Service name: `pdf-ingestion-api`
- Port mapping: 8001:8001
- Volume persistence for ChromaDB data
- Build context: current directory

## Project Structure

```
IngestionLayer/
├── app.py                 # FastAPI application with REST endpoints
├── chroma_manager.py      # ChromaDB vector database operations
├── models.py              # Pydantic data models
├── unstructured_manager.py# PDF parsing with Unstructured.io
├── utils.py               # Utility functions (file handling, hashing)
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
├── .gitignore            # Git ignore patterns
├── .dockerignore         # Docker ignore patterns
├── README.md             # This documentation
├── uploads/              # Temporary upload storage (auto-created)
└── chroma-data/          # ChromaDB persistent storage (auto-created)
```

## API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc
