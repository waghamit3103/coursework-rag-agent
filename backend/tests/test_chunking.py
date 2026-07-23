from app.ingestion.chunking import (
    chunk_markdown,
    fixed_size_chunks,
    split_markdown_into_sections,
)


class TestSplitMarkdownIntoSections:
    def test_no_headings_produces_single_rootless_section(self):
        sections = split_markdown_into_sections("just some plain text\nmore text")
        assert len(sections) == 1
        assert sections[0].heading_path == []
        assert "just some plain text" in sections[0].content

    def test_single_heading(self):
        text = "# Title\n\nSome content here."
        sections = split_markdown_into_sections(text)
        assert len(sections) == 1
        assert sections[0].heading_path == ["Title"]
        assert sections[0].content == "Some content here."

    def test_nested_headings_build_path(self):
        text = (
            "# Trees\n"
            "intro text\n"
            "## Binary Search Trees\n"
            "bst text\n"
            "### Traversal\n"
            "traversal text\n"
        )
        sections = split_markdown_into_sections(text)
        paths = [s.heading_path for s in sections]
        assert paths == [
            ["Trees"],
            ["Trees", "Binary Search Trees"],
            ["Trees", "Binary Search Trees", "Traversal"],
        ]

    def test_sibling_headings_reset_stack(self):
        text = "# A\n## A1\ncontent\n# B\ncontent\n"
        sections = split_markdown_into_sections(text)
        paths = [s.heading_path for s in sections]
        assert paths == [["A", "A1"], ["B"]]

    def test_heading_in_fenced_code_block_is_not_a_heading(self):
        text = (
            "# Real Heading\n"
            "```python\n"
            "# not a heading, just a comment\n"
            "x = 1\n"
            "```\n"
            "trailing text\n"
        )
        sections = split_markdown_into_sections(text)
        assert len(sections) == 1
        assert sections[0].heading_path == ["Real Heading"]
        assert "not a heading, just a comment" in sections[0].content

    def test_content_before_first_heading_is_kept(self):
        text = "preamble line\n# First Heading\nbody\n"
        sections = split_markdown_into_sections(text)
        assert sections[0].heading_path == []
        assert sections[0].content == "preamble line"
        assert sections[1].heading_path == ["First Heading"]

    def test_empty_sections_are_dropped(self):
        # A heading immediately followed by another heading with no content
        # in between shouldn't produce an empty chunk.
        text = "# A\n## B\ncontent under B\n"
        sections = split_markdown_into_sections(text)
        assert len(sections) == 1
        assert sections[0].heading_path == ["A", "B"]


class TestFixedSizeChunks:
    def test_short_text_returns_single_chunk(self):
        text = " ".join(f"word{i}" for i in range(10))
        chunks = fixed_size_chunks(
            text, chunk_size_words=100, overlap_words=10, min_chunk_words=5
        )
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_returns_no_chunks(self):
        assert fixed_size_chunks("", 100, 10, 5) == []
        assert fixed_size_chunks("   \n  ", 100, 10, 5) == []

    def test_exact_multiple_splits_evenly_with_overlap(self):
        words = [f"w{i}" for i in range(20)]
        text = " ".join(words)
        chunks = fixed_size_chunks(
            text, chunk_size_words=10, overlap_words=2, min_chunk_words=1
        )
        # step = 8: windows are [0:10], [8:18], [16:20]... but last window
        # ([16:20], 4 words) is below min_chunk_words=1? no, 4 >= 1, so it
        # stays separate. Verify overlap between consecutive chunks.
        assert chunks[0].split() == words[0:10]
        assert chunks[1].split() == words[8:18]

    def test_overlap_words_present_in_consecutive_chunks(self):
        words = [f"w{i}" for i in range(30)]
        text = " ".join(words)
        chunks = fixed_size_chunks(
            text, chunk_size_words=10, overlap_words=3, min_chunk_words=1
        )
        for i in range(len(chunks) - 1):
            tail = chunks[i].split()[-3:]
            head = chunks[i + 1].split()[:3]
            assert tail == head

    def test_small_trailing_window_merged_into_previous_chunk(self):
        # 25 words, chunk_size=10, overlap=2 -> step=8 -> windows at
        # 0-10, 8-18, 16-25 (last window has 9 words: 16..24). Use a size
        # that forces a genuinely tiny trailing window instead.
        words = [f"w{i}" for i in range(22)]
        text = " ".join(words)
        # step = 10 - 2 = 8; windows: [0:10], [8:18], [16:22] -> last has 6 words
        chunks = fixed_size_chunks(
            text, chunk_size_words=10, overlap_words=2, min_chunk_words=8
        )
        # last window (6 words) < min_chunk_words (8) -> merged into previous
        assert len(chunks) == 2
        assert chunks[-1].split()[-6:] == words[-6:]

    def test_rejects_overlap_not_smaller_than_chunk_size(self):
        import pytest

        with pytest.raises(ValueError):
            fixed_size_chunks(
                "a b c", chunk_size_words=5, overlap_words=5, min_chunk_words=1
            )


class TestChunkMarkdown:
    def test_small_section_stays_whole(self):
        text = "# Title\n\nShort content."
        results = chunk_markdown(
            text,
            chunk_size_words=300,
            overlap_words=50,
            max_section_words=450,
            min_chunk_words=40,
        )
        assert len(results) == 1
        chunk_text, section, method = results[0]
        assert chunk_text == "Short content."
        assert section == "Title"
        assert method == "heading"

    def test_oversized_section_is_sub_chunked_but_keeps_section_label(self):
        big_content = " ".join(f"word{i}" for i in range(1000))
        text = f"# Big Section\n\n{big_content}"
        results = chunk_markdown(
            text,
            chunk_size_words=300,
            overlap_words=50,
            max_section_words=450,
            min_chunk_words=40,
        )
        assert len(results) > 1
        for _, section, method in results:
            assert section == "Big Section"
            assert method == "heading+fixed_size"

    def test_headingless_document_falls_back_to_fixed_size_via_none_section(self):
        text = " ".join(f"word{i}" for i in range(500))
        results = chunk_markdown(
            text,
            chunk_size_words=300,
            overlap_words=50,
            max_section_words=450,
            min_chunk_words=40,
        )
        assert len(results) > 1
        for _, section, method in results:
            assert section is None
            assert method == "heading+fixed_size"

    def test_multiple_sections_each_chunked_independently(self):
        text = "# One\ncontent one\n# Two\ncontent two\n"
        results = chunk_markdown(
            text,
            chunk_size_words=300,
            overlap_words=50,
            max_section_words=450,
            min_chunk_words=40,
        )
        sections = [section for _, section, _ in results]
        assert sections == ["One", "Two"]
