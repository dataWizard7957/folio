"""
Folder watcher: drop a screenshot or PDF into a watched folder and it shows
up in Folio, curated.

Configure with FOLIO_WATCH_DIRS (paths separated by ':' on macOS/Linux, ';' on
Windows), e.g.

    FOLIO_WATCH_DIRS="~/Desktop:~/Downloads:~/Pictures/Screenshots"

Uses `watchdog` for native file events when installed, otherwise polls every
few seconds. Only files that appear *after* Folio starts are ingested, unless
FOLIO_WATCH_BACKFILL=1, which also imports what's already there.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import database as db
import files
import pipeline

log = logging.getLogger("folio.watch")

IGNORE_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".partial", ".icloud"}
STABLE_SECONDS = 1.5   # wait until the file stops growing (screenshots / downloads)
POLL_SECONDS = 4.0

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:  # pragma: no cover
    HAS_WATCHDOG = False
    FileSystemEventHandler = object  # type: ignore[assignment,misc]


def watch_dirs() -> list[Path]:
    raw = os.getenv("FOLIO_WATCH_DIRS", "").strip()
    if not raw:
        return []
    out = []
    for part in raw.split(os.pathsep):
        p = Path(os.path.expanduser(part.strip())).resolve()
        if part.strip() and p.is_dir():
            out.append(p)
        elif part.strip():
            log.warning("Watch folder does not exist, skipping: %s", p)
    return out


def _eligible(path: Path) -> bool:
    name = path.name
    return (path.is_file() and not name.startswith(".") and not name.startswith("~$")
            and path.suffix.lower() not in IGNORE_SUFFIXES and files.kind_of(name) is not None)


def _wait_stable(path: Path, timeout: float = 60) -> bool:
    deadline, last = time.time() + timeout, -1
    while time.time() < deadline:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last and size > 0:
            return True
        last = size
        time.sleep(STABLE_SECONDS)
    return False


def ingest_path(path: Path) -> int | None:
    """Ingest one file from disk if it's new. Returns the item id (or None)."""
    if not _eligible(path) or not _wait_stable(path):
        return None
    try:
        data = path.read_bytes()
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None
    digest = files.sha256(data)
    if db.watched_file_known(str(path), digest):
        return None
    try:
        item, dup = pipeline.ingest_file(data, path.name, origin=f"watch:{path.parent}")
    except files.FileError as exc:
        log.warning("Skipping %s: %s", path, exc)
        db.record_watched_file(str(path), digest, None)
        return None
    db.record_watched_file(str(path), digest, item.id)
    if not dup:
        log.info("Watcher picked up %s → item %s", path.name, item.id)
        pipeline.process_item(item.id)
    return item.id


class _Handler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, queue: "set[Path]", lock: threading.Lock):
        self.queue, self.lock = queue, lock

    def _add(self, p: str) -> None:
        with self.lock:
            self.queue.add(Path(p))

    def on_created(self, event):  # noqa: D401
        if not event.is_directory:
            self._add(event.src_path)

    def on_moved(self, event):  # browsers rename .crdownload -> final name
        if not event.is_directory:
            self._add(event.dest_path)


class FolderWatcher:
    def __init__(self, dirs: list[Path] | None = None):
        self.dirs = dirs if dirs is not None else watch_dirs()
        self.stop_event = threading.Event()
        self.queue: set[Path] = set()
        self.lock = threading.Lock()
        self.observer = None
        self.mode = "off"

    def start(self) -> "FolderWatcher":
        if not self.dirs:
            return self
        if os.getenv("FOLIO_WATCH_BACKFILL") == "1":
            for d in self.dirs:
                self.queue.update(p for p in d.iterdir() if p.is_file())
        if HAS_WATCHDOG:
            self.observer = Observer()
            handler = _Handler(self.queue, self.lock)
            for d in self.dirs:
                self.observer.schedule(handler, str(d), recursive=False)
            self.observer.start()
            self.mode = "events"
        else:
            self._seen = {p for d in self.dirs for p in d.iterdir()}
            self.mode = "polling"
        threading.Thread(target=self._worker, daemon=True, name="folio-watcher").start()
        log.info("Watching %s (%s)", ", ".join(map(str, self.dirs)), self.mode)
        return self

    def _worker(self) -> None:
        while not self.stop_event.wait(1.0 if self.mode == "events" else POLL_SECONDS):
            if self.mode == "polling":
                current = {p for d in self.dirs for p in d.iterdir()}
                with self.lock:
                    self.queue.update(current - self._seen)
                self._seen = current
            with self.lock:
                batch, self.queue = list(self.queue), set()
            for p in batch:
                try:
                    ingest_path(p)
                except Exception:  # noqa: BLE001
                    log.exception("Watcher failed on %s", p)

    def stop(self) -> None:
        self.stop_event.set()
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

    def status(self) -> dict:
        return {"mode": self.mode, "dirs": [str(d) for d in self.dirs]}
