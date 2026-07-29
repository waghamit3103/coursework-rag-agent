# Coursework RAG Agent

**Live demo:** https://coursework-rag-agent.vercel.app
(Backend API: https://coursework-rag-agent-1.onrender.com/api/health)

> Both the frontend and backend are on free tiers, so the backend spins
> down after ~15 min idle. First message after that can take up to a
> minute (Render waking up, plus re-bootstrapping the vector store since
> the free tier's disk doesn't persist — see
> [ARCHITECTURE.md](ARCHITECTURE.md#deployment-stage-9)). It's not
> broken, just cold. Everything after that first message is normal
> speed.

> 📸 Screenshot/GIF placeholder — need to add one at
> `docs/demo-screenshot.png` and link it here. A cross-course comparison
> question ("compare BST insertion with round robin scheduling
> fairness") shows the multi-search behavior best, so probably use that.

An agentic RAG app for querying your own class notes (Data Structures &
Algorithms, Operating Systems, Machine Learning, OOP) through a chat
interface, with grounded, cited answers. Claude decides when to search,
checks whether what came back actually answers the question, and
re-queries if it doesn't. So it's an agent that has a retrieval tool,
not a retrieve-then-generate pipeline that always runs the same steps.



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

Requires Python 3.11+ (I built this against 3.13) and Node 18+ (built
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

`backend/data/raw_notes/` ships with synthetic sample notes (not real
course material) covering all four courses in all three supported
formats, so you can run the whole pipeline out of the box:

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

Add your own notes under `backend/data/raw_notes/<course>/<topic>/` — the
top two directory levels are the `course` and `topic` metadata, so there's
no config file to keep in sync with your folder structure. Supported:
`.md`, `.txt`, `.pdf`.

## Run ingestion

```bash
cd backend
python scripts/run_ingestion.py
```

Chunks every file under `data/raw_notes/` and writes
`data/processed/chunks.jsonl` (one JSON object per chunk: `text` +
`metadata`), plus a per-course, per-method summary to stdout. Against the
bundled sample notes this currently produces 32 chunks (29 heading-based,
3 fixed-size fallback for the one unstructured `.txt` file).

## Run embedding

Requires `VOYAGE_API_KEY` in `backend/.env` (see Setup above).

```bash
cd backend
python scripts/run_embedding.py
```

Embeds every chunk from `data/processed/chunks.jsonl` with Voyage AI's
`voyage-3-large` — one batched API call for the whole set, not one per
file (see [ARCHITECTURE.md](ARCHITECTURE.md#embedding--storage-stage-2)
for why that matters) — and persists to a ChromaDB collection at
`data/chroma/`. Safe to re-run: each file's existing chunks get deleted
before its current chunks are re-inserted, so editing a note and
re-running replaces that note's vectors instead of duplicating them.

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
core function: it embeds the query (`input_type="query"`), searches
ChromaDB (optionally scoped to one course via `course_filter`), and
returns `RetrievedChunk` objects with a cosine-similarity `score` and a
`.citation()` method. `retrieve_with_defaults(...)` above just builds the
real embedder/store for you — the agent tool and the API construct those
once and call `retrieve()` directly instead.

## Chat with the agent

Requires both API keys set and embeddings already built.

```bash
cd backend
python scripts/chat.py
```

Try something that needs the notes ("what's the difference between mutual
exclusion and hold-and-wait in deadlocks?"), a multi-hop question that
should trigger more than one search ("compare BST insertion with how
round robin scheduling handles fairness"), or something the notes don't
cover — it should say so instead of answering from general knowledge.
Sources used get printed under each answer.

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
canned-response agent (it logs loudly when it does this) so you can
exercise the whole stack — routing, CORS, sessions, the React UI — before
you have a real key. Set the key and restart for real answers.

## Run with Docker

Requires both API keys in `backend/.env`. Unlike `run_api.py`, this path
fails loudly instead of falling back to a canned agent (see
[ARCHITECTURE.md](ARCHITECTURE.md#docker--docker-compose-stage-7)).

```bash
docker compose up --build
# backend:  http://localhost:5000
# frontend: http://localhost:5173
```

First run with no existing `backend/data/chroma/` bootstraps
automatically: the backend container chunks and embeds `data/raw_notes/`
(baked into the image) before starting the server. Later runs skip
straight to serving, reusing whatever's already been embedded on the
host. Health check: `curl http://localhost:5000/api/health`.

## Run tests

```bash
cd backend
pytest
```

111 tests, 100% line coverage across `app/`, enforced via
`--cov-fail-under=90` in `pytest.ini`. I didn't chase 100% for its own
sake — it just kept surfacing real gaps as I went, including a PDF
heading-detection branch I'd only ever checked by hand, and a "reader"
round-trip test that turned out to be calling `json.loads()` directly
instead of the function it was supposed to test. Full list in
[ARCHITECTURE.md](ARCHITECTURE.md#test-suite-hardening-stage-6).

(No frontend test framework yet — see ARCHITECTURE.md for why, and how I
verified the UI instead.)

## Lint

```bash
cd backend
ruff check app scripts tests wsgi.py
ruff format --check app scripts tests wsgi.py   # drop --check to reformat in place

cd ../frontend
npm run lint
```

Both run on every push and PR — [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Design decisions

Full reasoning is in [ARCHITECTURE.md](ARCHITECTURE.md#design-decisions).
Short version:

**Chunking.** Heading-aware for Markdown (splits at `#`/`##`/`###`,
ignoring headings inside fenced code blocks), falling back to a
word-count sliding window with overlap for unstructured text and for any
single heading section that's too large. PDFs are chunked per page,
trying heading detection first (some course PDFs are exports of
already-structured notes) and falling back to fixed-size per page.
Sizing is word-based rather than token-based — it's a simpler,
dependency-free proxy, and exact token counts don't matter for chunk
boundaries, just "roughly one concept per chunk."

**Metadata.** `course`, `topic`, `source_file`, `section` (heading path,
when detected), `page` (for PDFs), `chunk_index`, `chunking_method` — kept
as separate fields rather than one formatted citation string, so
downstream code can filter or render them independently.

**Embedding.** `input_type="document"` for stored chunks vs.
`input_type="query"` at search time, per Voyage's asymmetric-embedding
recommendation. One ChromaDB collection with `course`/`topic` as
metadata rather than one collection per course, so the course filter is
actually optional. API calls are batched across the whole set of chunks
being embedded, not one call per file — an earlier per-file version hit
Voyage's reduced rate limit for accounts without a payment method on
file, which is why this is called out specifically rather than just
assumed as best practice.

**Retrieval.** ChromaDB's collection is explicitly configured for cosine
distance — I checked that the default is actually squared L2, not
cosine, by testing hand-constructed vectors — and converted to an
interpretable cosine-similarity score. Ranking correctness is
unit-tested against hand-computed vector geometry (a `ScriptedVoyageClient`
test double), not just "did it return something."

**Agent loop.** Hand-written rather than the SDK's beta Tool Runner,
because the point of this project was understanding how the loop works,
and a helper that hides it works against that. The loop itself just runs
whatever tool calls Claude asks for until Claude stops asking — the
"evaluate results, re-query with refined terms if they're weak, search
once per course for a multi-course question" behavior comes entirely
from the system prompt (`agent/prompts.py`), not from harness code
inspecting scores. The `search_notes` tool's `course_filter` enum is
derived from the vector store's actual contents so it can't drift from
what's really in `data/raw_notes/`.

**API/frontend.** `create_app(client, embedder, store)` takes its
dependencies as arguments, same as every layer below it — that's what let
the whole stack, including the real React UI in a real browser, get
built and manually verified before the Anthropic key even existed.
Conversation state is a plain in-memory dict keyed by `conversation_id`,
which is fine for a single-instance deployment and not meant to scale
past that. There's no manual course-filter control in the UI; letting the
agent decide when to use it is the whole point.

**Docker.** Multi-stage builds for both images, so the compiler/Node
toolchain never ships in the final image. `wsgi.py` fails loudly on a
missing key; the local dev script falls back to a canned agent instead.
Found a real bug while testing the fresh-bootstrap path with an empty
mounted directory: mounting a volume at the whole `data/` directory
shadows `data/raw_notes/` baked into the image at build time — it doesn't
just overlay it. Fixed by mounting only the derived subdirectories
(`data/chroma/`, `data/processed/`). Full story in ARCHITECTURE.md.

**CI.** Added `ruff` for backend linting/formatting (there was none
before this). Confirmed the pytest suite needs zero repository secrets by
hiding `.env` entirely and re-running it, so the workflow behaves the
same on a fork's PR. Ran the workflow locally with
[`act`](https://github.com/nektos/act) before pushing it, rather than
trusting the YAML on faith.

**Deployment.** Render (backend, Docker) + Vercel (frontend, static).
CORS is restricted to the real deployed frontend origin via
`FRONTEND_ORIGIN`, not left wide open. Render's free tier has no
persistent disk, so the entrypoint's auto-bootstrap from Stage 7
(chunk + embed if the store is empty) ends up doing double duty as the
fix for that, rather than being a separate piece of work. Two real
deployment bugs along the way, both in ARCHITECTURE.md: an env variable
name typo, and a CORS change that needed an actual process restart, not
just a saved dashboard setting.
