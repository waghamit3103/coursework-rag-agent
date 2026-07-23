#!/usr/bin/env python
"""Interactive CLI chat with the coursework agent. Manual testing tool —
Stage 5 will put a real API + React UI in front of the same Conversation
class this script uses.

Usage (from backend/, with venv activated, both API keys set in .env):
    python scripts/chat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.claude_client import build_default_client
from app.agent.conversation import Conversation
from app.embedding.store import NotesStore
from app.embedding.voyage_client import build_default_embedder


def main() -> None:
    store = NotesStore()
    if store.count() == 0:
        print(
            "No embedded chunks found. Run scripts/run_ingestion.py and "
            "scripts/run_embedding.py first."
        )
        return

    conversation = Conversation(
        client=build_default_client(),
        embedder=build_default_embedder(),
        store=store,
    )

    print("Coursework RAG Agent — type a question, or 'quit' to exit.")
    print(f"Courses available: {', '.join(store.distinct_courses())}")
    print()

    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            break

        result = conversation.send(user_text)

        print()
        print(result.text)
        if result.sources:
            print()
            print(f"Sources ({result.num_tool_calls} search(es)):")
            for s in result.sources:
                print(f"  [{s.score:.3f}] {s.citation()}")
        print()


if __name__ == "__main__":
    main()
