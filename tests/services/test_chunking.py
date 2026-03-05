"""Tests for chunking_service — all four strategies plus edge cases."""

import pytest

from app.services.chunking_service import (
    ChunkResult,
    _estimate_tokens,
    chunk_text,
)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_short(self):
        assert _estimate_tokens("abcd") == 1

    def test_approximation(self):
        text = "a" * 400
        assert _estimate_tokens(text) == 100


# ---------------------------------------------------------------------------
# Adaptive strategy
# ---------------------------------------------------------------------------

class TestAdaptiveChunking:
    def test_short_text_single_chunk(self):
        text = "Short paragraph of text."
        chunks = chunk_text(text, strategy="adaptive", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_heading_split(self):
        text = "# Heading One\nContent under heading one.\n\n# Heading Two\nContent two."
        chunks = chunk_text(text, strategy="adaptive", chunk_size=512)
        assert len(chunks) >= 2
        assert any("Content under heading one" in c.content for c in chunks)
        assert any("Content two" in c.content for c in chunks)

    def test_heading_context_preserved(self):
        text = "# My Title\nSome body text here."
        chunks = chunk_text(text, strategy="adaptive", chunk_size=512)
        heading_chunks = [c for c in chunks if c.heading_context is not None]
        assert len(heading_chunks) > 0
        assert "My Title" in heading_chunks[0].heading_context

    def test_long_section_subsplit(self):
        """A section longer than max_tokens should be sub-split by paragraphs."""
        para = "This is a test paragraph with some meaningful content. " * 50
        text = f"# Title\n{para}\n\n{para}"
        chunks = chunk_text(text, strategy="adaptive", chunk_size=64)
        assert len(chunks) > 1

    def test_html_headings(self):
        text = "<h1>Title</h1>Some body.<h2>Section</h2>More text."
        chunks = chunk_text(text, strategy="adaptive", chunk_size=512)
        assert len(chunks) >= 1

    def test_empty_text(self):
        chunks = chunk_text("", strategy="adaptive")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n   ", strategy="adaptive")
        assert chunks == []


# ---------------------------------------------------------------------------
# Fixed strategy
# ---------------------------------------------------------------------------

class TestFixedChunking:
    def test_single_chunk(self):
        text = "Hello world"
        chunks = chunk_text(text, strategy="fixed", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_overlap(self):
        text = "a" * 4000  # 4000 chars = ~1000 tokens
        chunks = chunk_text(text, strategy="fixed", chunk_size=512, chunk_overlap=50)
        assert len(chunks) > 1
        # Verify overlap: second chunk should start before end of first
        if len(chunks) >= 2:
            assert chunks[1].char_start < chunks[0].char_end

    def test_chunk_index_sequential(self):
        text = "word " * 2000
        chunks = chunk_text(text, strategy="fixed", chunk_size=100)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_empty(self):
        assert chunk_text("", strategy="fixed") == []


# ---------------------------------------------------------------------------
# Sentence strategy
# ---------------------------------------------------------------------------

class TestSentenceChunking:
    def test_basic_sentences(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunk_text(text, strategy="sentence", chunk_size=512)
        assert len(chunks) >= 1
        full = " ".join(c.content for c in chunks)
        assert "First sentence" in full

    def test_respects_max_tokens(self):
        text = ". ".join([f"Sentence number {i}" for i in range(200)]) + "."
        chunks = chunk_text(text, strategy="sentence", chunk_size=32)
        for chunk in chunks:
            assert chunk.token_count <= 40  # Allow some slack

    def test_exclamation_and_question(self):
        text = "Hello! How are you? I am fine."
        chunks = chunk_text(text, strategy="sentence", chunk_size=512)
        assert len(chunks) >= 1

    def test_single_sentence(self):
        text = "Just one sentence."
        chunks = chunk_text(text, strategy="sentence", chunk_size=512)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Paragraph strategy
# ---------------------------------------------------------------------------

class TestParagraphChunking:
    def test_basic_paragraphs(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text(text, strategy="paragraph", chunk_size=512)
        assert len(chunks) >= 1

    def test_merges_small_paragraphs(self):
        text = "Short.\n\nAlso short.\n\nTiny."
        chunks = chunk_text(text, strategy="paragraph", chunk_size=512)
        # All fit in one chunk
        assert len(chunks) == 1

    def test_splits_large_paragraphs(self):
        para = "This is a long paragraph. " * 200
        text = f"{para}\n\n{para}"
        chunks = chunk_text(text, strategy="paragraph", chunk_size=64)
        assert len(chunks) > 1


# ---------------------------------------------------------------------------
# Unknown strategy fallback
# ---------------------------------------------------------------------------

class TestUnknownStrategy:
    def test_falls_back_to_fixed(self):
        text = "Some text content."
        chunks = chunk_text(text, strategy="unknown_strategy", chunk_size=512)
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# ChunkResult invariants
# ---------------------------------------------------------------------------

class TestChunkResultInvariants:
    @pytest.mark.parametrize("strategy", ["adaptive", "fixed", "sentence", "paragraph"])
    def test_all_chunks_have_content(self, strategy):
        text = "First paragraph with enough content.\n\nSecond paragraph here.\n\nThird one."
        chunks = chunk_text(text, strategy=strategy, chunk_size=512)
        for chunk in chunks:
            assert isinstance(chunk, ChunkResult)
            assert len(chunk.content.strip()) > 0
            assert chunk.chunk_index >= 0
            assert chunk.token_count >= 0

    @pytest.mark.parametrize("strategy", ["adaptive", "fixed", "sentence", "paragraph"])
    def test_chunk_indices_start_at_zero(self, strategy):
        text = "Some meaningful text content for chunking."
        chunks = chunk_text(text, strategy=strategy, chunk_size=512)
        if chunks:
            assert chunks[0].chunk_index == 0
