import re
from dataclasses import dataclass


@dataclass
class ChunkResult:
    content: str
    chunk_index: int
    char_start: int
    char_end: int
    heading_context: str | None
    token_count: int


def chunk_text(
    text: str,
    strategy: str = "adaptive",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[ChunkResult]:
    """Split text into chunks based on the specified strategy."""
    if strategy == "adaptive":
        return _adaptive_chunk(text, chunk_size)
    elif strategy == "fixed":
        return _fixed_chunk(text, chunk_size, chunk_overlap)
    elif strategy == "sentence":
        return _sentence_chunk(text, chunk_size)
    elif strategy == "paragraph":
        return _paragraph_chunk(text, chunk_size)
    else:
        return _fixed_chunk(text, chunk_size, chunk_overlap)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimation, adjusted for script type.

    Latin-based scripts average ~4 characters per token.
    CJK, Arabic, Thai, Devanagari, and other non-Latin scripts average
    ~1.5–2 characters per token because each character carries more meaning.
    We count characters by category and blend the two estimates.
    """
    latin_chars = 0
    non_latin_chars = 0
    for ch in text:
        if ch.isspace():
            continue
        # ASCII letters, digits, and common Latin punctuation
        if ch.isascii():
            latin_chars += 1
        else:
            non_latin_chars += 1

    # Latin: ~4 chars/token, non-Latin: ~2 chars/token
    tokens = (latin_chars / 4) + (non_latin_chars / 2)
    return max(1, int(tokens)) if text.strip() else 0


def _adaptive_chunk(text: str, max_tokens: int = 512) -> list[ChunkResult]:
    """Split on headings and semantic boundaries."""
    # Split by heading patterns (markdown-style or HTML-style)
    heading_pattern = re.compile(
        r"((?:^|\n)#{1,6}\s+.+)|(?:<h[1-6][^>]*>.*?</h[1-6]>)", re.MULTILINE
    )

    sections = []
    last_end = 0
    current_heading = None

    for match in heading_pattern.finditer(text):
        if last_end < match.start():
            sections.append((current_heading, text[last_end : match.start()], last_end))
        current_heading = match.group().strip().lstrip("#").strip()
        last_end = match.end()

    if last_end < len(text):
        sections.append((current_heading, text[last_end:], last_end))

    if not sections:
        sections = [(None, text, 0)]

    chunks = []
    chunk_index = 0

    for heading, section_text, section_start in sections:
        section_text = section_text.strip()
        if not section_text:
            continue

        if _estimate_tokens(section_text) <= max_tokens:
            chunks.append(
                ChunkResult(
                    content=section_text,
                    chunk_index=chunk_index,
                    char_start=section_start,
                    char_end=section_start + len(section_text),
                    heading_context=heading,
                    token_count=_estimate_tokens(section_text),
                )
            )
            chunk_index += 1
        else:
            # Sub-split long sections by paragraph breaks
            sub_chunks = _split_by_paragraphs(
                section_text, max_tokens, section_start, heading
            )
            for sc in sub_chunks:
                sc.chunk_index = chunk_index
                chunks.append(sc)
                chunk_index += 1

    return chunks


def _split_by_paragraphs(
    text: str, max_tokens: int, offset: int, heading: str | None
) -> list[ChunkResult]:
    """Split text by paragraph boundaries, merging small ones."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""
    current_start = offset

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if current and _estimate_tokens(current + "\n\n" + para) > max_tokens:
            chunks.append(
                ChunkResult(
                    content=current,
                    chunk_index=0,
                    char_start=current_start,
                    char_end=current_start + len(current),
                    heading_context=heading,
                    token_count=_estimate_tokens(current),
                )
            )
            current = para
            current_start = offset + text.find(para)
        else:
            current = (current + "\n\n" + para).strip() if current else para

    if current:
        chunks.append(
            ChunkResult(
                content=current,
                chunk_index=0,
                char_start=current_start,
                char_end=current_start + len(current),
                heading_context=heading,
                token_count=_estimate_tokens(current),
            )
        )

    return chunks


def _chars_per_token(text: str) -> float:
    """Estimate the average characters-per-token ratio for the given text.

    Returns ~4 for pure Latin text and ~2 for pure non-Latin text,
    blending proportionally for mixed content.
    """
    latin = 0
    non_latin = 0
    for ch in text:
        if ch.isspace():
            continue
        if ch.isascii():
            latin += 1
        else:
            non_latin += 1
    total = latin + non_latin
    if total == 0:
        return 4.0
    # Weighted average: Latin chars ≈ 4 c/t, non-Latin ≈ 2 c/t
    return (latin * 4.0 + non_latin * 2.0) / total


def _fixed_chunk(
    text: str, chunk_size: int = 512, overlap: int = 50
) -> list[ChunkResult]:
    """Sliding window chunking by character count (token-approximate)."""
    cpt = _chars_per_token(text)
    char_chunk_size = int(chunk_size * cpt)
    char_overlap = int(overlap * cpt)
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = min(start + char_chunk_size, len(text))
        chunk_text = text[start:end]

        if chunk_text.strip():
            chunks.append(
                ChunkResult(
                    content=chunk_text.strip(),
                    chunk_index=chunk_index,
                    char_start=start,
                    char_end=end,
                    heading_context=None,
                    token_count=_estimate_tokens(chunk_text),
                )
            )
            chunk_index += 1

        if end >= len(text):
            break
        start = end - char_overlap

    return chunks


def _sentence_chunk(text: str, max_tokens: int = 512) -> list[ChunkResult]:
    """Split by sentence boundaries.

    Supports Latin (.!?), Arabic (؟ ، ؛), CJK (。！？), Thai (ฯ),
    and other common sentence-ending punctuation.
    """
    sentences = re.split(r"(?<=[.!?\u061F\u060C\u061B\u06D4\u3002\uFF01\uFF1F\u0E2F])\s+", text)
    chunks = []
    current = ""
    current_start = 0
    chunk_index = 0

    for sentence in sentences:
        if current and _estimate_tokens(current + " " + sentence) > max_tokens:
            chunks.append(
                ChunkResult(
                    content=current.strip(),
                    chunk_index=chunk_index,
                    char_start=current_start,
                    char_end=current_start + len(current),
                    heading_context=None,
                    token_count=_estimate_tokens(current),
                )
            )
            chunk_index += 1
            current_start = current_start + len(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current.strip():
        chunks.append(
            ChunkResult(
                content=current.strip(),
                chunk_index=chunk_index,
                char_start=current_start,
                char_end=current_start + len(current),
                heading_context=None,
                token_count=_estimate_tokens(current),
            )
        )

    return chunks


def _paragraph_chunk(text: str, max_tokens: int = 512) -> list[ChunkResult]:
    """Split by paragraph breaks."""
    return _split_by_paragraphs(text, max_tokens, 0, None)
