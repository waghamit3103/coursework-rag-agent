#!/bin/sh
# Bootstraps the vector store on first run (chunks + embeds
# data/raw_notes/ if the store is still empty — e.g. a fresh container
# with no persisted data/chroma/ volume) then hands off to gunicorn.
# Safe to run on every container start: embed_and_store deletes and
# re-inserts per source file, so re-running against an already-populated
# store is a no-op cost-wise beyond the emptiness check itself.
set -e

python -c "
from app.embedding.store import NotesStore
import sys
sys.exit(0 if NotesStore().count() > 0 else 1)
" || {
  echo "No embedded chunks found -- running ingestion and embedding..."
  python scripts/run_ingestion.py
  python scripts/run_embedding.py
}

exec gunicorn --workers 2 --bind 0.0.0.0:5000 --access-logfile - wsgi:app
