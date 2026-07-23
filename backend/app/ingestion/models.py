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


@dataclass
class Chunk:
    text: str
    metadata: ChunkMetadata

    def to_dict(self) -> dict:
        return {"text": self.text, "metadata": self.metadata.to_dict()}
