"""Flask app factory. Takes client/embedder/store as arguments rather than
constructing them internally — same dependency-injection pattern used
throughout this codebase (Conversation, run_agent_turn, retrieve all take
their dependencies as arguments) — so tests can inject fakes and get a
real, fully-wired Flask app with zero network calls (see tests/test_api.py).
"""

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from app import config
from app.api.routes import bp
from app.api.sessions import ConversationStore

# Comma-separated list so both a local dev frontend and a deployed one can
# be allowed at once (e.g. testing a deployed backend against `npm run dev`
# locally). Defaults to Vite's dev port — deployment (Stage 9) sets this to
# the actual Vercel URL instead of leaving CORS open to any origin, which
# is what an unset default would otherwise mean.
DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"


def create_app(
    client, embedder, store, raw_notes_dir: Path = config.RAW_NOTES_DIR
) -> Flask:
    app = Flask(__name__)

    origins = os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN).split(",")
    CORS(app, origins=[origin.strip() for origin in origins])

    # 20MB is generous for course notes (.md/.txt/.pdf) while still bounding
    # request size — Flask returns a clean 413 on its own for anything over.
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

    app.config["NOTES_STORE"] = store
    app.config["EMBEDDER"] = embedder
    # Injectable like everything else here, specifically so tests can point
    # uploads at a tmp_path instead of writing into the real backend/data
    # tree (see tests/test_api.py::TestUpload).
    app.config["RAW_NOTES_DIR"] = raw_notes_dir
    app.config["CONVERSATION_STORE"] = ConversationStore(
        client=client, embedder=embedder, store=store
    )

    app.register_blueprint(bp)
    return app
