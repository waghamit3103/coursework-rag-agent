#!/usr/bin/env python
"""Run the Flask API dev server.

If ANTHROPIC_API_KEY isn't set, falls back to a canned fake Claude client
so the API — and a frontend pointed at it — can be manually exercised
end-to-end before a real key is available. This is loudly logged, never
silent, and is a *different, minimal* stand-in from the scripted test
double in tests/fake_anthropic.py (that one is for pytest; this one exists
purely so a human can click around a real browser and see the whole
stack wired up correctly before the real key arrives).

Usage (from backend/, with venv activated):
    python scripts/run_api.py
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.app import create_app
from app.embedding.store import NotesStore
from app.embedding.voyage_client import build_default_embedder

FAKE_ANSWER = (
    "(fake agent response — ANTHROPIC_API_KEY is not set) This is a canned "
    "reply so you can manually verify the API and frontend are wired up "
    "correctly. Set ANTHROPIC_API_KEY in backend/.env and restart for real "
    "answers grounded in your notes."
)


class _DevFakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=FAKE_ANSWER)],
            stop_reason="end_turn",
            stop_details=None,
        )


class _DevFakeClient:
    def __init__(self):
        self.messages = _DevFakeMessages()


def _build_client():
    if os.environ.get("ANTHROPIC_API_KEY"):
        from app.agent.claude_client import build_default_client

        return build_default_client()

    print(
        "WARNING: ANTHROPIC_API_KEY is not set. Using a canned fake agent "
        "client — responses will NOT be real. Set it in backend/.env for "
        "actual grounded answers.\n"
    )
    return _DevFakeClient()


def main() -> None:
    store = NotesStore()
    if store.count() == 0:
        print(
            "No embedded chunks found. Run scripts/run_ingestion.py and "
            "scripts/run_embedding.py first."
        )
        return

    client = _build_client()
    embedder = build_default_embedder()

    app = create_app(client=client, embedder=embedder, store=store)
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
