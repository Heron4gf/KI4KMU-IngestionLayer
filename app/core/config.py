import os

UNSTRUCTURED_URL = os.getenv(
    "UNSTRUCTURED_URL",
    "http://unstructured:8000/general/v0/general",
)

UNSTRUCTURED_CHUNKING_STRATEGY = os.getenv(
    "UNSTRUCTURED_CHUNKING_STRATEGY",
    "by_title",
)
UNSTRUCTURED_MAX_CHARACTERS = int(os.getenv("UNSTRUCTURED_MAX_CHARACTERS", "1000"))
UNSTRUCTURED_OVERLAP = int(os.getenv("UNSTRUCTURED_OVERLAP", "150"))

CAPTIONING_AI_BASE_URL = os.getenv("CAPTIONING_AI_BASE_URL", "http://host.docker.internal:1234/v1")
CAPTIONING_AI_MODEL = os.getenv("CAPTIONING_AI_MODEL", "lmstudio-community/Qwen3.5-0.8B-GGUF")
CAPTIONING_AI_API_KEY = os.getenv("CAPTIONING_AI_API_KEY", "dummy")
CAPTION_MAX_TOKENS = int(os.getenv("CAPTION_MAX_TOKENS", "256"))
CAPTIONER_PROMPT_PATH = os.getenv("CAPTIONER_PROMPT_PATH", "prompts/describe_image.md")

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

TEXT_MODEL = os.getenv("TEXT_EMBEDDING_MODEL", "perplexity-ai/pplx-embed-v1-0.6b")

HF_TOKEN = os.getenv("HF_TOKEN")

BASE_NS     = os.getenv("GRAPHDB_BASE_NS", "http://pdf-ingestion/ontology/")
GRAPHDB_URL = os.getenv("GRAPHDB_URL", "http://graphdb:7200")
GRAPHDB_REPO= os.getenv("GRAPHDB_REPOSITORY", "pdf-ingestion")

PREFIXES = f"""
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX pi:   <{BASE_NS}>
"""

LANGEXTRACT_URL = os.getenv("LANGEXTRACT_URL", "http://langextract:8003")