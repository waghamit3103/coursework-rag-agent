# Coursework RAG Agent

An agentic RAG application for querying your own class notes (Data Structures &
Algorithms, Operating Systems, Machine Learning, OOP) through a chat interface,
with grounded, cited answers. Claude decides when to search, evaluates whether
results actually answer the question, and re-queries when they don't — this is
an agent with a retrieval tool, not a fixed retrieve-then-generate pipeline.

**Status:** Stage 8 of 10 complete (ingestion/chunking + embedding/vector
storage + retrieval + agent loop + Flask API/React frontend + hardened
pytest suite + Docker/docker-compose + CI). See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full design and the build plan.

## Project layout

```
backend/
  app/
    config.py              # paths, chunking constants, Voyage/Chroma/Claude constants
    ingestion/
      models.py             # Chunk / ChunkMetadata, chunk_id()
      loaders.py             # .md / .txt / .pdf -> raw text
      chunking.py            # heading-aware + fixed-size chunkers
      pipeline.py             # ties loaders + chunkers together, walks data/raw_notes/
    embedding/
      voyage_client.py       # VoyageEmbedder: batching + retry over the Voyage API
      store.py                # NotesStore: ChromaDB persistence, course-filterable query
      pipeline.py              # embed_and_store(): ties embedder + store together
    retrieval/
      retriever.py            # retrieve(query, course_filter?): embed + search + rank
    agent/
      tools.py                # search_notes tool schema + execution
      prompts.py               # system prompt (the "evaluate & re-query" behavior lives here)
      loop.py                   # run_agent_turn(): the hand-written tool-use loop
      conversation.py            # Conversation: multi-turn history across calls
      claude_client.py            # builds the real Anthropic client from ANTHROPIC_API_KEY
    api/
      app.py                   # create_app(client, embedder, store) Flask factory
      routes.py                 # /api/chat, /api/courses, /api/health
      sessions.py                # ConversationStore: in-memory, keyed by conversation_id
  scripts/
    run_ingestion.py        # CLI: chunk everything, write data/processed/chunks.jsonl
    run_embedding.py         # CLI: embed chunks.jsonl, persist to data/chroma/
    chat.py                   # CLI: interactive chat with the agent
    run_api.py                 # Flask dev server (falls back to a canned agent if no key yet)
  tests/
    fixtures/                # sample .md / .txt / .pdf used by the test suite
    fakes.py                  # FakeVoyageClient + ScriptedVoyageClient (no network in tests)
    fake_anthropic.py          # FakeAnthropicClient (scripted Claude responses, no network)
    test_chunking.py / test_loaders.py / test_pipeline.py / test_models.py
    test_voyage_client.py / test_store.py / test_embedding_pipeline.py
    test_retriever.py
    test_agent_tools.py / test_loop.py / test_conversation.py
    test_api.py / test_sessions.py
  data/
    raw_notes/<course>/<topic>/   # sample notes ship here (see below)
    processed/                     # chunks.jsonl output (gitignored)
    chroma/                         # ChromaDB persistence (gitignored)
  Dockerfile                 # multi-stage: build deps, then a slim runtime image
  docker-entrypoint.sh         # auto-bootstraps the vector store on first run
  wsgi.py                       # production entry point (gunicorn wsgi:app)
frontend/
  src/
    api.js                   # fetch wrapper for the Flask API
    App.jsx                    # renders <Chat />
    components/
      Chat.jsx                  # message list + input, holds all chat state
      MessageBubble.jsx           # one message (user or assistant)
      SourceList.jsx               # citations + scores under an assistant message
      LoadingIndicator.jsx          # "thinking" indicator while awaiting a response
  Dockerfile                # multi-stage: Vite build, then served by nginx
docker-compose.yml          # backend + frontend together for local dev
.github/workflows/
  ci.yml                     # lint + test (backend), lint + build (frontend), on every push/PR
```

## Setup

Requires Python 3.11+ (developed against 3.13) and Node 18+ (developed
against Node 24).

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
# then edit .env and set VOYAGE_API_KEY (https://dashboard.voyageai.com)
# and ANTHROPIC_API_KEY (https://console.anthropic.com)
```

```bash
cd frontend
npm install
```

## Notes data

`backend/data/raw_notes/` ships with synthetic sample notes (not real course
material) covering all four courses, in all three supported formats, so the
pipeline is runnable and demoable out of the box:

```
backend/data/raw_notes/
  dsa/
    trees/binary_search_trees.md         (heading-based chunking)
    sorting/sorting_algorithms.md         (heading-based chunking)
  operating_systems/
    scheduling/cpu_scheduling.md          (heading-based chunking)
    deadlocks/deadlock_notes.txt          (fixed-size fallback, no headings)
  machine_learning/
    supervised_learning/linear_regression.md
  oop/
    design_patterns/factory_pattern.pdf   (per-page chunking, real headings
                                            in the extracted PDF text)
```

Add your own notes the same way, under `backend/data/raw_notes/<course>/<topic>/`
— the top two directory levels *are* the `course` and `topic` metadata, so
there's no separate config file to keep in sync with your folder structure.
Supported formats: `.md`, `.txt`, `.pdf`.

## Run ingestion

```bash
cd backend
python scripts/run_ingestion.py
```

This chunks every file under `data/raw_notes/` and writes
`data/processed/chunks.jsonl` (one JSON object per chunk: `text` +
`metadata`), plus a per-course, per-method summary to stdout. Against the
bundled sample notes this currently produces 32 chunks (29 heading-based,
3 fixed-size fallback for the one unstructured `.txt` file).

## Run embedding

Requires `VOYAGE_API_KEY` set in `backend/.env` (see Setup above).

```bash
cd backend
python scripts/run_embedding.py
```

Embeds every chunk from `data/processed/chunks.jsonl` with Voyage AI's
`voyage-3-large` (one batched API call for the whole set, not one per file
— see [ARCHITECTURE.md](ARCHITECTURE.md#embedding--storage-stage-2) for why
that matters) and persists to a ChromaDB collection at `data/chroma/`.
Safe to re-run: each file's existing chunks are deleted before its current
chunks are re-inserted, so re-running after editing a note replaces that
note's vectors rather than duplicating or orphaning them.

## Try retrieval

Requires embeddings to already exist (see "Run embedding" above).

```bash
cd backend
python -c "
from app.retrieval.retriever import retrieve_with_defaults
for r in retrieve_with_defaults('why does an unbalanced BST hurt performance?', n_results=3):
    print(f'{r.score:.4f}  {r.citation()}')
"
```

`retrieve(query, embedder, store, course_filter=None, n_results=5)` is the
core function — it embeds the query (`input_type="query"`), searches
ChromaDB (optionally scoped to one course via `course_filter`), and returns
`RetrievedChunk` objects with a cosine-similarity `score` and a
`.citation()` method for display. `retrieve_with_defaults(...)` above is
just a convenience wrapper that builds the real embedder/store for you —
Stage 4's agent tool and Stage 5's API will construct those once and call
`retrieve()` directly instead.

## Chat with the agent

Requires both API keys set and embeddings already built (steps above).

```bash
cd backend
python scripts/chat.py
```

Ask something that needs the notes ("what's the difference between
mutual exclusion and hold-and-wait in deadlocks?"), a multi-hop question
that should trigger more than one search ("compare BST insertion with how
round robin scheduling handles fairness"), or something the notes don't
cover — the agent should say so rather than answer from general
knowledge. Sources used are printed under each answer.

## Run the full app (API + frontend)

```bash
# Terminal 1 — backend
cd backend
python scripts/run_api.py            # http://localhost:5000

# Terminal 2 — frontend
cd frontend
npm run dev                          # http://localhost:5173
```

If `ANTHROPIC_API_KEY` isn't set yet, `run_api.py` falls back to a
canned-response agent (loudly logged, never silent) so the whole stack —
routing, CORS, session handling, the React UI — can be exercised end to
end before the real key exists. Set the key and restart for real,
grounded answers.

## Run with Docker

Requires both API keys in `backend/.env` (this path — unlike
`run_api.py` — fails loudly rather than falling back to a canned agent;
see [ARCHITECTURE.md](ARCHITECTURE.md#docker--docker-compose-stage-7)).

```bash
docker compose up --build
# backend:  http://localhost:5000
# frontend: http://localhost:5173
```

First run with no existing `backend/data/chroma/` bootstraps
automatically — the backend container chunks and embeds
`data/raw_notes/` (baked into the image) before starting the server.
Subsequent runs skip straight to serving, reusing whatever's already been
embedded on the host. Backend health: `curl http://localhost:5000/api/health`.

## Run tests

```bash
cd backend
pytest
```

111 tests, 100% line coverage across `app/`, enforced (`--cov-fail-under=90`
in `pytest.ini` — a bare `pytest` run always measures and enforces this,
including in CI). Coverage was measured deliberately, not chased as a
vanity number: it surfaced real gaps, including a PDF heading-detection
branch that had only ever been manually verified and a "reader" function
whose round-trip test was quietly calling `json.loads()` directly instead
of the function it was meant to test. See
[ARCHITECTURE.md](ARCHITECTURE.md#test-suite-hardening-stage-6) for the
full list and what each one turned out to be.

(No frontend test framework yet — see
[ARCHITECTURE.md](ARCHITECTURE.md#flask-api--react-frontend-stage-5) for
why, and how the UI was verified instead.)

## Lint

```bash
cd backend
ruff check app scripts tests wsgi.py
ruff format --check app scripts tests wsgi.py   # --check omitted: reformats in place

cd ../frontend
npm run lint
```

Both run automatically on every push and pull request —
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Design decisions

See [ARCHITECTURE.md](ARCHITECTURE.md#design-decisions) for the full
reasoning — short version:

- **Chunking**: heading-aware for Markdown (splits at `#`/`##`/`###`,
  ignoring headings inside fenced code blocks), falling back to a
  word-count sliding window with overlap for unstructured text and for
  any single heading section that's too large. PDFs are chunked per page,
  attempting heading detection first (some course PDFs are exports of
  already-structured notes) and falling back to fixed-size per page.
- **Sizing is word-based, not token-based** — a stable, dependency-free,
  deterministic proxy; exact token counts aren't needed for chunk
  boundaries, only "roughly one concept per chunk."
- **Metadata**: `course`, `topic`, `source_file`, `section` (heading path,
  when detected), `page` (for PDFs), `chunk_index`, `chunking_method` — kept
  as separate structured fields (not one formatted citation string) so
  downstream code can filter or render them independently.
- **Embedding**: `input_type="document"` for stored chunks vs.
  `input_type="query"` at search time (Voyage's asymmetric-embedding
  recommendation — free retrieval-quality improvement, easy to silently get
  wrong). One ChromaDB collection with `course`/`topic` as metadata, not one
  collection per course, so an optional course filter is genuinely optional.
  Voyage API calls are batched across the whole set of chunks being
  embedded (not one call per file) — an earlier per-file version hit
  Voyage's reduced rate limit for accounts without a payment method on
  file, which is documented in ARCHITECTURE.md as a real lesson, not a
  hypothetical one.
- **Retrieval**: ChromaDB's collection is explicitly configured for cosine
  distance (confirmed the default is actually squared L2, not cosine, by
  testing hand-constructed vectors) and converted to an interpretable
  cosine-similarity score. Ranking correctness is unit-tested with
  hand-computed vector geometry (a `ScriptedVoyageClient` test double), not
  just "did it return something."
- **Agent loop**: hand-written, not the SDK's beta Tool Runner — the point
  of this project is being able to explain how the loop works, which a
  helper that hides it would work against. The loop itself is deliberately
  "dumb": it runs whatever tool calls Claude asks for until Claude stops
  asking. The actual "evaluate results, re-query with refined terms if
  they're weak, search once per course for a multi-course question"
  behavior is the model's own judgment, driven entirely by the system
  prompt (`agent/prompts.py`) — not by harness code that inspects scores
  and second-guesses the model. The `search_notes` tool's `course_filter`
  enum is derived from the vector store's actual contents rather than
  hardcoded, so it can't drift from what's really in `data/raw_notes/`.
- **API/frontend**: Flask's `create_app(client, embedder, store)` takes
  its dependencies as arguments, same as every layer below it — which is
  what let the entire stack (including the real React UI, in a real
  browser) get built and manually verified before the Anthropic key
  existed. Conversation state is a plain in-memory dict keyed by
  `conversation_id` — a deliberate, documented scope boundary for a
  single-instance deployment, not an oversight. No manual course-filter
  control in the UI: the agent deciding when to use it autonomously is
  the point of the project.
- **Docker**: multi-stage builds for both images (compiler/Node toolchain
  never ships in the final image). Production (`wsgi.py`) fails loudly on
  a missing key; the local dev script falls back to a canned agent — a
  deliberate difference, not an inconsistency. Found a real bug by
  actually testing the fresh-bootstrap path with an empty mounted
  directory: mounting a volume at the whole `data/` directory shadows
  `data/raw_notes/` baked into the image at build time, not just overlays
  it. Fixed by mounting only the derived subdirectories
  (`data/chroma/`, `data/processed/`) — see ARCHITECTURE.md for the full
  story.
- **CI**: added `ruff` for backend linting/formatting (the project had
  none before this stage); confirmed the entire pytest suite needs zero
  repository secrets by hiding `.env` entirely and re-running it, which
  is why the workflow works identically on a fork's pull request. The
  workflow itself was run locally with [`act`](https://github.com/nektos/act)
  before ever being pushed, rather than trusting the YAML on faith.

## Coming next

- Stage 9+: deployment, evaluation script.
