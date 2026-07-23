"""Factory for the real Anthropic client — mirrors
embedding.voyage_client.build_default_embedder: reads the key from the
environment (populated from backend/.env via config.py) rather than every
call site needing to know where it lives.
"""

import os


def build_default_client():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to "
            "backend/.env and fill in your Anthropic key."
        )
    return anthropic.Anthropic(api_key=api_key)
