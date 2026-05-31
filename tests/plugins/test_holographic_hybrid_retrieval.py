"""Tests for the holographic memory store's Hybrid-Full retrieval.

Covers the local additions made on the maintained fork:
  - query sanitization for FTS5 (raw NL no longer crashes MATCH → [])
  - dense-embedding parallel candidate retrieval (semantic recall)
  - MAX fusion (strongest signal wins; literal queries don't regress)
  - graceful degradation when the embedding stack is absent

The embedding-dependent assertions are skipped when sentence-transformers
is not installed, so the suite still passes in a lexical-only environment.
"""

import os
import sys
import tempfile

import pytest

_PLUGIN = os.path.join(
    os.path.dirname(__file__), "..", "..", "plugins", "memory", "holographic"
)
sys.path.insert(0, os.path.abspath(_PLUGIN))

from store import MemoryStore          # noqa: E402
from retrieval import FactRetriever    # noqa: E402
import embedding as emb                # noqa: E402

_HAS_EMBED = emb.is_available()
_skip_embed = pytest.mark.skipif(
    not _HAS_EMBED, reason="sentence-transformers not installed"
)

_FACTS = [
    ("Checkout and venv root is ~/.hermes/hermes-agent.", "environment"),
    ("Update the fork with the hermes sync command, never plain hermes update.", "git"),
    ("Image generation works via the Nous managed gateway with no FAL key.", "config"),
    ("User prefers a minimal, face-free interface.", "preference"),
    ("web_search depends on the ddgs package; a venv rebuild silently drops it.", "tooling"),
    ("The Anthropic thinking-block 400 was a Hermes bug in the native transport.", "bug"),
    ("A headless Thorium daemon runs via systemd exposing CDP on 127.0.0.1:9222 for browser automation.", "environment"),
    ("The secret-redaction layer scrubs credential strings to a placeholder.", "security"),
]


@pytest.fixture
def store():
    path = os.path.join(tempfile.mkdtemp(), "test_mem.db")
    s = MemoryStore(db_path=path, default_trust=0.6)
    for content, cat in _FACTS:
        s.add_fact(content, category=cat)
    return s


@pytest.fixture
def retriever(store):
    return FactRetriever(store)


class TestQuerySanitization:
    def test_raw_nl_query_does_not_crash(self, retriever):
        # Apostrophes, question marks, etc. used to throw FTS5 syntax errors
        # that were swallowed → silent empty result. Must not raise now.
        for q in ["why isn't it working?", "what's the deal?", "()[]", "   ", ""]:
            retriever.search(q, limit=3)  # no exception = pass

    def test_sanitizer_strips_to_or_tokens(self):
        out = FactRetriever._sanitize_fts_query("How do I update my fork?")
        assert "OR" in out
        assert "update" in out and "fork" in out
        assert "how" not in out  # stopword dropped

    def test_sanitizer_empty_returns_no_match_sentinel(self):
        out = FactRetriever._sanitize_fts_query("?? a I the")
        assert out == "__hermes_no_fts_match__"


class TestLiteralRetrieval:
    """Exact-keyword queries must still resolve (no regression from embeddings)."""

    @pytest.mark.parametrize("query,needle", [
        ("ddgs", "ddgs"),
        ("hermes sync", "hermes sync"),
        ("CDP 9222", "Thorium"),
        ("FAL key", "Image generation"),
        ("venv root", "Checkout"),
    ])
    def test_literal_hit(self, retriever, query, needle):
        res = retriever.search(query, limit=1)
        assert res, f"no result for {query!r}"
        assert needle in res[0]["content"]


@_skip_embed
class TestSemanticRetrieval:
    """Synonym / paraphrase queries with low lexical overlap."""

    @pytest.mark.parametrize("query,needle", [
        ("how do I update my fork safely?", "Update the fork"),
        ("make me a picture", "Image generation"),
        ("keep the screen clean and simple", "minimal"),
        ("my search tool is broken", "ddgs"),
        ("why did the model reject my reasoning blocks?", "thinking-block"),
        ("log into a website in the browser", "Thorium"),
        ("how are API keys protected", "redaction"),
    ])
    def test_semantic_hit(self, retriever, query, needle):
        res = retriever.search(query, limit=1)
        assert res, f"no result for {query!r}"
        assert needle in res[0]["content"], (
            f"{query!r} -> {res[0]['content'][:60]!r} (expected {needle!r})"
        )

    def test_embeddings_written_on_add(self, store):
        n = store._conn.execute(
            "SELECT COUNT(*) FROM facts WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        assert n == len(_FACTS)

    def test_backfill_is_idempotent(self, store):
        # Already embedded at add time → nothing missing to backfill.
        assert store.backfill_embeddings(only_missing=True) == 0


class TestEmbeddingModule:
    def test_none_safe_cosine(self):
        assert emb.cosine(None, None) == 0.0

    def test_bytes_roundtrip_none_safe(self):
        assert emb.bytes_to_vec(None) is None

    @_skip_embed
    def test_query_prefix_changes_vector(self):
        # is_query=True applies the BGE retrieval prefix → different vector.
        bare = emb.embed("update my fork")
        q = emb.embed("update my fork", is_query=True)
        assert bare is not None and q is not None
        # Not identical (prefix shifts the embedding).
        import numpy as np
        assert not np.allclose(bare, q)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
