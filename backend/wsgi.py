"""Production WSGI entry point — what gunicorn actually imports
(`gunicorn wsgi:app`). Separate from scripts/run_api.py, which is the dev
server with the no-key fake-agent fallback: a production process should
fail loudly at startup if a real key is missing, not silently degrade to
canned responses.
"""

from app.agent.claude_client import build_default_client
from app.api.app import create_app
from app.embedding.store import NotesStore
from app.embedding.voyage_client import build_default_embedder

app = create_app(
    client=build_default_client(),
    embedder=build_default_embedder(),
    store=NotesStore(),
)
