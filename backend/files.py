"""
File ingestion: PDFs, screenshots/images and plain-text files.

* PDFs   -> text via pypdf. Scanned PDFs (no text layer) fall back to running
            the vision model on the page images embedded in the file.
* Images -> downscaled with Pillow, then a local vision model (gemma3 / llava)
            transcribes visible text and describes the picture.
* Text   -> .md / .txt / .html read directly.

Originals are copied into FOLIO_FILES_DIR (content-addressed by SHA-256) so the
UI can show thumbnails and open the source, and duplicates are detected.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import ai_service

log = logging.getLogger("folio.files")

FILES_DIR = Path(os.getenv("FOLIO_FILES_DIR", Path(__file__).parent / "files"))
MAX_FILE_BYTES = int(os.getenv("FOLIO_MAX_FILE_MB", "50")) * 1024 * 1024
MAX_PDF_PAGES = 60
MAX_VISION_PAGES = 3

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".html", ".htm"}
SUPPORTED_EXT = PDF_EXT | IMAGE_EXT | TEXT_EXT

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


class FileError(Exception):
    pass


@dataclass
class ExtractedFile:
    title: str
    text: str
    content_type: str  # "pdf" | "image" | "text"
    meta: dict = field(default_factory=dict)
    error: str | None = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kind_of(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext in TEXT_EXT:
        return "text"
    return None


def store(data: bytes, filename: str) -> tuple[str, Path]:
    """Copy into the content-addressed store. Returns (sha, path)."""
    if len(data) > MAX_FILE_BYTES:
        raise FileError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    digest = sha256(data)
    ext = Path(filename).suffix.lower() or ".bin"
    path = FILES_DIR / digest[:2] / f"{digest}{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return digest, path


def _title_from_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem[:120] or "Untitled file"


def _is_generic_name(filename: str) -> bool:
    return bool(re.match(r"(?i)^(screen ?shot|screenshot|img|image|photo|pxl|dsc|capture|scan)[\s_\-]*[\d\-_. at]*$",
                         Path(filename).stem))


def _first_line_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip().strip("#*>-• ").strip()
        if 8 <= len(line) <= 120 and not line.lower().startswith(("description:", "http")):
            return line
    return None


# --------------------------------------------------------------------------- #
# Extractors
# --------------------------------------------------------------------------- #
def _prep_image(data: bytes, max_side: int = 1600) -> bytes:
    from PIL import Image  # Pillow is a hard dependency for image ingestion

    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def extract_image(data: bytes, filename: str) -> ExtractedFile:
    try:
        png = _prep_image(data)
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            size = im.size
    except Exception as exc:  # noqa: BLE001
        return ExtractedFile(_title_from_name(filename), "", "image", error=f"unreadable image: {exc}")
    text, err = ai_service.describe_image(png)
    title = (_first_line_title(text) if _is_generic_name(filename) else None) or _title_from_name(filename)
    return ExtractedFile(title, text, "image",
                         meta={"kind": "image", "width": size[0], "height": size[1],
                               "urls_found": sorted(set(_URL_RE.findall(text)))[:10],
                               "vision_model": ai_service.VISION_MODEL if text else None},
                         error=err)


def extract_pdf(data: bytes, filename: str) -> ExtractedFile:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        return ExtractedFile(_title_from_name(filename), "", "pdf", error=f"unreadable PDF: {exc}")

    pages = reader.pages
    texts = []
    for page in list(pages)[:MAX_PDF_PAGES]:
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one bad page shouldn't sink the file
            texts.append("")
    text = "\n\n".join(t.strip() for t in texts if t.strip())
    meta: dict = {"kind": "pdf", "pages": len(pages)}

    info = reader.metadata or {}
    doc_title = (getattr(info, "title", None) or "").strip()
    if getattr(info, "author", None):
        meta["author"] = str(info.author).strip()

    err = None
    if len(text) < 100:  # probably scanned: try vision on embedded page images
        meta["scanned"] = True
        ocr = []
        for page in list(pages)[:MAX_VISION_PAGES]:
            try:
                for img in list(page.images)[:1]:
                    t, e = ai_service.describe_image(_prep_image(img.data))
                    if t:
                        ocr.append(t)
                    err = err or e
            except Exception as exc:  # noqa: BLE001
                err = err or f"page image extraction failed: {exc}"
        text = "\n\n".join(ocr) or text

    meta["urls_found"] = sorted(set(_URL_RE.findall(text)))[:10]
    arxiv = re.search(r"arXiv:(\d{4}\.\d{4,5})", text[:3000])
    if arxiv:
        meta["arxiv_id"] = arxiv.group(1)
    title = (doc_title if len(doc_title) > 4 and not doc_title.lower().startswith(("microsoft word", "untitled")) else None) \
        or _first_line_title(text[:2000]) or _title_from_name(filename)
    return ExtractedFile(title[:200], text, "pdf", meta=meta, error=err)


def extract_text_file(data: bytes, filename: str) -> ExtractedFile:
    raw = data.decode("utf-8", errors="replace")
    if Path(filename).suffix.lower() in {".html", ".htm"}:
        from scraper import parse_html

        parsed = parse_html(raw, f"file://{filename}")
        return ExtractedFile(parsed.title or _title_from_name(filename), parsed.text, "text", meta={"kind": "file"})
    return ExtractedFile(_first_line_title(raw) or _title_from_name(filename), raw, "text", meta={"kind": "file"})


def extract(data: bytes, filename: str) -> ExtractedFile:
    kind = kind_of(filename)
    if kind == "pdf":
        return extract_pdf(data, filename)
    if kind == "image":
        return extract_image(data, filename)
    if kind == "text":
        return extract_text_file(data, filename)
    raise FileError(f"Unsupported file type: {Path(filename).suffix or filename}")
