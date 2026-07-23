"""Central place for paths and chunking constants.

Keeping these as plain module-level constants (rather than a settings class
or env-driven config) is a deliberate stage-1 choice: there's nothing here
yet that needs to vary per-environment. Later stages (Flask API, Docker) can
introduce env-var overrides without this module's call sites changing.
"""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
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
