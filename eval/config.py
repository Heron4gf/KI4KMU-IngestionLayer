import os

# --- Ingestion API ---
INGESTION_API_URL = os.environ["INGESTION_API_URL"]  # e.g. http://api:8001

# --- LLM judge (Gemma 4 E2B, OpenAI-compatible endpoint) ---
GEMMA_BASE_URL = os.environ.get("GEMMA_BASE_URL", "http://86.119.83.67:8003/v1")
GEMMA_API_KEY = os.environ.get("GEMMA_API_KEY", "no-key")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-e2b-it")

# --- Confident AI ---
CONFIDENT_AI_KEY = os.environ["CONFIDENT_AI_KEY"]

# --- Dataset ---
DATASET_NAME = "llmware/rag_instruct_benchmark_tester"
DATASET_SPLIT = os.environ.get("EVAL_DATASET_SPLIT", "train")
# How many dataset rows to evaluate (set to 0 for all)
EVAL_LIMIT = int(os.environ.get("EVAL_LIMIT", "200"))

# --- Ingestion batching ---
INGEST_BATCH_SIZE = int(os.environ.get("EVAL_INGEST_BATCH_SIZE", "50"))

# --- Retrieval top-k ---
TOP_K = int(os.environ.get("EVAL_TOP_K", "5"))

# --- Checkpoints (all written to STATE_DIR, which should be bind-mounted) ---
STATE_DIR = os.environ.get("EVAL_STATE_DIR", "/app/state")
CHECKPOINT_INGEST = f"{STATE_DIR}/phase1_ingest.jsonl"
CHECKPOINT_RETRIEVE = f"{STATE_DIR}/phase2_retrieve.jsonl"
CHECKPOINT_GENERATE = f"{STATE_DIR}/phase3_generate.jsonl"
CHECKPOINT_SCORE_HYBRID = f"{STATE_DIR}/phase4_score_hybrid.jsonl"
CHECKPOINT_SCORE_VECTOR = f"{STATE_DIR}/phase4_score_vector.jsonl"
