"""
The ingestion + curation pipeline, shared by the API, the folder watcher and
other local clients.

    ingest_input / ingest_file      fast: save item with status=pending
    process_item                    slow, background:
        1. extract text from files (PDF / vision model)
        2. enrich developer content (GitHub / arXiv / docs versions)
        3. summarise + categorise with the local LLM
        4. chunk + embed for semantic search
    ask_library                     hybrid retrieval + grounded answer
    maintenance_loop                auto-archive, update checks, re-embedding
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import ai_service
import database as db
import embeddings
import enrich
import files
import scraper

log = logging.getLogger("folio.pipeline")

# Small local machines choke on parallel model calls; serialise the heavy work.
AI_LOCK = threading.Semaphore(int(os.getenv("FOLIO_AI_CONCURRENCY", "1")))
ARCHIVE_AFTER_DAYS = int(os.getenv("FOLIO_ARCHIVE_AFTER_DAYS", "60"))
REFRESH_HOURS = float(os.getenv("FOLIO_REFRESH_HOURS", "24"))


# --------------------------------------------------------------------------- #
# Ingestion (fast path)
# --------------------------------------------------------------------------- #
def ingest_input(req: db.IngestRequest) -> tuple[db.Item, bool]:
    """URL or text -> pending item. Returns (item, was_duplicate)."""
    raw = req.raw_input
    if scraper.is_url(raw):
        if existing := db.find_by_url(raw):
            db.touch(existing.id)
            return existing, True
        error = None
        try:
            content = scraper.scrape_url(raw)
        except scraper.ScrapeError as exc:
            # Keep the link anyway; enrichment and the AI can still work from the URL.
            error = str(exc)[:500]
            content = scraper.ScrapedContent(title=req.title or scraper.domain_of(raw) or raw, text="",
                                             content_type=scraper.detect_content_type(raw),
                                             url=raw, source=scraper.domain_of(raw))
        if req.title and (not content.title or content.title == content.source):
            content.title = req.title
        if req.url and req.text and req.text.strip():
            content.text = f"USER NOTE: {req.text.strip()}\n\n{content.text}"
    else:
        content = scraper.parse_text(raw)
        if req.title:
            content.title = req.title
        error = None

    item = db.create_item(title=content.title, raw_text=content.text or content.title,
                          content_type=content.content_type, url=content.url, source=content.source)
    if error:
        item = db.update_item(item.id, error=error)
    return item, False


def ingest_file(data: bytes, filename: str, origin: str = "upload") -> tuple[db.Item, bool]:
    """Store a file and create a pending item. Extraction happens in process_item."""
    kind = files.kind_of(filename)
    if not kind:
        raise files.FileError(f"Unsupported file type: {Path(filename).suffix or filename}")
    digest, path = files.store(data, filename)
    if existing := db.find_by_sha(digest):
        db.touch(existing.id)
        return existing, True
    item = db.create_item(title=files._title_from_name(filename), raw_text="", content_type=kind,
                          file_name=filename, sha256=digest,
                          meta={"file_path": str(path), "origin": origin, "size": len(data)})
    return item, False


# --------------------------------------------------------------------------- #
# Curation (slow path, background)
# --------------------------------------------------------------------------- #
def process_item(item_id: int) -> None:
    """Run the full pipeline for one item. Never raises."""
    errors: list[str] = []
    try:
        with AI_LOCK:
            item = db.get_item(item_id)
            row = db.get_raw_text(item_id)
            if not item or not row:
                return  # deleted before we got to it
            title, raw = row
            db.update_item(item_id, status="processing")

            # 1. Files -> text
            if item.meta.get("file_path") and not raw.strip():
                try:
                    data = Path(item.meta["file_path"]).read_bytes()
                    ext = files.extract(data, item.file_name or Path(item.meta["file_path"]).name)
                    raw, title = ext.text, ext.title
                    db.set_raw_text(item_id, raw)
                    db.update_item(item_id, title=title)
                    db.merge_meta(item_id, ext.meta)
                    if ext.error:
                        errors.append(ext.error)
                    # A PDF of an arXiv paper gets the same treatment as the link would.
                    if ext.meta.get("arxiv_id"):
                        pm, extra, err = enrich.enrich(f"https://arxiv.org/abs/{ext.meta['arxiv_id']}")
                        if pm:
                            db.merge_meta(item_id, {**pm, "kind": "paper"})
                            title = pm.get("paper_title") or title
                            db.update_item(item_id, title=title, url=f"https://arxiv.org/abs/{ext.meta['arxiv_id']}",
                                           source="arxiv.org")
                        if err:
                            errors.append(err)
                except (OSError, files.FileError) as exc:
                    errors.append(f"file extraction failed: {exc}")

            # 2. Developer-aware enrichment
            item = db.get_item(item_id)
            if item.url and not item.meta.get("kind"):
                meta, extra, err = enrich.enrich(item.url, raw)
                if meta:
                    db.merge_meta(item_id, meta)
                    if meta.get("kind") == "repo":
                        db.update_item(item_id, content_type="repo", title=meta.get("full_name") or title)
                    elif meta.get("kind") == "paper":
                        db.update_item(item_id, content_type="paper", title=meta.get("paper_title") or title)
                    elif meta.get("kind") == "docs":
                        db.update_item(item_id, content_type="documentation")
                if extra:
                    raw = f"{extra}\n\n{raw}".strip()
                    db.set_raw_text(item_id, raw)
                if err:
                    errors.append(err)

            # 3. Summarise + categorise
            item = db.get_item(item_id)
            analysis, err = ai_service.analyze_item(item.title, raw, item.content_type,
                                                    hints=enrich.hints_for_model(item.meta))
            if err:
                errors.append(err)
            db.update_item(item_id, summary=analysis.summary, category=analysis.category,
                           tags=analysis.tags, next_step=analysis.next_step)

            # 4. Embed for search / Q&A
            res = embeddings.index_item(item_id)
            if res["error"]:
                errors.append(f"embedding: {res['error']}")

            db.update_item(item_id, status="done", error="; ".join(errors)[:800] or None)

            # 5. A save can already be out of date (old docs, an old release link)
            enrich.check_item(db.get_item(item_id))
            log.info("Item %s → %s %s (%d chunks%s)", item_id, analysis.category, analysis.tags,
                     res["chunks"], ", fallbacks: " + "; ".join(errors) if errors else "")
    except Exception as exc:  # noqa: BLE001
        log.exception("Pipeline crashed for item %s", item_id)
        try:
            db.update_item(item_id, status="failed", error=str(exc)[:500])
        except Exception:  # noqa: BLE001
            pass


def process_in_thread(item_id: int) -> None:
    threading.Thread(target=process_item, args=(item_id,), daemon=True, name=f"folio-item-{item_id}").start()


# --------------------------------------------------------------------------- #
# Q&A
# --------------------------------------------------------------------------- #
def ask_library(question: str, k: int = 6) -> dict:
    hits, info = embeddings.search(question, limit=k)
    chunk_ids = [cid for h in hits for cid in h.chunk_ids[:2]]
    texts = embeddings.chunk_texts(chunk_ids)
    contexts = []
    for h in hits:
        body = "\n".join(texts[c] for c in h.chunk_ids[:2] if c in texts) or h.snippet
        contexts.append((h.item.id, h.item.title, body[:1500]))
    answer, err = ai_service.answer_question(question, contexts)
    cited = set(answer.cited_ids)
    sources = [{"id": h.item.id, "title": h.item.title, "url": h.item.url, "category": h.item.category,
                "snippet": h.snippet, "cited": h.item.id in cited} for h in hits]
    return {"question": question, "answer": answer.answer, "cited_ids": answer.cited_ids,
            "sources": sources, "retrieval": info, "error": err}


# --------------------------------------------------------------------------- #
# Maintenance
# --------------------------------------------------------------------------- #
def run_maintenance(check_updates: bool = True) -> dict:
    archived = db.auto_archive(ARCHIVE_AFTER_DAYS)
    reindexed = 0
    for iid in embeddings.missing_vectors()[:50]:  # embed model may have come online since
        if embeddings.index_item(iid)["embedded"]:
            reindexed += 1
    updates = enrich.check_all() if check_updates else {"checked": 0, "new_alerts": []}
    return {"archived": archived, "reindexed": reindexed, **updates}


def maintenance_loop(stop: threading.Event, interval_s: float = 3600) -> None:
    """Hourly: archive + re-embed. Every REFRESH_HOURS: repo/paper/docs update checks."""
    last_refresh = 0.0
    import time

    while not stop.wait(5 if last_refresh == 0 else interval_s):
        try:
            due = time.time() - last_refresh >= REFRESH_HOURS * 3600
            res = run_maintenance(check_updates=due)
            if due:
                last_refresh = time.time()
            if res["archived"] or res["reindexed"] or res["new_alerts"]:
                log.info("Maintenance: archived %d, re-embedded %d, %d new alerts",
                         len(res["archived"]), res["reindexed"], len(res["new_alerts"]))
        except Exception:  # noqa: BLE001
            log.exception("Maintenance run failed")
