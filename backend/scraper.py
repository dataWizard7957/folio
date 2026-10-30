"""
Universal ingestion: URL parsing, boilerplate stripping and content-type detection.

Everything here is synchronous and side-effect free apart from the HTTP fetch,
so it can be unit-tested with plain HTML strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 Folio/1.0"
)
REQUEST_TIMEOUT = 15
MAX_TEXT_CHARS = 20_000

# Tags that never carry article content.
BOILERPLATE_TAGS = [
    "script", "style", "noscript", "iframe", "svg", "canvas", "form", "button",
    "nav", "header", "footer", "aside", "template", "dialog",
]

# class/id fragments that usually mark ads, menus and other chrome.
NOISE_RE = re.compile(
    r"(^|[-_\s])("
    r"ad|ads|advert|advertisement|banner|cookie|consent|gdpr|newsletter|subscribe|"
    r"promo|sponsor|sponsored|share|sharing|social|related|recommended|comments?|"
    r"sidebar|popup|modal|breadcrumbs?|navbar|menu|footer|header|masthead|paywall|signup"
    r")([-_\s]|$)",
    re.IGNORECASE,
)
PROTECTED_TAGS = {"html", "body", "main", "article"}


class ScrapeError(Exception):
    """Raised when a URL cannot be fetched or parsed."""


@dataclass
class ScrapedContent:
    title: str
    text: str
    content_type: str
    url: str | None = None
    source: str | None = None


# --------------------------------------------------------------------------- #
# Detection helpers
# --------------------------------------------------------------------------- #
def is_url(value: str) -> bool:
    value = value.strip()
    return bool(re.match(r"^https?://\S+$", value, re.IGNORECASE))


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def detect_content_type(url: str | None, text: str = "") -> str:
    """Cheap heuristics; the AI later decides the *category*, this is the *format*."""
    if url:
        host = domain_of(url)
        path = urlparse(url).path.lower()
        if host in {"github.com", "gitlab.com", "bitbucket.org", "huggingface.co"}:
            return "repo"
        if host in {"arxiv.org", "openreview.net", "paperswithcode.com"} or path.endswith(".pdf"):
            return "paper"
        if host in {"youtube.com", "youtu.be", "vimeo.com", "m.youtube.com"}:
            return "video"
        if host.startswith(("docs.", "developer.", "dev.")) or "/docs" in path or "/reference" in path:
            return "documentation"
        return "article"
    return "note" if len(text) < 600 else "text"


# --------------------------------------------------------------------------- #
# HTML cleaning
# --------------------------------------------------------------------------- #
def _clean_text(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 2:
            continue
        if lines and lines[-1] == line:  # collapse repeated lines
            continue
        lines.append(line)
    return "\n".join(lines)[:MAX_TEXT_CHARS]


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            return meta["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return domain_of(url)


def _meta_description(soup: BeautifulSoup) -> str:
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            return meta["content"].strip()
    return ""


def parse_html(html: str, url: str) -> ScrapedContent:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup, url)
    description = _meta_description(soup)

    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()

    for el in list(soup.find_all(True)):
        if not isinstance(el, Tag) or el.decomposed or el.name in PROTECTED_TAGS:
            continue
        attrs = el.attrs or {}
        if attrs.get("role") in {"navigation", "banner", "contentinfo", "complementary"}:
            el.decompose()
            continue
        marker = " ".join(attrs.get("class", [])) + " " + str(attrs.get("id", ""))
        if marker.strip() and NOISE_RE.search(marker):
            el.decompose()

    root = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )
    text = _clean_text(root.get_text(separator="\n"))
    if len(text) < 200 and description:
        text = f"{description}\n{text}".strip()

    return ScrapedContent(
        title=title[:300],
        text=text,
        content_type=detect_content_type(url, text),
        url=url,
        source=domain_of(url),
    )


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def scrape_url(url: str) -> ScrapedContent:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ScrapeError(f"Could not fetch {url}: {exc}") from exc

    ctype = resp.headers.get("content-type", "").lower()
    if "html" not in ctype and "xml" not in ctype:
        name = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or domain_of(url)
        return ScrapedContent(
            title=name,
            text="",
            content_type="paper" if "pdf" in ctype else detect_content_type(url),
            url=url,
            source=domain_of(url),
        )

    resp.encoding = resp.encoding or resp.apparent_encoding
    return parse_html(resp.text, url)


def parse_text(text: str) -> ScrapedContent:
    """Raw text or a quick note: first line becomes the title."""
    text = text.strip()
    first_line = text.splitlines()[0].strip() if text else "Untitled note"
    title = first_line.lstrip("#").strip()
    if len(title) > 90:
        title = title[:90].rsplit(" ", 1)[0] + "…"
    return ScrapedContent(
        title=title or "Untitled note",
        text=_clean_text(text),
        content_type=detect_content_type(None, text),
    )
