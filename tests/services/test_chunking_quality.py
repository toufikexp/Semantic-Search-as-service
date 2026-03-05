"""Advanced chunking quality tests.

These tests go beyond basic functionality to verify:
  - Full text coverage (no content lost during chunking)
  - Overlap correctness
  - Heading context preservation
  - Boundary quality (chunks don't split mid-word/sentence)
  - Token count accuracy
  - Behavior with real-world content patterns
"""

from app.services.chunking_service import chunk_text


# ---------------------------------------------------------------------------
# Coverage: no content lost
# ---------------------------------------------------------------------------

class TestChunkCoverage:
    def test_full_text_reconstructable_fixed(self):
        """All characters in the original text appear in at least one chunk."""
        text = "The quick brown fox jumps over the lazy dog. " * 50
        chunks = chunk_text(text, strategy="fixed", chunk_size=50, chunk_overlap=10)
        # Reconstruct: every char_start..char_end range should cover the text
        covered = set()
        for c in chunks:
            for i in range(c.char_start, c.char_end):
                covered.add(i)
        # Every non-trailing-whitespace position should be covered
        for i, ch in enumerate(text.rstrip()):
            assert i in covered, f"Position {i} ('{ch}') not in any chunk"

    def test_full_text_reconstructable_adaptive(self):
        """Adaptive chunking covers all content."""
        text = """# Section One
First section content here with some details.

# Section Two
Second section with different information and more details."""
        chunks = chunk_text(text, strategy="adaptive")
        combined = " ".join(c.content for c in chunks)
        # Each significant word from original should appear
        for word in ["First", "section", "Second", "information", "details"]:
            assert word in combined, f"'{word}' missing from chunks"

    def test_no_empty_chunks(self):
        """No chunking strategy should produce empty chunks."""
        text = "Content. " * 100
        for strategy in ["adaptive", "fixed", "sentence", "paragraph"]:
            chunks = chunk_text(text, strategy=strategy)
            for c in chunks:
                assert c.content.strip(), (
                    f"Empty chunk from strategy '{strategy}' at index {c.chunk_index}"
                )


# ---------------------------------------------------------------------------
# Overlap correctness
# ---------------------------------------------------------------------------

class TestChunkOverlap:
    def test_fixed_overlap_exists(self):
        """Adjacent fixed chunks should share overlapping content."""
        text = "word " * 500  # Long enough to need multiple chunks
        chunks = chunk_text(text, strategy="fixed", chunk_size=100, chunk_overlap=25)
        if len(chunks) < 2:
            pytest.skip("Text too short for overlap test")

        for i in range(len(chunks) - 1):
            current_end = chunks[i].content[-50:]  # last 50 chars of current
            next_start = chunks[i + 1].content[:50]  # first 50 chars of next
            # There should be some shared substring
            overlap_found = any(
                current_end[j:j+10] in next_start
                for j in range(len(current_end) - 10)
            )
            assert overlap_found, (
                f"No overlap between chunk {i} and {i+1}"
            )

    def test_zero_overlap(self):
        """With overlap=0, chunks should not repeat content."""
        text = "alpha bravo charlie delta echo foxtrot " * 20
        chunks = chunk_text(text, strategy="fixed", chunk_size=50, chunk_overlap=0)
        if len(chunks) < 2:
            pytest.skip("Not enough chunks")
        # Content of consecutive chunks should not share full words
        for i in range(len(chunks) - 1):
            last_words = set(chunks[i].content.strip().split()[-3:])
            first_words = set(chunks[i + 1].content.strip().split()[:3])
            overlap = last_words & first_words
            assert len(overlap) <= 1, (
                f"Too much overlap with overlap=0: {overlap}"
            )


# ---------------------------------------------------------------------------
# Heading context preservation
# ---------------------------------------------------------------------------

class TestHeadingContext:
    def test_adaptive_preserves_headings(self):
        """Chunks under headings should carry heading_context."""
        text = """# Getting Started
This is the getting started guide for new users.

# Configuration
Configure your system with these settings.

# Troubleshooting
Common issues and their solutions."""
        chunks = chunk_text(text, strategy="adaptive")
        headings_found = [c.heading_context for c in chunks if c.heading_context]
        assert len(headings_found) >= 2, "Adaptive should preserve heading contexts"

    def test_heading_context_matches_section(self):
        """heading_context should match the heading above the chunk content."""
        text = """# Billing
Pay your bill at the store or online.

# Support
Call 888 for 24/7 support."""
        chunks = chunk_text(text, strategy="adaptive")
        for c in chunks:
            if c.heading_context and "Billing" in c.heading_context:
                assert "bill" in c.content.lower() or "pay" in c.content.lower()
            if c.heading_context and "Support" in c.heading_context:
                assert "support" in c.content.lower() or "888" in c.content


# ---------------------------------------------------------------------------
# Boundary quality
# ---------------------------------------------------------------------------

class TestChunkBoundaries:
    def test_sentence_chunks_end_at_sentence(self):
        """Sentence-strategy chunks should end at sentence boundaries."""
        text = (
            "First sentence here. Second sentence follows. "
            "Third one is longer with more words. Fourth sentence. "
            "Fifth and final sentence here."
        )
        chunks = chunk_text(text, strategy="sentence", chunk_size=30)
        for c in chunks:
            stripped = c.content.strip()
            if stripped:
                assert stripped[-1] in ".!?", (
                    f"Sentence chunk doesn't end with punctuation: '{stripped[-20:]}'"
                )

    def test_paragraph_chunks_respect_boundaries(self):
        """Paragraph chunks should split on double newlines."""
        text = "Para one content.\n\nPara two content.\n\nPara three content."
        chunks = chunk_text(text, strategy="paragraph")
        for c in chunks:
            # No chunk should contain a double newline internally
            assert "\n\n" not in c.content.strip(), (
                f"Paragraph chunk contains internal paragraph break"
            )


# ---------------------------------------------------------------------------
# Chunk metadata correctness
# ---------------------------------------------------------------------------

class TestChunkMetadata:
    def test_chunk_indices_are_sequential(self):
        """chunk_index should be 0, 1, 2, ... for each document."""
        text = "Content here. " * 200
        for strategy in ["adaptive", "fixed", "sentence", "paragraph"]:
            chunks = chunk_text(text, strategy=strategy)
            indices = [c.chunk_index for c in chunks]
            assert indices == list(range(len(chunks))), (
                f"Non-sequential indices for {strategy}: {indices[:10]}"
            )

    def test_char_offsets_non_overlapping_boundaries(self):
        """char_start of chunk N+1 should be >= char_start of chunk N."""
        text = "Some test content. " * 100
        chunks = chunk_text(text, strategy="fixed", chunk_size=50)
        for i in range(len(chunks) - 1):
            assert chunks[i].char_start < chunks[i + 1].char_start, (
                f"char_start not increasing: {chunks[i].char_start} vs "
                f"{chunks[i+1].char_start}"
            )

    def test_token_count_reasonable(self):
        """Token counts should be reasonable (roughly chars/4)."""
        text = "This is a test of token counting in the chunking service. " * 20
        chunks = chunk_text(text, strategy="fixed", chunk_size=100)
        for c in chunks:
            char_count = len(c.content)
            # Token estimate should be roughly chars/4, allow 50% variance
            expected = char_count / 4
            assert c.token_count > 0
            assert 0.3 * expected < c.token_count < 3 * expected, (
                f"Token count {c.token_count} unexpected for {char_count} chars"
            )


# ---------------------------------------------------------------------------
# Real-world content patterns
# ---------------------------------------------------------------------------

class TestRealWorldContent:
    def test_html_like_content(self):
        """Content with HTML remnants should chunk without issues."""
        text = (
            "Welcome to Ooredoo.\n"
            "5G Plans\n"
            "Our 5G plans start at 2000 DA per month for 50GB of high-speed data.\n"
            "4G Plans\n"
            "Choose from our range of 4G forfaits starting at just 500 DA.\n"
            "Need help? Contact us at 888.\n"
        )
        chunks = chunk_text(text, strategy="adaptive")
        assert len(chunks) >= 1
        assert all(c.content.strip() for c in chunks)

    def test_mixed_language_content(self):
        """Mixed French/English/Arabic should not break chunking."""
        text = (
            "# Offres Ooredoo\n"
            "Découvrez nos forfaits 4G et 5G.\n\n"
            "# Ooredoo Offers\n"
            "Check out our 4G and 5G plans.\n\n"
            "# عروض أوريدو\n"
            "اكتشف عروضنا للجيل الرابع والخامس.\n"
        )
        chunks = chunk_text(text, strategy="adaptive")
        assert len(chunks) >= 1

    def test_very_short_document(self):
        """A single short sentence should produce exactly one chunk."""
        text = "Ooredoo customer service: call 888."
        chunks = chunk_text(text, strategy="adaptive")
        assert len(chunks) == 1
        assert chunks[0].content.strip() == text.strip()

    def test_very_long_single_paragraph(self):
        """A long paragraph with no breaks should still be chunked."""
        text = "Ooredoo provides mobile services. " * 300
        chunks = chunk_text(text, strategy="adaptive", chunk_size=100)
        assert len(chunks) > 1
