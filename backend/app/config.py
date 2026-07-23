"""Central place for paths and chunking constants.

Keeping these as plain module-level constants (rather than a settings class
or env-driven config) is a deliberate stage-1 choice: there's nothing here
yet that needs to vary per-environment. Later stages (Flask API, Docker) can
introduce env-var overrides without this module's call sites changing.
"""

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env once, here, so every module that imports config (which
# is effectively every module in this app) has API keys available in
# os.environ without each call site needing its own load_dotenv() call.
load_dotenv(BACKEND_DIR / ".env")
DATA_DIR = BACKEND_DIR / "data"
RAW_NOTES_DIR = DATA_DIR / "raw_notes"
PROCESSED_DIR = DATA_DIR / "processed"
CHUNKS_JSONL_PATH = PROCESSED_DIR / "chunks.jsonl"

# --- Chunking parameters (word-based, not token-based — see chunking.py
# module docstring for why) ---

# Target size for a fixed-size chunk.
CHUNK_SIZE_WORDS = 300

# Words shared between consecutive fixed-size chunks, so a fact split across
# a chunk boundary still appears whole in at least one chunk.
CHUNK_OVERLAP_WORDS = 50

# A markdown/PDF section detected via headings is kept as a single chunk if
# it's at or under this size. Above it, we sub-chunk with the fixed-size
# splitter (see chunk_markdown in chunking.py) so no single chunk gets huge.
MAX_SECTION_WORDS = 450

# If a trailing fixed-size window would be smaller than this, it's merged
# into the previous chunk instead of being emitted as its own tiny sliver.
MIN_CHUNK_WORDS = 40

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}

# --- Stage 2: embedding + vector storage ---

CHROMA_PERSIST_DIR = DATA_DIR / "chroma"
CHROMA_COLLECTION_NAME = "course_notes"

VOYAGE_MODEL = "voyage-3-large"
# Fixed explicitly rather than left to the API default: voyage-3-large
# supports 256/512/1024/2048-dim output via the output_dimension param.
# 1024 is Voyage's own recommended balance of retrieval quality vs.
# storage/compute cost for a general-purpose corpus like course notes.
VOYAGE_OUTPUT_DIMENSION = 1024
# Conservative default — well under Voyage's per-request text-count limit.
# At this project's scale (tens to low hundreds of chunks) most files embed
# in a single batch; the batching logic exists so this doesn't fall over
# if a much larger notes collection is ingested later.
VOYAGE_EMBED_BATCH_SIZE = 128
VOYAGE_MAX_RETRIES = 3
VOYAGE_RETRY_BACKOFF_SECONDS = 1.0
