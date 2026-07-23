"""Shared test helpers. `make_embedder` is the one piece of setup that was
byte-for-byte identical across every test module that needs a
VoyageEmbedder wrapping a fake client — extracted here rather than left
duplicated eight times over.

Not a pytest fixture: it takes an argument (the fake client to wrap),
which fixtures can't do without a factory-fixture layer of indirection
that would add a parameter to every test function for no real benefit
here. A plain imported function is simpler for something this small.
"""

from app.embedding.voyage_client import VoyageEmbedder


def make_embedder(client) -> VoyageEmbedder:
    return VoyageEmbedder(client=client, batch_size=128, max_retries=1, retry_backoff_seconds=0.0)
