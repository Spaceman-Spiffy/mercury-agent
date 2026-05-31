"""Dense semantic embeddings for the holographic memory store.

Adds a transformer-embedding signal alongside the existing FTS5 / Jaccard /
HRR retrieval. This closes the *pure-synonym* gap that lexical-first search
cannot: a query like "where does the code live" with zero token overlap to
"checkout and venv root is ..." is unreachable by FTS5 MATCH, so the fact
never enters the candidate pool. A dense embedding retriever runs in PARALLEL
to FTS5 and unions its candidates in, after which the blended score reranks.

Backend: sentence-transformers, CPU, model BAAI/bge-small-en-v1.5 (~130 MB).
Chosen empirically over model2vec (too noisy on short jargon facts) and
bge-base (no accuracy gain on short facts, 3x footprint). The model loads
lazily on first use and is cached process-wide.

Design rules:
  - HARD optional. If sentence-transformers is not installed, _HAS_EMBED is
    False and every function is a safe no-op / neutral value, exactly like
    holographic.py gates on numpy. The store and retriever keep working with
    FTS5+Jaccard(+HRR) only.
  - Deterministic, offline. No network calls at query time once the model is
    cached on disk. First-ever load downloads the model from HF; thereafter
    it is read from the local HF cache.
  - float32 vectors, L2-normalized, stored as raw bytes in the facts table
    (mirrors how holographic stores phase vectors).
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

# Default model — small, strong, CPU-friendly. Overridable via config/env.
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_MODEL = os.environ.get("HERMES_MEMORY_EMBED_MODEL", DEFAULT_EMBED_MODEL)

# BGE models are trained with an asymmetric retrieval scheme: the QUERY must
# carry a short instruction prefix, while passages (facts) are embedded bare.
# Without the query prefix, BGE similarities collapse into a narrow band and
# retrieval degrades to near-noise. This prefix is applied to queries only.
# See BAAI/bge docs ("Represent this sentence for searching relevant passages").
# Non-BGE models that don't need it are unaffected — the extra lead-in text is
# semantically harmless to symmetric models.
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _is_bge(model_name: str) -> bool:
    return "bge" in (model_name or "").lower()

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    # Importing the class is cheap; the heavy model load is deferred.
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _HAS_EMBED = _HAS_NUMPY  # embeddings require numpy for storage/similarity
except Exception:  # ImportError, or torch load issues on exotic platforms
    _HAS_EMBED = False

_model = None
_model_lock = threading.Lock()
_model_dim: int | None = None


def is_available() -> bool:
    """True iff dense embeddings can be computed (deps present)."""
    return _HAS_EMBED


def _get_model():
    """Lazily load and cache the embedding model (process-wide, thread-safe).

    Returns None if embeddings are unavailable or the model fails to load —
    callers must treat None as "embedding signal disabled" and fall back.
    """
    global _model, _model_dim
    if not _HAS_EMBED:
        return None
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            # device="cpu" is explicit: this workload (one query + a few
            # hundred short facts) is CPU-bound; GPU dispatch would be slower
            # and would drag CUDA/ROCm deps onto the install.
            m = SentenceTransformer(EMBED_MODEL, device="cpu")
            _model = m
            try:
                _dim = m.get_sentence_embedding_dimension()
                _model_dim = int(_dim) if _dim is not None else None
            except Exception:
                _model_dim = None
            logger.info("Loaded memory embedding model %s (dim=%s)", EMBED_MODEL, _model_dim)
        except Exception as exc:
            # Disable cleanly for the rest of the process; never raise into
            # the retrieval hot path.
            logger.warning("Embedding model load failed (%s); semantic signal disabled.", exc)
            globals()["_HAS_EMBED"] = False
            return None
    return _model


def embed(text: str, *, is_query: bool = False) -> "np.ndarray | None":
    """Return an L2-normalized float32 embedding for *text*, or None.

    Set ``is_query=True`` when embedding a search query (as opposed to a
    stored fact/passage). For BGE models this prepends the required retrieval
    instruction prefix — without it, query/passage similarities collapse and
    retrieval degrades badly. Passages are always embedded bare.

    None means "no embedding available" — callers treat that as a neutral /
    skipped signal, never an error.
    """
    if not _HAS_EMBED or not text or not text.strip():
        return None
    model = _get_model()
    if model is None:
        return None
    payload = text
    if is_query and _is_bge(EMBED_MODEL):
        payload = _BGE_QUERY_PREFIX + text
    try:
        vec = model.encode([payload], normalize_embeddings=True)[0]
        return np.asarray(vec, dtype=np.float32)
    except Exception as exc:
        logger.debug("embed() failed: %s", exc)
        return None


def embed_to_bytes(text: str) -> "bytes | None":
    """Embed *text* and serialize to raw float32 bytes for SQLite storage."""
    vec = embed(text)
    if vec is None:
        return None
    return vec.tobytes()


def bytes_to_vec(data: "bytes | None") -> "np.ndarray | None":
    """Deserialize stored float32 bytes back to a vector. None-safe."""
    if not data or not _HAS_NUMPY:
        return None
    try:
        return np.frombuffer(data, dtype=np.float32).copy()
    except Exception:
        return None


def cosine(a: "np.ndarray | None", b: "np.ndarray | None") -> float:
    """Cosine similarity in [-1, 1]. Returns 0.0 if either vector is missing.

    Inputs are expected to be L2-normalized (embed() normalizes), so this is
    a dot product; we normalize defensively in case a stored vector wasn't.
    """
    if a is None or b is None or not _HAS_NUMPY:
        return 0.0
    try:
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
    except Exception:
        return 0.0
