"""The search_notes tool: schema definition + execution.

Design decision — the course_filter enum is derived from the store, not
hardcoded:
`build_search_notes_tool` calls `store.distinct_courses()` to populate the
`course_filter` parameter's JSON Schema `enum`. Hardcoding
["dsa", "operating_systems", "machine_learning", "oop"] would work today,
but it's a second place (besides the actual folder names under
data/raw_notes/) that has to be kept in sync — add a fifth course and
forget to update the enum, and the agent would either reject a valid
filter or (worse) silently accept one that matches nothing. Deriving it
from what's actually been embedded means the tool schema can never drift
from the real data.
"""

from typing import List

from app.embedding.store import NotesStore
from app.retrieval.retriever import RetrievedChunk, retrieve
from app.embedding.voyage_client import VoyageEmbedder

SEARCH_NOTES_TOOL_NAME = "search_notes"


def build_search_notes_tool(store: NotesStore) -> dict:
    courses = store.distinct_courses()

    return {
        "name": SEARCH_NOTES_TOOL_NAME,
        "description": (
            "Search the user's own course notes for relevant passages. "
            "Returns the top matching passages with their source file, "
            "section, and a relevance score. Call this before answering any "
            "question that depends on specific facts, definitions, "
            "algorithms, or examples from the notes — do not answer such "
            "questions from general knowledge alone. You may call this "
            "tool more than once in a turn: once per course for a "
            "question that compares or combines material across courses, "
            "or again with refined search terms if the first results "
            "don't actually address the question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural-language description of what to find in the notes."
                    ),
                },
                "course_filter": {
                    "type": "string",
                    "enum": courses,
                    "description": (
                        "Optional. Restrict the search to one course. Omit "
                        "to search across all courses."
                    ),
                },
            },
            "required": ["query"],
        },
    }


def execute_search_notes(
    tool_input: dict, embedder: VoyageEmbedder, store: NotesStore
) -> tuple[str, List[RetrievedChunk]]:
    """Run the actual retrieval for a search_notes tool call. Returns the
    formatted text to send back as the tool_result content, plus the
    RetrievedChunks (for the caller to accumulate as "sources used" —
    Stage 5's API needs these to render citations, separately from
    whatever text the agent's final answer contains).
    """
    query = tool_input["query"]
    course_filter = tool_input.get("course_filter")

    results = retrieve(query, embedder, store, course_filter=course_filter)
    return _format_results(results), results


def _format_results(results: List[RetrievedChunk]) -> str:
    if not results:
        return (
            "No matching passages found. Try different search terms, "
            "or omit the course filter."
        )

    lines = [f"Found {len(results)} passage(s):", ""]
    for i, r in enumerate(results, start=1):
        lines.append(f"[{i}] score={r.score:.3f} | {r.citation()}")
        lines.append(r.text)
        lines.append("")
    return "\n".join(lines).strip()
