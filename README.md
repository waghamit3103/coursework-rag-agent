# Coursework RAG Agent

An agentic RAG application for querying your own class notes (Data Structures &
Algorithms, Operating Systems, Machine Learning, OOP) through a chat interface,
with grounded, cited answers. Claude decides when to search, evaluates whether
results actually answer the question, and re-queries when they don't — this is
an agent with a retrieval tool, not a fixed retrieve-then-generate pipeline.

**Status:** Stage 1 of 10 complete (ingestion + chunking pipeline). See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full design and the build plan.

## Project layout

```
backend/
  app/
    config.py              # paths + chunking constants
    ingestion/
      models.py             # Chunk / ChunkMetadata dataclasses
      loaders.py             # .md / .txt / .pdf -> raw text
      chunking.py            # heading-aware + fixed-size chunkers
      pipeline.py             # ties loaders + chunkers together, walks data/raw_notes/
  scripts/
    run_ingestion.py        # CLI: chunk everything, write data/processed/chunks.jsonl
  tests/
    fixtures/                # sample .md / .txt / .pdf used by the test suite
    test_chunking.py
    test_loaders.py
    test_pipeline.py
  data/
    raw_notes/<course>/<topic>/   # put your own notes here (gitignored)
    processed/                     # chunks.jsonl output (gitignored)
frontend/                    # React chat UI (Stage 5)
.github/workflows/           # CI (Stage 8)
```

## Setup

Requires Python 3.11+ (developed against 3.13).

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
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

## Run tests

```bash
cd backend
pytest -q
```

## Design decisions (Stage 1)

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

## Coming next

- Stage 2: embed chunks with Voyage AI `voyage-3-large`, persist to ChromaDB.
- Stage 3: standalone retrieval (testable without the agent loop).
- Stage 4: agent loop — Claude decides when to call `search_notes`, evaluates
  results, and re-queries for multi-hop questions.
- Stage 5+: Flask API, React chat UI, full pytest suite, Docker, CI,
  deployment, evaluation script.
