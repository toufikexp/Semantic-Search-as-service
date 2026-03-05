"""Tests for embedding quality: similarity, consistency, and multilingual behavior.

These tests verify that the embedding model (BGE-M3) produces vectors with
expected properties.  They require the model to be loadable but do NOT need
a database.

Run with: pytest tests/evaluation/test_embedding_quality.py -v
Mark: @pytest.mark.eval
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.embedding_service import compute_embeddings

pytestmark = pytest.mark.eval


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


# ---------------------------------------------------------------------------
# Dimensionality and normalization
# ---------------------------------------------------------------------------

class TestEmbeddingBasics:
    def test_output_dimension(self):
        vecs = compute_embeddings(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 1024  # BGE-M3 = 1024 dims

    def test_vectors_are_normalized(self):
        vecs = compute_embeddings(["test normalization"])
        norm = np.linalg.norm(vecs[0])
        assert norm == pytest.approx(1.0, abs=1e-4)

    def test_batch_output_count(self):
        texts = ["one", "two", "three", "four", "five"]
        vecs = compute_embeddings(texts)
        assert len(vecs) == 5

    def test_deterministic(self):
        text = "deterministic test"
        v1 = compute_embeddings([text])[0]
        v2 = compute_embeddings([text])[0]
        sim = cosine_sim(v1, v2)
        assert sim == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Semantic similarity: similar texts should be close
# ---------------------------------------------------------------------------

class TestSemanticSimilarity:
    def test_synonyms_are_close(self):
        """Near-synonyms should have high cosine similarity."""
        vecs = compute_embeddings([
            "How do I pay my phone bill?",
            "How can I settle my mobile invoice?",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim > 0.80, f"Synonym sim {sim:.4f} too low"

    def test_paraphrase_similarity(self):
        """Full paraphrases should be very close."""
        vecs = compute_embeddings([
            "I lost my SIM card, what should I do?",
            "My SIM card is missing, how can I get a replacement?",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim > 0.82, f"Paraphrase sim {sim:.4f} too low"

    def test_unrelated_texts_are_far(self):
        """Semantically unrelated texts should have low similarity."""
        vecs = compute_embeddings([
            "Ooredoo 5G mobile plans and pricing",
            "The history of ancient Roman architecture",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim < 0.40, f"Unrelated sim {sim:.4f} too high"

    def test_related_but_different(self):
        """Same domain but different topics: moderate similarity."""
        vecs = compute_embeddings([
            "Ooredoo 5G plans with 50GB data",
            "Ooredoo customer service phone number",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        # Same brand, different intent — should be moderate
        assert 0.30 < sim < 0.80, f"Related sim {sim:.4f} unexpected"


# ---------------------------------------------------------------------------
# Multilingual / cross-lingual similarity
# ---------------------------------------------------------------------------

class TestMultilingualEmbeddings:
    def test_french_english_same_meaning(self):
        """BGE-M3 should produce close vectors for EN/FR translations."""
        vecs = compute_embeddings([
            "How to pay my bill online?",
            "Comment payer ma facture en ligne ?",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim > 0.75, f"EN/FR sim {sim:.4f} too low for BGE-M3"

    def test_arabic_english_same_meaning(self):
        """Arabic and English expressing the same concept."""
        vecs = compute_embeddings([
            "internet mobile offers",
            "عروض الإنترنت عبر الهاتف المحمول",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim > 0.65, f"EN/AR sim {sim:.4f} too low"

    def test_french_arabic_same_meaning(self):
        """French and Arabic expressing the same concept."""
        vecs = compute_embeddings([
            "forfaits internet mobile",
            "باقات الإنترنت عبر الهاتف المحمول",
        ])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim > 0.60, f"FR/AR sim {sim:.4f} too low"


# ---------------------------------------------------------------------------
# Query-document similarity
# ---------------------------------------------------------------------------

class TestQueryDocumentSimilarity:
    """The core test: does the embedding space place queries near their
    relevant documents and far from irrelevant ones?"""

    def test_query_ranks_relevant_doc_first(self):
        """A targeted query should be closest to its matching document."""
        query = "How do I configure APN settings on my phone?"
        docs = [
            "APN settings for Ooredoo: APN internet, MCC 603, MNC 01",  # relevant
            "Ooredoo career opportunities and job openings",             # irrelevant
            "Ooredoo 5G plans starting at 2000 DA per month",           # wrong topic
        ]
        vecs = compute_embeddings([query] + docs)
        q_vec = vecs[0]
        sims = [cosine_sim(q_vec, vecs[i + 1]) for i in range(len(docs))]

        assert sims[0] > sims[1], "Relevant doc should rank above careers"
        assert sims[0] > sims[2], "Relevant doc should rank above 5G offers"

    def test_french_query_matches_french_doc(self):
        """A French query should find a French document."""
        query = "forfaits internet mobile Ooredoo"
        docs = [
            "Forfaits 4G Ooredoo avec des offres allant de 500 DA à 5000 DA",  # FR match
            "Ooredoo corporate social responsibility and tree planting",         # EN irrelevant
        ]
        vecs = compute_embeddings([query] + docs)
        q_vec = vecs[0]
        sims = [cosine_sim(q_vec, vecs[i + 1]) for i in range(len(docs))]
        assert sims[0] > sims[1]

    def test_semantic_reformulation(self):
        """Query with no keyword overlap should still find the right doc."""
        query = "how much data do I get for 200 dinars"
        docs = [
            "200 DA gives 3GB for 3 days, 500 DA gives 10GB for 7 days",  # match
            "Join the Ooredoo team! We are hiring software engineers",      # irrelevant
        ]
        vecs = compute_embeddings([query] + docs)
        q_vec = vecs[0]
        sims = [cosine_sim(q_vec, vecs[i + 1]) for i in range(len(docs))]
        assert sims[0] > sims[1]


# ---------------------------------------------------------------------------
# Embedding stability / edge cases
# ---------------------------------------------------------------------------

class TestEmbeddingEdgeCases:
    def test_empty_string(self):
        """Empty or whitespace-only input should not crash."""
        vecs = compute_embeddings([""])
        assert len(vecs) == 1
        assert len(vecs[0]) == 1024

    def test_very_long_text(self):
        """Model should handle text beyond typical chunk sizes."""
        long_text = "Ooredoo offers great mobile plans. " * 500
        vecs = compute_embeddings([long_text])
        assert len(vecs) == 1
        norm = np.linalg.norm(vecs[0])
        assert norm == pytest.approx(1.0, abs=1e-3)

    def test_special_characters(self):
        """Text with special chars / mixed scripts should not crash."""
        text = "Ooredoo عروض 5G <html>&amp; réseau mobile #2026!"
        vecs = compute_embeddings([text])
        assert len(vecs) == 1

    def test_duplicate_texts_same_vectors(self):
        """Identical texts in a batch should produce identical vectors."""
        vecs = compute_embeddings(["duplicate", "duplicate"])
        sim = cosine_sim(vecs[0], vecs[1])
        assert sim == pytest.approx(1.0, abs=1e-6)
