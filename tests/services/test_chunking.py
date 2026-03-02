from app.services.chunking_service import chunk_text


def test_adaptive_chunking_basic():
    text = "This is a simple paragraph of text for testing chunking."
    chunks = chunk_text(text, strategy="adaptive")
    assert len(chunks) >= 1
    assert chunks[0].content == text


def test_adaptive_chunking_with_headings():
    text = """# Introduction
This is the introduction section.

# Methods
This is the methods section with detailed explanation."""
    chunks = chunk_text(text, strategy="adaptive")
    assert len(chunks) >= 2


def test_fixed_chunking():
    text = "word " * 1000  # ~5000 chars
    chunks = chunk_text(text, strategy="fixed", chunk_size=100)
    assert len(chunks) > 1
    # All chunks should have content
    for chunk in chunks:
        assert chunk.content.strip()


def test_sentence_chunking():
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunks = chunk_text(text, strategy="sentence", chunk_size=10)
    assert len(chunks) >= 1


def test_paragraph_chunking():
    text = "Paragraph one content.\n\nParagraph two content.\n\nParagraph three content."
    chunks = chunk_text(text, strategy="paragraph")
    assert len(chunks) >= 1


def test_empty_text():
    chunks = chunk_text("", strategy="adaptive")
    assert len(chunks) == 0


def test_chunk_metadata():
    text = "Some text content for testing metadata."
    chunks = chunk_text(text, strategy="fixed")
    assert len(chunks) >= 1
    chunk = chunks[0]
    assert chunk.chunk_index == 0
    assert chunk.char_start >= 0
    assert chunk.char_end > chunk.char_start
    assert chunk.token_count > 0
