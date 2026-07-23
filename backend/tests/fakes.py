"""Test doubles shared across the embedding test modules. Kept separate
from any single test file since both test_voyage_client.py and
test_embedding_pipeline.py need a fake Voyage client.
"""

from dataclasses import dataclass, field
from typing import List


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
