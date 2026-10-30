"""
Developer-aware enrichment and update tracking.

Folio knows what it's looking at:
  * GitHub repos  -> description, stars, language, topics, license, last push,
                     latest release, README excerpt. Later: alerts on major
                     releases, new releases, archival and staleness.
  * arXiv papers  -> abstract, authors, dates, primary category, linked code
                     (from the abstract/comments and Hugging Face Papers).
                     Later: alerts when a highly-cited paper cites it
                     (via the Semantic Scholar API).
  * Docs pages    -> which library and version the page documents, compared
                     with the latest release on PyPI / npm, so outdated guides
                     get flagged.

All network calls are best-effort: any failure returns partial metadata and
never blocks ingestion. Set GITHUB_TOKEN to lift GitHub's 60 req/h limit.
"""

from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

import database as db

log = logging.getLogger("folio.enrich")

TIMEOUT = 12
UA = {"User-Agent": "Folio/1.0 (+local-first research library)"}
GITHUB_API = os.getenv("FOLIO_GITHUB_API", "https://api.github.com")
ARXIV_API = os.getenv("FOLIO_ARXIV_API", "https://export.arxiv.org/api/query")
S2_API = os.getenv("FOLIO_S2_API", "https://api.semanticscholar.org/graph/v1")
HF_API = os.getenv("FOLIO_HF_API", "https://huggingface.co/api")
PYPI_API = os.getenv("FOLIO_PYPI_API", "https://pypi.org/pypi")
NPM_API = os.getenv("FOLIO_NPM_API", "https://registry.npmjs.org")
ARXIV_PDF = os.getenv("FOLIO_ARXIV_PDF", "https://arxiv.org/pdf")

STALE_DAYS = int(os.getenv("FOLIO_STALE_DAYS", "365"))
INFLUENTIAL_CITATIONS = int(os.getenv("FOLIO_INFLUENTIAL_CITATIONS", "50"))
README_CHARS = 6000


def _get(url: str, **kw) -> requests.Response:
    headers = {**UA, **kw.pop("headers", {})}
    return requests.get(url, headers=headers, timeout=TIMEOUT, **kw)


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #
_VER = re.compile(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(tag: str | None) -> tuple[int, int, int] | None:
    if not tag:
        return None
    m = _VER.search(tag)
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())  # type: ignore[return-value]


def is_major_bump(old: str | None, new: str | None) -> bool:
    a, b = parse_version(old), parse_version(new)
    if not a or not b:
        return False
    if a[0] == 0 and b[0] == 0:  # 0.x: minor bumps are breaking by semver convention
        return b[1] > a[1]
    return b[0] > a[0]


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
def github_slug(url: str) -> str | None:
    p = urlparse(url)
    if p.netloc.lower().removeprefix("www.") != "github.com":
        return None
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2 or parts[0] in {"orgs", "topics", "search", "features", "marketplace", "settings"}:
        return None
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


_GH_SAVED_TAG = re.compile(r"/(?:releases/tag|tree)/(v?\d+(?:\.\d+)*[^/]*)")


def github_saved_version(url: str) -> str | None:
    """The release a link points at, e.g. /releases/tag/v1.2.0: that's the version the user saved."""
    m = _GH_SAVED_TAG.search(urlparse(url).path)
    return m.group(1) if m else None


def _gh_headers(raw: bool = False) -> dict:
    h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if os.getenv("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return h


def github_repo(slug: str, with_readme: bool = True) -> dict:
    meta: dict = {"kind": "repo", "repo": slug}
    r = _get(f"{GITHUB_API}/repos/{slug}", headers=_gh_headers())
    r.raise_for_status()
    j = r.json()
    meta.update(
        full_name=j.get("full_name", slug), description=j.get("description") or "",
        stars=j.get("stargazers_count"), forks=j.get("forks_count"), language=j.get("language"),
        topics=j.get("topics") or [], license=(j.get("license") or {}).get("spdx_id"),
        pushed_at=j.get("pushed_at"), archived=bool(j.get("archived")),
        homepage=j.get("homepage") or None, open_issues=j.get("open_issues_count"),
    )
    try:
        rel = _get(f"{GITHUB_API}/repos/{slug}/releases/latest", headers=_gh_headers())
        if rel.status_code == 200:
            rj = rel.json()
            meta["latest_release"] = rj.get("tag_name")
            meta["latest_release_at"] = rj.get("published_at")
            meta["latest_release_url"] = rj.get("html_url")
        else:  # no formal releases: fall back to the newest tag
            tags = _get(f"{GITHUB_API}/repos/{slug}/tags", headers=_gh_headers(), params={"per_page": 1})
            if tags.status_code == 200 and tags.json():
                meta["latest_release"] = tags.json()[0].get("name")
    except requests.RequestException:
        pass
    if with_readme:
        try:
            rd = _get(f"{GITHUB_API}/repos/{slug}/readme", headers=_gh_headers(raw=True))
            if rd.status_code == 200:
                meta["readme"] = _clean_markdown(rd.text)[:README_CHARS]
        except requests.RequestException:
            pass
    days = _days_since(meta.get("pushed_at"))
    meta["stale"] = bool(meta.get("archived") or (days is not None and days > STALE_DAYS))
    meta["days_since_push"] = days
    return meta


def _clean_markdown(md: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)            # images / badges
    md = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", md)  # linked badges
    md = re.sub(r"<[^>]+>", "", md)                          # inline html
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)        # links -> text
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


# --------------------------------------------------------------------------- #
# arXiv + citations
# --------------------------------------------------------------------------- #
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_ARXIV_OLD = re.compile(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?")
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv_id(url: str) -> str | None:
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    if host not in {"arxiv.org", "export.arxiv.org", "alphaxiv.org", "huggingface.co"}:
        return None
    if host == "huggingface.co" and not p.path.startswith("/papers/"):
        return None
    m = _ARXIV_NEW.search(p.path) or _ARXIV_OLD.search(p.path)
    return m.group(1) if m else None


def _pdf_code_links(aid: str, limit: int = 3) -> list[str]:
    """Repos the paper itself links to, read from the PDF's text before its references."""
    from io import BytesIO

    from pypdf import PdfReader

    r = _get(f"{ARXIV_PDF}/{aid}")
    r.raise_for_status()
    found: list[str] = []
    for page in PdfReader(BytesIO(r.content)).pages:
        text = page.extract_text() or ""
        refs = re.search(r"^\s*(?:\d+\.?\s*)?references\s*$", text, re.I | re.M)
        for slug in re.findall(r"github\.com/\s*([\w.\-]+/\s*[\w.\-]+)", text[: refs.start()] if refs else text):
            link = "https://github.com/" + re.sub(r"\s+", "", slug).rstrip(".,;")  # URLs wrap across lines
            if link not in found:
                found.append(link)
        if refs or len(found) >= limit:
            break
    return found[:limit]


def arxiv_paper(aid: str) -> dict:
    r = _get(ARXIV_API, params={"id_list": aid, "max_results": 1})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    entry = root.find("a:entry", ATOM)
    if entry is None or entry.find("a:title", ATOM) is None:
        raise ValueError(f"arXiv returned no entry for {aid}")
    txt = lambda tag: re.sub(r"\s+", " ", (entry.findtext(tag, default="", namespaces=ATOM) or "")).strip()  # noqa: E731
    authors = [re.sub(r"\s+", " ", a.findtext("a:name", default="", namespaces=ATOM)).strip()
               for a in entry.findall("a:author", ATOM)]
    comment = txt("arxiv:comment")
    abstract = txt("a:summary")
    prim = entry.find("arxiv:primary_category", ATOM)
    meta = {
        "kind": "paper", "arxiv_id": aid, "paper_title": txt("a:title"), "abstract": abstract,
        "authors": authors, "published": txt("a:published"), "updated": txt("a:updated"),
        "primary_category": prim.get("term") if prim is not None else None, "comment": comment or None,
        "pdf_url": f"https://arxiv.org/pdf/{aid}",
    }
    code = sorted(set(re.findall(r"https?://github\.com/[\w.\-]+/[\w.\-]+", f"{abstract} {comment}")))
    meta["code_links"] = [c.rstrip(".,);") for c in code]
    try:  # Hugging Face Papers often knows the official repo
        hf = _get(f"{HF_API}/papers/{aid}")
        if hf.status_code == 200:
            repo = hf.json().get("githubRepo")
            if repo and repo not in meta["code_links"]:
                meta["code_links"].append(repo)
    except (requests.RequestException, ValueError):
        pass
    if not meta["code_links"]:
        try:
            meta["code_links"] = _pdf_code_links(aid)
        except Exception as exc:  # noqa: BLE001 - pypdf raises many types on odd PDFs
            log.info("Could not read code links from the PDF of %s: %s", aid, exc)
    return meta


def _s2_get(url: str, **kw) -> requests.Response:
    """Semantic Scholar's shared anonymous pool often answers 429, so wait and retry."""
    if os.getenv("S2_API_KEY"):
        kw["headers"] = {"x-api-key": os.environ["S2_API_KEY"]}
    for attempt in range(4):
        r = _get(url, **kw)
        if r.status_code != 429:
            break
        if attempt < 3:
            time.sleep(2 ** (attempt + 1))
    return r


def s2_citation_info(aid: str) -> dict:
    r = _s2_get(f"{S2_API}/paper/arXiv:{aid}", params={"fields": "citationCount,influentialCitationCount,year"})
    r.raise_for_status()
    return r.json()


def s2_influential_followups(aid: str, min_citations: int = INFLUENTIAL_CITATIONS, limit: int = 5) -> list[dict]:
    """Papers that cite `aid` and are themselves highly cited (likely follow-ups / successors)."""
    rows, offset = [], 0
    while offset is not None and offset < 9000:  # the API stops at 10,000 citations
        r = _s2_get(f"{S2_API}/paper/arXiv:{aid}/citations",
                    params={"fields": "title,year,citationCount,externalIds,url,paperId",
                            "limit": 1000, "offset": offset})
        if rows and r.status_code != 200:  # rate-limited mid-way: use what we have
            break
        r.raise_for_status()
        j = r.json()
        rows += [c.get("citingPaper", {}) for c in j.get("data", [])]
        offset = j.get("next")
    rows = [p for p in rows if (p.get("citationCount") or 0) >= min_citations]
    rows.sort(key=lambda p: -(p.get("citationCount") or 0))
    out = []
    for p in rows[:limit]:
        ax = (p.get("externalIds") or {}).get("ArXiv")
        out.append({"paper_id": p.get("paperId"), "title": p.get("title"), "year": p.get("year"),
                    "citations": p.get("citationCount"),
                    "url": f"https://arxiv.org/abs/{ax}" if ax else p.get("url")})
    return out


# --------------------------------------------------------------------------- #
# Docs version tracking
# --------------------------------------------------------------------------- #
# host (and optional path prefix) -> (ecosystem, package)
DOCS_PACKAGES: list[tuple[str, str, str, str]] = [
    ("docs.pydantic.dev", "", "pypi", "pydantic"),
    ("fastapi.tiangolo.com", "", "pypi", "fastapi"),
    ("docs.djangoproject.com", "", "pypi", "django"),
    ("flask.palletsprojects.com", "", "pypi", "flask"),
    ("docs.sqlalchemy.org", "", "pypi", "sqlalchemy"),
    ("pandas.pydata.org", "", "pypi", "pandas"),
    ("numpy.org", "/doc", "pypi", "numpy"),
    ("scikit-learn.org", "", "pypi", "scikit-learn"),
    ("pytorch.org", "/docs", "pypi", "torch"),
    ("docs.pytorch.org", "", "pypi", "torch"),
    ("huggingface.co", "/docs/transformers", "pypi", "transformers"),
    ("huggingface.co", "/docs/diffusers", "pypi", "diffusers"),
    ("python.langchain.com", "", "pypi", "langchain"),
    ("docs.llamaindex.ai", "", "pypi", "llama-index"),
    ("docs.ray.io", "", "pypi", "ray"),
    ("react.dev", "", "npm", "react"),
    ("nextjs.org", "/docs", "npm", "next"),
    ("vuejs.org", "", "npm", "vue"),
    ("svelte.dev", "", "npm", "svelte"),
    ("tailwindcss.com", "", "npm", "tailwindcss"),
    ("vitejs.dev", "", "npm", "vite"),
    ("vite.dev", "", "npm", "vite"),
    ("www.typescriptlang.org", "/docs", "npm", "typescript"),
    ("motion.dev", "", "npm", "motion"),
]
_URL_VER = re.compile(r"/(?:v|version[-/])?(\d+(?:\.\d+){0,2})(?:\.x)?(?:/|$)")
_TEXT_VER = re.compile(r"\b(?:version|v)\s*(\d+\.\d+(?:\.\d+)?)\b", re.I)


def docs_package(url: str) -> tuple[str, str] | None:
    p = urlparse(url)
    host, path = p.netloc.lower(), p.path
    for h, prefix, eco, pkg in DOCS_PACKAGES:
        if host == h or host == f"www.{h}":
            if not prefix or path.startswith(prefix):
                return eco, pkg
    m = re.match(r"([a-z0-9\-]+)\.readthedocs\.io$", host)
    if m:
        return "pypi", m.group(1)
    return None


def docs_version(url: str, text: str = "") -> str | None:
    path = urlparse(url).path
    for seg in re.findall(r"/[^/]+", path):
        if re.fullmatch(r"/(stable|latest|main|master|dev|current)", seg):
            return None  # page tracks the newest release
    m = _URL_VER.search(path)
    if m:
        return m.group(1)
    m = _TEXT_VER.search(text[:3000])
    return m.group(1) if m else None


def latest_package_version(eco: str, pkg: str) -> str | None:
    try:
        if eco == "pypi":
            r = _get(f"{PYPI_API}/{pkg}/json")
            return r.json()["info"]["version"] if r.status_code == 200 else None
        if eco == "npm":
            r = _get(f"{NPM_API}/{pkg}/latest")
            return r.json().get("version") if r.status_code == 200 else None
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None


def docs_meta(url: str, text: str = "") -> dict | None:
    pkg = docs_package(url)
    if not pkg:
        return None
    eco, name = pkg
    ver = docs_version(url, text)
    latest = latest_package_version(eco, name)
    out = {"kind": "docs", "package": name, "ecosystem": eco, "doc_version": ver, "latest_version": latest}
    out["outdated"] = bool(ver and latest and is_major_bump(ver, latest))
    return out


# --------------------------------------------------------------------------- #
# Entry points used by the pipeline
# --------------------------------------------------------------------------- #
def enrich(url: str | None, text: str = "") -> tuple[dict, str, str | None]:
    """Returns (meta, extra_text_for_indexing, error). Never raises."""
    if not url:
        return {}, "", None
    try:
        if slug := github_slug(url):
            m = github_repo(slug)
            extra = "\n\n".join(x for x in [m.get("description", ""), m.pop("readme", "")] if x)
            m["release_baseline"] = github_saved_version(url) or m.get("latest_release")
            return m, extra, None
        if aid := arxiv_id(url):
            m = arxiv_paper(aid)
            try:
                info = s2_citation_info(aid)
                m["citations"] = info.get("citationCount")
                m["influential_citations"] = info.get("influentialCitationCount")
            except (requests.RequestException, ValueError):
                pass
            extra = f"{m['paper_title']}\nAuthors: {', '.join(m['authors'][:12])}\n\n{m['abstract']}"
            return m, extra, None
        if d := docs_meta(url, text):
            return d, "", None
    except Exception as exc:  # noqa: BLE001
        log.warning("Enrichment failed for %s: %s", url, exc)
        return {}, "", f"{exc.__class__.__name__}: {exc}"
    return {}, "", None


def hints_for_model(meta: dict) -> str:
    """Compact metadata string that helps the small model categorise correctly."""
    k = meta.get("kind")
    if k == "repo":
        return (f"GitHub repo {meta.get('full_name')}, {meta.get('language') or 'unknown language'}, "
                f"{meta.get('stars')} stars, topics: {', '.join(meta.get('topics', [])[:6])}")
    if k == "paper":
        return f"arXiv paper {meta.get('arxiv_id')} ({meta.get('primary_category')}) by {', '.join(meta.get('authors', [])[:3])}"
    if k == "docs":
        return f"Documentation for {meta.get('package')} {meta.get('doc_version') or '(latest)'}"
    return ""


def check_item(item: db.Item) -> list[str]:
    """Refresh one item's metadata and raise alerts. Returns new alert messages."""
    if not item.url:
        return []
    new: list[str] = []
    meta = dict(item.meta)
    kind = meta.get("kind")
    try:
        if kind == "repo" and (slug := meta.get("repo") or github_slug(item.url)):
            fresh = github_repo(slug, with_readme=False)
            old_rel, new_rel = meta.get("release_baseline") or meta.get("latest_release"), fresh.get("latest_release")
            if new_rel and new_rel != old_rel:
                major = is_major_bump(old_rel, new_rel)
                msg = (f"{slug} shipped a major release: {new_rel}" + (f" (you saved it at {old_rel})" if old_rel else "")
                       if major else f"{slug} released {new_rel}")
                if db.add_alert(item.id, "major_release" if major else "release", msg,
                                fresh.get("latest_release_url") or item.url, f"rel:{item.id}:{new_rel}"):
                    new.append(msg)
                fresh["release_baseline"] = new_rel
            if fresh.get("archived"):  # add_alert dedupes, so already-true states still alert once
                msg = f"{slug} was archived by its maintainers"
                if db.add_alert(item.id, "archived", msg, item.url, f"archived:{item.id}"):
                    new.append(msg)
            elif fresh.get("stale"):
                msg = f"{slug} has gone quiet: no commits in {fresh.get('days_since_push')} days"
                if db.add_alert(item.id, "stale", msg, item.url, f"stale:{item.id}"):
                    new.append(msg)
            meta.update(fresh)
        elif kind == "paper" and (aid := meta.get("arxiv_id")):
            followups = s2_influential_followups(aid)
            for f in followups:
                msg = f"“{f['title']}” ({f['year']}, {f['citations']} citations) builds on “{item.title}”"
                if db.add_alert(item.id, "followup_paper", msg, f.get("url"), f"cite:{item.id}:{f['paper_id']}"):
                    new.append(msg)
            meta["followups"] = followups
            try:
                info = s2_citation_info(aid)
                meta["citations"] = info.get("citationCount")
            except (requests.RequestException, ValueError):
                pass
        elif kind == "docs":
            fresh = docs_meta(item.url)
            if fresh:
                fresh["doc_version"] = meta.get("doc_version") or fresh.get("doc_version")
                fresh["outdated"] = bool(fresh["doc_version"] and fresh.get("latest_version")
                                         and is_major_bump(fresh["doc_version"], fresh["latest_version"]))
                if fresh["outdated"]:
                    msg = (f"Your {fresh['package']} guide covers v{fresh['doc_version']}, "
                           f"but v{fresh['latest_version']} is out")
                    if db.add_alert(item.id, "outdated_docs", msg, item.url,
                                    f"docs:{item.id}:{fresh['latest_version']}"):
                        new.append(msg)
                meta.update(fresh)
    except Exception as exc:  # noqa: BLE001
        log.warning("Update check failed for item %s: %s", item.id, exc)
        return new
    meta["checked_at"] = db.now_iso()
    db.update_item(item.id, meta=meta)
    return new


def check_all(pause: float = 0.6) -> dict:
    """Refresh every tracked repo / paper / docs item. Polite to rate limits."""
    tracked = [i for i in db.list_items(archived=None) if i.meta.get("kind") in {"repo", "paper", "docs"}]
    alerts: list[str] = []
    for it in tracked:
        alerts += check_item(it)
        time.sleep(pause)
    return {"checked": len(tracked), "new_alerts": alerts}
