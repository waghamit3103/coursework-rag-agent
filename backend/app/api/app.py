"""Flask app factory. Takes client/embedder/store as arguments rather than
constructing them internally — same dependency-injection pattern used
throughout this codebase (Conversation, run_agent_turn, retrieve all take
their dependencies as arguments) — so tests can inject fakes and get a
real, fully-wired Flask app with zero network calls (see tests/test_api.py).
"""

import os

from flask import Flask
from flask_cors import CORS

from app.api.routes import bp
from app.api.sessions import ConversationStore

# Comma-separated list so both a local dev frontend and a deployed one can
# be allowed at once (e.g. testing a deployed backend against `npm run dev`
# locally). Defaults to Vite's dev port — deployment (Stage 9) sets this to
# the actual Vercel URL instead of leaving CORS open to any origin, which
# is what an unset default would otherwise mean.
DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"


def create_app(client, embedder, store) -> Flask:
    app = Flask(__name__)

    origins = os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN).split(",")
    CORS(app, origins=[origin.strip() for origin in origins])

    app.config["NOTES_STORE"] = store
    app.config["CONVERSATION_STORE"] = ConversationStore(
        client=client, embedder=embedder, store=store
    )

    app.register_blueprint(bp)
    return app
