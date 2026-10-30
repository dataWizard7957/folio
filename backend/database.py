"""
SQLite connection, schema, migrations and Pydantic models.

Uses the standard-library sqlite3 driver with one short-lived connection per
operation, which is safe across FastAPI's threadpool and background tasks.
Vector storage lives in embeddings.py; this module owns the relational data.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal, Optional

from pydantic import BaseModel, Field, model_validator

DB_PATH = os.getenv("FOLIO_DB_PATH", os.path.join(os.path.dirname(__file__), "folio.db"))

Category = Literal["read", "cook", "buy", "explore", "build", "uncategorized"]
Status = Literal["pending", "processing", "done", "failed"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    url             TEXT,
    source          TEXT,
    content_type    TEXT    NOT NULL DEFAULT 'note',
    raw_text        TEXT    NOT NULL DEFAULT '',
    summary         TEXT,
    category        TEXT    NOT NULL DEFAULT 'uncategorized',
    tags            TEXT    NOT NULL DEFAULT '[]',
    status          TEXT    NOT NULL DEFAULT 'pending',
    is_read         INTEGER NOT NULL DEFAULT 0,
    featured        INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Text chunks used for semantic + keyword search and Q&A.
CREATE TABLE IF NOT EXISTS chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    idx       INTEGER NOT NULL,
    text      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_id);

-- Keyword index (BM25) over chunk text.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

-- Raw float32 vectors (source of truth; sqlite-vec index is built from these).
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id  INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    vec       BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS item_vectors (
    item_id   INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    model     TEXT NOT NULL,
    vec       BLOB NOT NULL
);

-- "Your saved repo shipped v2.0", "this paper has a highly-cited follow-up"...
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER REFERENCES items(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    message     TEXT NOT NULL,
    url         TEXT,
    dedupe_key  TEXT UNIQUE,
    seen        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Files picked up by the folder watcher, so each is ingested once.
CREATE TABLE IF NOT EXISTS watched_files (
    path        TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    item_id     INTEGER,
    ingested_at TEXT NOT NULL
);
"""

# Columns added after v1. Each is applied only if missing, so old DBs upgrade in place.
MIGRATIONS: dict[str, str] = {
    "kept": "INTEGER NOT NULL DEFAULT 0",
    "archived": "INTEGER NOT NULL DEFAULT 0",
    "archived_at": "TEXT",
    "read_at": "TEXT",
    "last_touched_at": "TEXT",
    "next_step": "TEXT",
    "meta": "TEXT NOT NULL DEFAULT '{}'",
    "file_name": "TEXT",
    "sha256": "TEXT",
}

POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_items_created  ON items(created_at);
CREATE INDEX IF NOT EXISTS idx_items_read     ON items(is_read);
CREATE INDEX IF NOT EXISTS idx_items_archived ON items(archived);
CREATE INDEX IF NOT EXISTS idx_items_sha      ON items(sha256);
"""


# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #
class IngestRequest(BaseModel):
    """Accepts either a URL or raw text / a note. A string starting with
    http(s):// in either field is treated as a URL."""

    url: Optional[str] = Field(default=None, max_length=2048)
    text: Optional[str] = Field(default=None, max_length=200_000)
    title: Optional[str] = Field(default=None, max_length=300)  # e.g. from the browser extension

    @model_validator(mode="after")
    def _one_input(self) -> "IngestRequest":
        if not (self.url and self.url.strip()) and not (self.text and self.text.strip()):
            raise ValueError("Provide either 'url' or 'text'.")
        return self

    @property
    def raw_input(self) -> str:
        return (self.url or self.text or "").strip()


class Item(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    source: Optional[str] = None
    content_type: str = "note"
    summary: Optional[str] = None
    category: Category = "uncategorized"
    tags: list[str] = Field(default_factory=list)
    status: Status = "pending"
    is_read: bool = False
    featured: bool = False
    kept: bool = False
    archived: bool = False
    next_step: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    file_name: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    read_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    last_touched_at: Optional[datetime] = None


class ItemUpdate(BaseModel):
    is_read: Optional[bool] = None
    featured: Optional[bool] = None
    kept: Optional[bool] = None
    archived: Optional[bool] = None
    category: Optional[Category] = None
    next_step: Optional[str] = Field(default=None, max_length=500)


class Alert(BaseModel):
    id: int
    item_id: Optional[int]
    kind: str
    message: str
    url: Optional[str] = None
    seen: bool
    created_at: datetime
    item_title: Optional[str] = None


# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def days_ago_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        for col, ddl in MIGRATIONS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE items ADD COLUMN {col} {ddl}")
        conn.executescript(POST_MIGRATION_INDEXES)


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data.pop("raw_text", None)
    data.pop("sha256", None)
    data["tags"] = json.loads(data.get("tags") or "[]")
    data["meta"] = json.loads(data.get("meta") or "{}")
    for key in ("is_read", "featured", "kept", "archived"):
        data[key] = bool(data.get(key))
    return Item.model_validate(data)


# --------------------------------------------------------------------------- #
# Item CRUD
# --------------------------------------------------------------------------- #
def create_item(*, title: str, raw_text: str, content_type: str, url: str | None = None,
                source: str | None = None, file_name: str | None = None,
                sha256: str | None = None, meta: dict | None = None) -> Item:
    ts = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO items (title, url, source, content_type, raw_text, status, file_name,
                                  sha256, meta, created_at, updated_at, last_touched_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
            (title, url, source, content_type, raw_text, file_name, sha256,
             json.dumps(meta or {}), ts, ts, ts),
        )
        item_id = cur.lastrowid
    return get_item(item_id)  # type: ignore[return-value]


def get_item(item_id: int) -> Item | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def get_items(ids: list[int]) -> dict[int, Item]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM items WHERE id IN ({marks})", ids).fetchall()
    return {r["id"]: _row_to_item(r) for r in rows}


def get_raw_text(item_id: int) -> tuple[str, str] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT title, raw_text FROM items WHERE id = ?", (item_id,)).fetchone()
    return (row["title"], row["raw_text"]) if row else None


def set_raw_text(item_id: int, raw_text: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE items SET raw_text = ?, updated_at = ? WHERE id = ?", (raw_text, now_iso(), item_id))


def find_by_url(url: str) -> Item | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM items WHERE url = ? ORDER BY id DESC LIMIT 1", (url,)).fetchone()
    return _row_to_item(row) if row else None


def find_by_sha(sha: str) -> Item | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM items WHERE sha256 = ? LIMIT 1", (sha,)).fetchone()
    return _row_to_item(row) if row else None


def list_items(category: str | None = None, include_read: bool = True,
               archived: bool | None = False, content_type: str | None = None,
               limit: int | None = None) -> list[Item]:
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if category and category != "all":
        sql += " AND category = ?"
        args.append(category)
    if not include_read:
        sql += " AND is_read = 0"
    if archived is not None:
        sql += " AND archived = ?"
        args.append(int(archived))
    if content_type:
        sql += " AND content_type = ?"
        args.append(content_type)
    sql += " ORDER BY featured DESC, created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_item(r) for r in rows]


BOOL_FIELDS = ("is_read", "featured", "kept", "archived")
TOUCH_FIELDS = {"is_read", "featured", "kept", "archived", "category", "next_step"}


def update_item(item_id: int, **fields) -> Item | None:
    if not fields:
        return get_item(item_id)
    ts = now_iso()
    if "tags" in fields:
        fields["tags"] = json.dumps(fields["tags"])
    if "meta" in fields:
        fields["meta"] = json.dumps(fields["meta"], default=str)
    if "is_read" in fields:
        fields["read_at"] = ts if fields["is_read"] else None
    if "archived" in fields:
        fields["archived_at"] = ts if fields["archived"] else None
    for key in BOOL_FIELDS:
        if key in fields:
            fields[key] = int(bool(fields[key]))
    if TOUCH_FIELDS & fields.keys():
        fields["last_touched_at"] = ts
    fields["updated_at"] = ts
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE items SET {cols} WHERE id = ?", (*fields.values(), item_id))
    return get_item(item_id)


def merge_meta(item_id: int, patch: dict) -> Item | None:
    item = get_item(item_id)
    if not item:
        return None
    return update_item(item_id, meta={**item.meta, **patch})


def touch(item_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE items SET last_touched_at = ? WHERE id = ?", (now_iso(), item_id))


def delete_item(item_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0


def category_counts() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM items WHERE archived = 0 GROUP BY category"
        ).fetchall()
        archived = conn.execute("SELECT COUNT(*) FROM items WHERE archived = 1").fetchone()[0]
    return {**{r["category"]: r["n"] for r in rows}, "archived": archived}


# --------------------------------------------------------------------------- #
# Habits: auto-archive + honest stats
# --------------------------------------------------------------------------- #
def auto_archive(days: int = 60) -> list[int]:
    """Archive unread, un-kept items nobody has touched for `days`. Returns ids."""
    cutoff = days_ago_iso(days)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id FROM items
               WHERE archived = 0 AND kept = 0 AND is_read = 0 AND featured = 0
                 AND COALESCE(last_touched_at, created_at) < ?""",
            (cutoff,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            ts = now_iso()
            conn.executemany(
                "UPDATE items SET archived = 1, archived_at = ?, updated_at = ? WHERE id = ?",
                [(ts, ts, i) for i in ids],
            )
    return ids


def weekly_stats(weeks: int = 8) -> list[dict]:
    """Saved vs read per ISO week, oldest first."""
    now = datetime.now(timezone.utc)
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    with get_conn() as conn:
        for w in range(weeks - 1, -1, -1):
            start = start_of_week - timedelta(weeks=w)
            end = start + timedelta(weeks=1)
            s, e = start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")
            saved = conn.execute("SELECT COUNT(*) FROM items WHERE created_at >= ? AND created_at < ?", (s, e)).fetchone()[0]
            read = conn.execute("SELECT COUNT(*) FROM items WHERE read_at >= ? AND read_at < ?", (s, e)).fetchone()[0]
            archived = conn.execute("SELECT COUNT(*) FROM items WHERE archived_at >= ? AND archived_at < ?", (s, e)).fetchone()[0]
            out.append({"week_start": start.date().isoformat(), "saved": saved, "read": read, "archived": archived})
    return out


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
def add_alert(item_id: int | None, kind: str, message: str, url: str | None = None,
              dedupe_key: str | None = None) -> bool:
    """Insert an alert; returns False if an alert with the same dedupe_key exists."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO alerts (item_id, kind, message, url, dedupe_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (item_id, kind, message, url, dedupe_key, now_iso()),
        )
    return cur.rowcount > 0


def list_alerts(include_seen: bool = False, limit: int = 50) -> list[Alert]:
    sql = """SELECT a.*, i.title AS item_title FROM alerts a LEFT JOIN items i ON i.id = a.item_id"""
    if not include_seen:
        sql += " WHERE a.seen = 0"
    sql += f" ORDER BY a.created_at DESC LIMIT {int(limit)}"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [Alert.model_validate({**dict(r), "seen": bool(r["seen"])}) for r in rows]


def mark_alerts_seen(ids: list[int] | None = None) -> None:
    with get_conn() as conn:
        if ids:
            conn.executemany("UPDATE alerts SET seen = 1 WHERE id = ?", [(i,) for i in ids])
        else:
            conn.execute("UPDATE alerts SET seen = 1")


# --------------------------------------------------------------------------- #
# Watched files
# --------------------------------------------------------------------------- #
def watched_file_known(path: str, sha: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT sha256 FROM watched_files WHERE path = ?", (path,)).fetchone()
    return bool(row and row["sha256"] == sha)


def record_watched_file(path: str, sha: str, item_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO watched_files (path, sha256, item_id, ingested_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET sha256 = excluded.sha256,
                   item_id = excluded.item_id, ingested_at = excluded.ingested_at""",
            (path, sha, item_id, now_iso()),
        )
