"""
Folio API — FastAPI app & routing.

Run:  uvicorn main:app --reload --port 8000   (from the backend/ folder)
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import ai_service
import database as db
import embeddings
import enrich
import files
import pipeline
import watcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("folio.api")

STATE: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    stop = threading.Event()
    STATE["watcher"] = watcher.FolderWatcher().start()
    if os.getenv("FOLIO_MAINTENANCE", "1") == "1":
        threading.Thread(target=pipeline.maintenance_loop, args=(stop,), daemon=True,
                         name="folio-maintenance").start()
    log.info("Folio ready · db=%s · llm=%s · embed=%s · vectors=%s · watch=%s",
             db.DB_PATH, ai_service.OLLAMA_MODEL, embeddings.EMBED_MODEL,
             "sqlite-vec" if embeddings.HAS_SQLITE_VEC else "numpy", STATE["watcher"].mode)
    yield
    stop.set()
    STATE["watcher"].stop()


app = FastAPI(title="Folio", version="2.0.0", description="Your Digital Life, Curated.", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FOLIO_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    # Browser extensions call the API from chrome-extension:// / moz-extension:// origins.
    allow_origin_regex=r"^(chrome|moz)-extension://.*$",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    w = STATE.get("watcher")
    return {"ok": True, "ollama": ai_service.ollama_status(), "index": embeddings.index_stats(),
            "watcher": w.status() if w else {"mode": "off", "dirs": []}}


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
@app.post("/api/ingest", response_model=db.Item, status_code=201)
def ingest(payload: db.IngestRequest, background: BackgroundTasks, response: Response):
    """Save a URL, raw text or a note. URLs are scraped (nav/footer/ads stripped);
    the item is stored with status='pending' and curated in the background."""
    item, dup = pipeline.ingest_input(payload)
    if dup:
        response.status_code = 200
        response.headers["X-Folio-Duplicate"] = "1"
        return item
    background.add_task(pipeline.process_item, item.id)
    return item


@app.post("/api/ingest/file", response_model=list[db.Item], status_code=201)
async def ingest_files(background: BackgroundTasks, uploads: list[UploadFile] = File(...)):
    """Upload PDFs, screenshots/images or text files (multipart, field name 'uploads')."""
    out = []
    for up in uploads:
        data = await up.read()
        try:
            item, dup = pipeline.ingest_file(data, up.filename or "upload", origin="upload")
        except files.FileError as exc:
            raise HTTPException(415 if "Unsupported" in str(exc) else 413, str(exc))
        if not dup:
            background.add_task(pipeline.process_item, item.id)
        out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #
@app.get("/api/items", response_model=list[db.Item])
def list_items(category: Optional[str] = None, include_read: bool = True,
               archived: Literal["false", "true", "all"] = "false", type: Optional[str] = None):
    flag = {"false": False, "true": True, "all": None}[archived]
    return db.list_items(category=category, include_read=include_read, archived=flag, content_type=type)


@app.get("/api/items/{item_id}", response_model=db.Item)
def get_item(item_id: int):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@app.patch("/api/items/{item_id}", response_model=db.Item)
def patch_item(item_id: int, patch: db.ItemUpdate):
    if not db.get_item(item_id):
        raise HTTPException(404, "Item not found")
    return db.update_item(item_id, **patch.model_dump(exclude_none=True))


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    embeddings.delete_item_index(item_id)
    db.delete_item(item_id)
    if fp := item.meta.get("file_path"):
        Path(fp).unlink(missing_ok=True)


@app.post("/api/items/{item_id}/reprocess", response_model=db.Item)
def reprocess(item_id: int, background: BackgroundTasks):
    """Re-run the pipeline, e.g. after starting Ollama or pulling a model."""
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item.meta.get("kind") in {"repo", "paper", "docs"}:
        db.update_item(item_id, meta={k: v for k, v in item.meta.items() if k != "kind"})
    item = db.update_item(item_id, status="pending", error=None)
    background.add_task(pipeline.process_item, item_id)
    return item


@app.get("/api/items/{item_id}/similar")
def similar(item_id: int, limit: int = Query(5, ge=1, le=20)):
    return [{"item": it, "similarity": round(s, 4)} for it, s in embeddings.similar_items(item_id, limit)]


@app.get("/api/items/{item_id}/file")
def item_file(item_id: int):
    item = db.get_item(item_id)
    fp = item.meta.get("file_path") if item else None
    if not fp or not Path(fp).exists():
        raise HTTPException(404, "No stored file for this item")
    return FileResponse(fp, filename=item.file_name or Path(fp).name)


@app.get("/api/categories")
def categories():
    counts = db.category_counts()
    live = {k: v for k, v in counts.items() if k != "archived"}
    return {"all": sum(live.values()), **{c: live.get(c, 0) for c in (*ai_service.CATEGORIES, "uncategorized")},
            "archived": counts.get("archived", 0)}


@app.get("/api/projects", response_model=list[db.Item])
def projects():
    """'Build' items as project cards: things you meant to make, with a first step."""
    return [i for i in db.list_items(category="build", archived=False) if not i.is_read]


# --------------------------------------------------------------------------- #
# Search + Q&A
# --------------------------------------------------------------------------- #
@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=500), limit: int = Query(12, ge=1, le=50),
           mode: Literal["hybrid", "semantic", "keyword"] = "hybrid",
           category: Optional[str] = None, include_archived: bool = True):
    hits, info = embeddings.search(q, limit=limit, mode=mode, category=category,
                                   include_archived=include_archived)
    return {"query": q, "retrieval": info,
            "results": [{"item": h.item, "score": h.score, "similarity": h.similarity,
                         "snippet": h.snippet, "matched": h.matched} for h in hits]}


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=6, ge=1, le=12)


@app.post("/api/ask")
def ask(req: AskRequest):
    """Answer a question from your own library, citing the items used."""
    return pipeline.ask_library(req.question, k=req.k)


@app.post("/api/reindex")
def reindex(background: BackgroundTasks, only_missing: bool = True):
    ids = embeddings.missing_vectors() if only_missing else [i.id for i in db.list_items(archived=None)]

    def run():
        for iid in ids:
            embeddings.index_item(iid)

    background.add_task(run)
    return {"queued": len(ids)}


# --------------------------------------------------------------------------- #
# Habits
# --------------------------------------------------------------------------- #
@app.get("/api/stats")
def stats(weeks: int = Query(8, ge=1, le=52)):
    """The honest numbers: how much you save versus how much you read."""
    series = db.weekly_stats(weeks)
    this = series[-1]
    items = db.list_items(archived=None)
    unread_live = sum(1 for i in items if not i.is_read and not i.archived)
    total_saved = sum(w["saved"] for w in series)
    total_read = sum(w["read"] for w in series)
    return {"weeks": series, "this_week": this,
            "read_ratio": round(total_read / total_saved, 3) if total_saved else None,
            "unread": unread_live, "kept": sum(1 for i in items if i.kept),
            "archived": sum(1 for i in items if i.archived),
            "archive_after_days": pipeline.ARCHIVE_AFTER_DAYS}


@app.post("/api/maintenance")
def maintenance(check_updates: bool = False):
    """Run auto-archive + re-embedding now (optionally the update checks too)."""
    return pipeline.run_maintenance(check_updates=check_updates)


# --------------------------------------------------------------------------- #
# Alerts (repo releases, follow-up papers, outdated docs)
# --------------------------------------------------------------------------- #
@app.get("/api/alerts", response_model=list[db.Alert])
def alerts(include_seen: bool = False):
    return db.list_alerts(include_seen=include_seen)


class SeenRequest(BaseModel):
    ids: Optional[list[int]] = None


@app.post("/api/alerts/seen", status_code=204)
def alerts_seen(req: SeenRequest):
    db.mark_alerts_seen(req.ids)


@app.post("/api/alerts/refresh")
def alerts_refresh(background: BackgroundTasks):
    background.add_task(enrich.check_all)
    return {"queued": True}


