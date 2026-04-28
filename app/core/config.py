import os

UNSTRUCTURED_URL = os.getenv(
    "UNSTRUCTURED_URL",
    "http://unstructured:8000/general/v0/general",
)

UNSTRUCTURED_CHUNKING_STRATEGY = os.getenv(
    "UNSTRUCTURED_CHUNKING_STRATEGY",
    "by_title",
)
UNSTRUCTURED_MAX_CHARACTERS = int(os.getenv("UNSTRUCTURED_MAX_CHARACTERS", "512"))
UNSTRUCTURED_OVERLAP = int(os.getenv("UNSTRUCTURED_OVERLAP", "30"))

CAPTIONING_AI_BASE_URL = os.getenv("CAPTIONING_AI_BASE_URL")
CAPTIONING_AI_MODEL = os.getenv("CAPTIONING_AI_MODEL")
CAPTIONING_AI_API_KEY = os.getenv("CAPTIONING_AI_API_KEY")
CAPTION_MAX_TOKENS = int(os.getenv("CAPTION_MAX_TOKENS", "256"))
CAPTIONER_PROMPT_PATH = os.getenv("CAPTIONER_PROMPT_PATH", "prompts/captioner.md")

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb-ingestion")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

TEXT_MODEL = os.getenv("TEXT_EMBEDDING_MODEL", "perplexity-ai/pplx-embed-v1-0.6b")

HF_TOKEN = os.getenv("HF_TOKEN")

BASE_NS     = os.getenv("GRAPHDB_BASE_NS", "http://ki4kmu.fhnw.ch/ontology")
GRAPHDB_URL = os.getenv("GRAPHDB_URL", "http://graphdb-ingestion:7200")
GRAPHDB_REPO= os.getenv("GRAPHDB_REPOSITORY", "rag-repo")

PREFIXES = f"""
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>
PREFIX ki4kmu: <{BASE_NS}>
"""

SECTION_EXTRACTOR_URL = os.getenv("SECTION_EXTRACTOR_URL", "http://section-extractor:8003")

UNSTRUCTURED_READ_TIMEOUT = float(os.getenv("UNSTRUCTURED_READ_TIMEOUT", "120.0"))
UNSTRUCTURED_SPLIT_PAGE_SIZE = int(os.getenv("UNSTRUCTURED_SPLIT_PAGE_SIZE", "10"))
UNSTRUCTURED_SPLIT_CONCURRENCY = int(os.getenv("UNSTRUCTURED_SPLIT_CONCURRENCY", "3"))

EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", "/ki4kmu_data/embedding-model")