"""Thin wrapper around the Voyage AI client: batching (so a large notes
collection doesn't get sent as one oversized request), retry with backoff
(so a transient network blip or rate-limit response doesn't fail the whole
ingestion run), and the query/document input_type distinction Voyage
recommends for retrieval quality.

Design decision — input_type="document" vs "query":
Voyage's embedding models support an optional `input_type` hint that tells
the model whether the text being embedded is a stored document or a search
query. Using it is an asymmetric-embedding technique: documents and queries
get slightly different embedding treatment tuned for the retrieval task,
rather than embedding both the same way and just comparing raw cosine
similarity. Skipping this (embedding queries with input_type="document",
or omitting it entirely) still works, but leaves retrieval quality on the
table for free — it costs nothing extra to set correctly. So: every chunk
stored in Stage 2 is embedded with input_type="document"; queries in
Stage 3 (retrieval) must use input_type="query".

Design decision — dependency-injected client:
VoyageEmbedder takes a `client` object satisfying the same interface as
voyageai.Client (an `.embed(texts, model=..., input_type=..., ...)` method
returning an object with `.embeddings` and `.total_tokens`) rather than
constructing its own client internally. This lets tests inject a fake
client and exercise batching/retry logic with zero network calls and zero
Voyage API cost — see tests/test_voyage_client.py.
"""

import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from app import config


class EmbedResult(Protocol):
    embeddings: List[List[float]]
    total_tokens: int


class VoyageClientProtocol(Protocol):
    def embed(
        self,
        texts: List[str],
        model: str,
        input_type: str,
        output_dimension: int,
    ) -> EmbedResult: ...


@dataclass
class EmbeddingBatchStats:
    embeddings: List[List[float]]
    total_tokens: int


class VoyageEmbeddingError(RuntimeError):
    """Raised when a batch fails on every retry attempt."""


class VoyageEmbedder:
    def __init__(
        self,
        client: VoyageClientProtocol,
        model: str = config.VOYAGE_MODEL,
        output_dimension: int = config.VOYAGE_OUTPUT_DIMENSION,
        batch_size: int = config.VOYAGE_EMBED_BATCH_SIZE,
        max_retries: int = config.VOYAGE_MAX_RETRIES,
        retry_backoff_seconds: float = config.VOYAGE_RETRY_BACKOFF_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._client = client
        self._model = model
        self._output_dimension = output_dimension
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._sleep_fn = sleep_fn

    def embed_documents(self, texts: List[str]) -> EmbeddingBatchStats:
        """Embed a list of chunk texts for storage. Batches internally so
        callers don't need to think about Voyage's per-request limits.
        """
        all_embeddings: List[List[float]] = []
        total_tokens = 0

        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            result = self._embed_batch_with_retry(batch, input_type="document")
            all_embeddings.extend(result.embeddings)
            total_tokens += result.total_tokens

        return EmbeddingBatchStats(embeddings=all_embeddings, total_tokens=total_tokens)

    def embed_query(self, text: str) -> List[float]:
        """Embed a single search query. Always input_type="query" — see
        module docstring for why this matters.
        """
        result = self._embed_batch_with_retry([text], input_type="query")
        return result.embeddings[0]

    def _embed_batch_with_retry(self, texts: List[str], input_type: str) -> EmbedResult:
        delay = self._retry_backoff_seconds
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return self._client.embed(
                    texts,
                    model=self._model,
                    input_type=input_type,
                    output_dimension=self._output_dimension,
                )
            except Exception as exc:  # noqa: BLE001 — see module docstring
                last_exc = exc
                if attempt == self._max_retries:
                    break
                self._sleep_fn(delay)
                delay *= 2

        raise VoyageEmbeddingError(
            f"Voyage embed call failed after {self._max_retries} attempt(s)"
        ) from last_exc


def build_default_embedder() -> VoyageEmbedder:
    """Factory for the CLI/app entry points. Reads the API key from the
    environment (populated from backend/.env via config.py's load_dotenv
    call) rather than requiring every caller to know where the key lives.
    """
    import voyageai

    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set. Copy backend/.env.example to "
            "backend/.env and fill in your Voyage AI key."
        )
    client = voyageai.Client(api_key=api_key)
    return VoyageEmbedder(client=client)
