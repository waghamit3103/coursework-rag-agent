"""Data structures shared by the ingestion pipeline and (later) the retrieval
and embedding stages. Kept dependency-free (stdlib only) so this module can
be imported anywhere without dragging in pypdf/chromadb/etc.
"""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ChunkMetadata:
    """Everything the agent needs to cite a chunk back to its source.

    `section` and `page` are independent fields (not a single combined
    string) so that downstream code — the retrieval filter, the citation
    renderer, the agent's tool results — can each decide how to display or
    filter on them without re-parsing a formatted string.
    """

    course: str
    topic: str
    source_file: str
    chunk_index: int
    chunking_method: str  # "heading" | "heading+fixed_size" | "fixed_size"
    section: Optional[str] = None
    page: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_chroma_metadata(self) -> dict:
        """ChromaDB silently drops any key whose value is None rather than
        erroring — which means a stored chunk's metadata dict ends up
        missing keys unpredictably (present for chunks with a section,
        absent for chunks without one). Stripping None values ourselves,
        explicitly, makes that behavior a documented decision instead of an
        implicit side effect of the vector store's internals.
        """
        return {k: v for k, v in self.to_dict().items() if v is not None}


@dataclass
class Chunk:
    text: str
    metadata: ChunkMetadata

    def to_dict(self) -> dict:
        return {"text": self.text, "metadata": self.metadata.to_dict()}


def chunk_id(chunk: Chunk) -> str:
    """Deterministic, human-readable ID for a chunk's position in the vector
    store: "<course>/<topic>/<source_file>#<chunk_index>". Deterministic so
    re-embedding an unchanged file produces the same IDs (upsert overwrites
    in place rather than duplicating); human-readable so a ChromaDB browser
    or a debug log line is self-explanatory without a join back to the
    source file.
    """
    m = chunk.metadata
    return f"{m.course}/{m.topic}/{m.source_file}#{m.chunk_index}"
