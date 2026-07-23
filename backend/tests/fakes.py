"""Test doubles shared across the embedding and retrieval test modules.
Kept separate from any single test file since several test files need a
fake Voyage client.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FakeEmbedResult:
    embeddings: List[List[float]]
    total_tokens: int


@dataclass
class FakeVoyageClient:
    """Duck-types voyageai.Client's .embed() interface.

    Deterministic embedding scheme: each text's embedding is [len(text)] —
    trivial to predict in assertions, and distinct enough per-text to
    verify that batched results are reassembled in the right order.

    fail_times: raise a RuntimeError on the first N calls (across all
    input_types), then succeed — used to test VoyageEmbedder's retry logic
    without a real flaky network call.
    """

    fail_times: int = 0
    calls: List[dict] = field(default_factory=list)
    _call_count: int = field(default=0, init=False)

    def embed(
        self, texts: List[str], model: str, input_type: str, output_dimension: int
    ) -> FakeEmbedResult:
        self._call_count += 1
        self.calls.append(
            {
                "texts": list(texts),
                "model": model,
                "input_type": input_type,
                "output_dimension": output_dimension,
            }
        )
        if self._call_count <= self.fail_times:
            raise RuntimeError("simulated transient Voyage API failure")

        return FakeEmbedResult(
            embeddings=[[float(len(t))] for t in texts],
            total_tokens=sum(len(t.split()) for t in texts),
        )


@dataclass
class ScriptedVoyageClient:
    """Duck-types voyageai.Client's .embed() interface, returning a
    caller-specified embedding per exact text match.

    Unlike FakeVoyageClient's automatic length-based scheme (which is
    fine for testing batching/retry plumbing but produces 1-D embeddings
    where cosine similarity is trivially 1.0 for any two same-sign
    vectors — useless for testing ranking), this lets a test construct
    real multi-dimensional vectors with deliberate angular relationships,
    so retrieval-ranking assertions ("chunk A should outrank chunk B for
    this query") are testing genuine cosine-similarity behavior rather
    than coincidence.
    """

    embeddings_by_text: Dict[str, List[float]]
    calls: List[dict] = field(default_factory=list)

    def embed(
        self, texts: List[str], model: str, input_type: str, output_dimension: int
    ) -> FakeEmbedResult:
        self.calls.append(
            {
                "texts": list(texts),
                "model": model,
                "input_type": input_type,
                "output_dimension": output_dimension,
            }
        )
        missing = [t for t in texts if t not in self.embeddings_by_text]
        if missing:
            raise KeyError(
                f"ScriptedVoyageClient has no embedding scripted for: {missing}"
            )

        return FakeEmbedResult(
            embeddings=[self.embeddings_by_text[t] for t in texts],
            total_tokens=sum(len(t.split()) for t in texts),
        )
