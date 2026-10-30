"""
Embeddings + hybrid semantic search.

* Embeds with a local Ollama embedding model (default `nomic-embed-text`, 768-d).
* Each item is split into chunks: a "header" chunk (title + summary + tags) that
  also serves as the item's vector for similarity, plus body chunks for search/Q&A.
* Vectors are stored as float32 BLOBs in SQLite. If the `sqlite-vec` extension
  is installed, a `vec0` index is kept in sync and used for KNN; otherwise a
  NumPy brute-force scan is used (fast enough for tens of thousands of chunks).
* Search is hybrid: cosine similarity + FTS5/BM25 keywords, fused with
  Reciprocal Rank Fusion, then rolled up to items. If Ollama is down, search
  silently degrades to keyword-only instead of failing.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import requests

import database as db

log = logging.getLogger("folio.embed")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("FOLIO_EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT = float(os.getenv("FOLIO_EMBED_TIMEOUT", "60"))
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150
MAX_CHUNKS = 40
BATCH = 16
RRF_K = 60

try:  # optional native vector index
    import sqlite_vec  # type: ignore

    HAS_SQLITE_VEC = True
except ImportError:  # pragma: no cover - depends on environment
    sqlite_vec = None
    HAS_SQLITE_VEC = False


class EmbeddingError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Embedding calls
# --------------------------------------------------------------------------- #
def _prefix(texts: list[str], kind: str) -> list[str]:
    # nomic-embed-text is trained with task prefixes; other models don't need them.
    if "nomic" in EMBED_MODEL:
        p = "search_query: " if kind == "query" else "search_document: "
        return [p + t for t in texts]
    return texts


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


def embed(texts: list[str], kind: str = "document") -> np.ndarray:
    """Return an (n, d) L2-normalised float32 matrix. Raises EmbeddingError."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    inputs = _prefix([t[:8000] for t in texts], kind)
    out: list[list[float]] = []
    try:
        for i in range(0, len(inputs), BATCH):
            batch = inputs[i : i + BATCH]
            r = requests.post(f"{OLLAMA_URL}/api/embed",
                              json={"model": EMBED_MODEL, "input": batch}, timeout=EMBED_TIMEOUT)
            if r.status_code == 404:  # Ollama < 0.3 only has the single-prompt endpoint
                for t in batch:
                    r1 = requests.post(f"{OLLAMA_URL}/api/embeddings",
                                       json={"model": EMBED_MODEL, "prompt": t}, timeout=EMBED_TIMEOUT)
                    r1.raise_for_status()
                    out.append(r1.json()["embedding"])
                continue
            r.raise_for_status()
            out.extend(r.json()["embeddings"])
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise EmbeddingError(f"{exc.__class__.__name__}: {exc}") from exc
    return _normalize(np.asarray(out, dtype=np.float32))


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Paragraph-aware chunking with a small character overlap."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:  # hard-split very long paragraphs
            head, p = p[:size], p[size - overlap :]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if len(cur) + len(p) + 1 <= size:
            cur = f"{cur}\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            tail = cur[-overlap:] if cur else ""
            cur = f"{tail}\n{p}" if tail else p
    if cur:
        chunks.append(cur)
    return chunks[:MAX_CHUNKS]


def header_text(item: db.Item) -> str:
    parts = [item.title]
    if item.summary:
        parts.append(item.summary)
    if item.tags:
        parts.append("Tags: " + ", ".join(item.tags))
    if item.meta.get("abstract"):
        parts.append(item.meta["abstract"][:1200])
    if item.meta.get("description"):
        parts.append(item.meta["description"])
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Vector index (sqlite-vec or NumPy)
# --------------------------------------------------------------------------- #
_cache_lock = threading.Lock()
_cache: dict = {"version": -1, "ids": None, "mat": None}
_version = 0


def _bump() -> None:
    global _version
    _version += 1


@contextmanager
def _vec_conn():
    """Like db.get_conn() but with the sqlite-vec extension loaded (when available)."""
    conn = sqlite3.connect(db.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if HAS_SQLITE_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _vec_table(dim: int) -> str:
    return f"vec_chunks_{dim}"


def _ensure_vec_table(conn: sqlite3.Connection, dim: int) -> None:
    if HAS_SQLITE_VEC:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_vec_table(dim)} "
            f"USING vec0(embedding float[{dim}] distance_metric=cosine)"
        )


def _drop_item_vectors(conn: sqlite3.Connection, item_id: int) -> None:
    chunk_ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE item_id = ?", (item_id,))]
    if HAS_SQLITE_VEC and chunk_ids:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'vec_chunks_%' AND type = 'table'")]
        for t in tables:
            if re.fullmatch(r"vec_chunks_\d+", t):
                conn.executemany(f"DELETE FROM {t} WHERE rowid = ?", [(c,) for c in chunk_ids])
    conn.execute("DELETE FROM chunks WHERE item_id = ?", (item_id,))  # cascades vectors + FTS
    conn.execute("DELETE FROM item_vectors WHERE item_id = ?", (item_id,))


def delete_item_index(item_id: int) -> None:
    with _vec_conn() as conn:
        _drop_item_vectors(conn, item_id)
    _bump()


def index_item(item_id: int) -> dict:
    """(Re)build chunks, keyword index and vectors for one item.
    Returns {"chunks": n, "embedded": bool, "error": str|None}. Never raises."""
    item = db.get_item(item_id)
    row = db.get_raw_text(item_id)
    if not item or not row:
        return {"chunks": 0, "embedded": False, "error": "missing item"}
    _, raw = row
    texts = [header_text(item)] + [c for c in chunk_text(raw) if c.strip()]

    vecs, err = None, None
    try:
        vecs = embed(texts, kind="document")
    except EmbeddingError as exc:
        err = str(exc)
        log.warning("Embedding failed for item %s (keyword search still works): %s", item_id, exc)

    with _vec_conn() as conn:
        _drop_item_vectors(conn, item_id)
        chunk_ids = []
        for idx, t in enumerate(texts):
            cur = conn.execute("INSERT INTO chunks (item_id, idx, text) VALUES (?, ?, ?)", (item_id, idx, t))
            chunk_ids.append(cur.lastrowid)
        if vecs is not None and len(vecs):
            dim = vecs.shape[1]
            conn.executemany("INSERT INTO chunk_vectors (chunk_id, vec) VALUES (?, ?)",
                             [(cid, to_blob(v)) for cid, v in zip(chunk_ids, vecs)])
            conn.execute("INSERT OR REPLACE INTO item_vectors (item_id, model, vec) VALUES (?, ?, ?)",
                         (item_id, EMBED_MODEL, to_blob(vecs[0])))
            if HAS_SQLITE_VEC:
                _ensure_vec_table(conn, dim)
                conn.executemany(f"INSERT INTO {_vec_table(dim)} (rowid, embedding) VALUES (?, ?)",
                                 [(cid, to_blob(v)) for cid, v in zip(chunk_ids, vecs)])
        conn.commit()
    _bump()
    return {"chunks": len(texts), "embedded": vecs is not None, "error": err}


def _load_matrix() -> tuple[np.ndarray, np.ndarray]:
    """All chunk vectors as (chunk_ids, matrix), cached until the next write."""
    with _cache_lock:
        if _cache["version"] == _version and _cache["mat"] is not None:
            return _cache["ids"], _cache["mat"]
        with _vec_conn() as conn:
            rows = conn.execute("SELECT chunk_id, vec FROM chunk_vectors").fetchall()
        if rows:
            ids = np.array([r[0] for r in rows], dtype=np.int64)
            mat = np.vstack([from_blob(r[1]) for r in rows])
        else:
            ids, mat = np.zeros(0, dtype=np.int64), np.zeros((0, 0), dtype=np.float32)
        _cache.update(version=_version, ids=ids, mat=mat)
        return ids, mat


def semantic_chunks(qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Top-k (chunk_id, cosine_similarity)."""
    dim = qvec.shape[-1]
    if HAS_SQLITE_VEC:
        try:
            with _vec_conn() as conn:
                _ensure_vec_table(conn, dim)
                rows = conn.execute(
                    f"SELECT rowid, distance FROM {_vec_table(dim)} WHERE embedding MATCH ? AND k = ?",
                    (to_blob(qvec), k),
                ).fetchall()
            return [(r[0], 1.0 - float(r[1])) for r in rows]
        except sqlite3.Error as exc:  # fall back to NumPy
            log.warning("sqlite-vec query failed, using NumPy: %s", exc)
    ids, mat = _load_matrix()
    if mat.size == 0 or mat.shape[1] != dim:
        return []
    sims = mat @ qvec
    top = np.argsort(-sims)[:k]
    return [(int(ids[i]), float(sims[i])) for i in top]


_FTS_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.\-]*")
STOPWORDS = set("a an and are as at be by for from how i in is it my of on or that the this to was what when where which who why with about".split())


def keyword_chunks(query: str, k: int) -> list[tuple[int, float]]:
    tokens = [t for t in _FTS_TOKEN.findall(query.lower()) if t not in STOPWORDS]
    if not tokens:
        return []
    match = " OR ".join(f'"{t}"' for t in tokens[:12])
    with db.get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT rowid, bm25(chunks_fts) AS s FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY s LIMIT ?",
                (match, k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [(r[0], -float(r[1])) for r in rows]


# --------------------------------------------------------------------------- #
# Public search API
# --------------------------------------------------------------------------- #
@dataclass
class SearchHit:
    item: db.Item
    score: float
    snippet: str
    matched: list[str] = field(default_factory=list)  # ["semantic", "keyword"]
    similarity: float | None = None
    chunk_ids: list[int] = field(default_factory=list)


def search(query: str, limit: int = 10, include_archived: bool = True,
           category: str | None = None, mode: str = "hybrid") -> tuple[list[SearchHit], dict]:
    """Hybrid search. Returns (hits, info) where info says which retrievers ran."""
    query = query.strip()
    if not query:
        return [], {"semantic": False, "keyword": False}
    pool = max(limit * 6, 40)
    info = {"semantic": False, "keyword": False, "error": None, "vector_backend":
            "sqlite-vec" if HAS_SQLITE_VEC else "numpy"}

    sem: list[tuple[int, float]] = []
    if mode in ("hybrid", "semantic"):
        try:
            qv = embed([query], kind="query")[0]
            sem = semantic_chunks(qv, pool)
            info["semantic"] = True
        except EmbeddingError as exc:
            info["error"] = str(exc)
    kw: list[tuple[int, float]] = keyword_chunks(query, pool) if mode in ("hybrid", "keyword") else []
    info["keyword"] = mode in ("hybrid", "keyword")

    # Reciprocal Rank Fusion at chunk level.
    fused: dict[int, float] = {}
    sources: dict[int, set] = {}
    sim_of: dict[int, float] = {}
    for rank, (cid, s) in enumerate(sem):
        fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
        sources.setdefault(cid, set()).add("semantic")
        sim_of[cid] = s
    for rank, (cid, _) in enumerate(kw):
        fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
        sources.setdefault(cid, set()).add("keyword")
    if not fused:
        return [], info

    with db.get_conn() as conn:
        marks = ",".join("?" * len(fused))
        rows = conn.execute(f"SELECT id, item_id, text FROM chunks WHERE id IN ({marks})",
                            list(fused)).fetchall()
    chunk_item = {r["id"]: (r["item_id"], r["text"]) for r in rows}

    # Roll up to items: best chunk + a small bonus for multiple matching chunks.
    per_item: dict[int, dict] = {}
    for cid, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        if cid not in chunk_item:
            continue  # stale index row
        iid, text = chunk_item[cid]
        agg = per_item.setdefault(iid, {"score": 0.0, "best": None, "n": 0, "src": set(),
                                        "sim": None, "chunks": []})
        if agg["best"] is None:
            agg["best"], agg["score"] = text, score
        agg["n"] += 1
        agg["src"] |= sources[cid]
        agg["chunks"].append(cid)
        if cid in sim_of:
            agg["sim"] = max(agg["sim"] or -1, sim_of[cid])
    for agg in per_item.values():
        agg["score"] += 0.002 * min(agg["n"] - 1, 5)

    items = db.get_items(list(per_item))
    hits = []
    for iid, agg in sorted(per_item.items(), key=lambda kv: -kv[1]["score"]):
        it = items.get(iid)
        if not it or (not include_archived and it.archived) or (category and category != "all" and it.category != category):
            continue
        hits.append(SearchHit(item=it, score=round(agg["score"], 5), snippet=_snippet(agg["best"], query),
                              matched=sorted(agg["src"]),
                              similarity=round(agg["sim"], 4) if agg["sim"] is not None else None,
                              chunk_ids=agg["chunks"][:3]))
        if len(hits) >= limit:
            break
    return hits, info


def _snippet(text: str, query: str, width: int = 260) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    terms = [t for t in _FTS_TOKEN.findall(query.lower()) if t not in STOPWORDS]
    pos = min((flat.lower().find(t) for t in terms if flat.lower().find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    out = flat[start : start + width]
    return ("…" if start else "") + out + ("…" if start + width < len(flat) else "")


def chunk_texts(chunk_ids: list[int]) -> dict[int, str]:
    if not chunk_ids:
        return {}
    with db.get_conn() as conn:
        marks = ",".join("?" * len(chunk_ids))
        rows = conn.execute(f"SELECT id, text FROM chunks WHERE id IN ({marks})", chunk_ids).fetchall()
    return {r["id"]: r["text"] for r in rows}


def item_vectors(item_ids: list[int]) -> dict[int, np.ndarray]:
    if not item_ids:
        return {}
    with db.get_conn() as conn:
        marks = ",".join("?" * len(item_ids))
        rows = conn.execute(f"SELECT item_id, vec FROM item_vectors WHERE item_id IN ({marks})", item_ids).fetchall()
    return {r["item_id"]: from_blob(r["vec"]) for r in rows}


def similar_items(item_id: int, limit: int = 5) -> list[tuple[db.Item, float]]:
    vecs = item_vectors([item_id])
    if item_id not in vecs:
        return []
    with db.get_conn() as conn:
        rows = conn.execute("SELECT item_id, vec FROM item_vectors WHERE item_id != ?", (item_id,)).fetchall()
    if not rows:
        return []
    ids = [r["item_id"] for r in rows]
    mat = np.vstack([from_blob(r["vec"]) for r in rows])
    if mat.shape[1] != vecs[item_id].shape[0]:
        return []
    sims = mat @ vecs[item_id]
    order = np.argsort(-sims)[:limit]
    items = db.get_items([ids[i] for i in order])
    return [(items[ids[i]], float(sims[i])) for i in order if ids[i] in items]


def index_stats() -> dict:
    with db.get_conn() as conn:
        n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        n_vec = conn.execute("SELECT COUNT(*) FROM item_vectors").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return {"items": n_items, "items_embedded": n_vec, "chunks": n_chunks, "model": EMBED_MODEL,
            "vector_backend": "sqlite-vec" if HAS_SQLITE_VEC else "numpy"}


def missing_vectors() -> list[int]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM items WHERE id NOT IN (SELECT item_id FROM item_vectors) AND status = 'done'"
        ).fetchall()
    return [r[0] for r in rows]
