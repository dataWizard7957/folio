# Folio

**A private research memory for developers.**

Papers sit in open tabs, starred repos get forgotten, and screenshots and notes end up scattered across apps. Folio keeps them on one local shelf. It understands developer content, finds items by meaning and tells you what has changed about what you saved.

Folio runs on your machine using FastAPI, SQLite and local Ollama models. Your content is never sent to a hosted AI service. 

## Features

| Feature | Description | Code |
| --- | --- | --- |
| **Semantic search** | Hybrid cosine and BM25 search, fused with Reciprocal Rank Fusion. Vectors are stored in SQLite and indexed with `sqlite-vec` when installed, otherwise with NumPy. | `embeddings.py` |
| **Universal ingestion** | Accepts URLs, notes, PDFs, screenshots, scanned PDFs, dropped files, pasted images and watched folders. | `files.py`, `watcher.py` |
| **Developer-aware metadata** | Repos get stars, language, latest release and README. Papers get abstract, authors, citations and code links. Docs pages have their version checked against PyPI or npm. | `enrich.py` |
| **Update alerts** | Flags major releases, stale or archived repos, highly cited follow-up papers and outdated docs. Checks run when an item is saved and on a schedule. | `enrich.py` |
| **Ask your library** | Answers questions from your own items with `[id]` citations. Citations to items that don't exist are removed. | `pipeline.py` |
| **Browser extension** | One-click save, context menus for pages, links, selections and images, and a keyboard shortcut. | `extension/` |
| **Follow-through tools** | A concrete first step for each item, a saved-vs-read chart, project cards, and auto-archiving after 60 untouched days unless kept. | `database.py`, `frontend/` |

## Requirements

- Python 3.12 (the version this was last run on)
- Node.js 22 (the version this was last run on)
- Ollama with the following models:

| Purpose | Default model | Install |
| --- | --- | --- |
| Summaries, categories and answers | `gemma2:2b` | `ollama pull gemma2:2b` |
| Search embeddings | `nomic-embed-text` | `ollama pull nomic-embed-text` |
| Screenshots and scanned PDFs | `gemma3:4b` or `llava` | `ollama pull gemma3:4b` |

If a model is missing, Folio degrades instead of failing: ingestion still completes and search falls back to keywords.

## Quick start

**1. Pull the models**

```bash
ollama pull gemma2:2b
ollama pull nomic-embed-text
ollama pull gemma3:4b
```

**2. Start the backend**

macOS and Linux:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --reload --port 8000
```

The first start can take around 30 seconds while Python libraries load. API docs are at <http://localhost:8000/docs>.

**3. Start the frontend** in a second terminal

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

**Keyboard shortcuts:** press `n` to save and `/` or `⌘K` to search. You can drop files anywhere on the page.

## Usage

### Watch folders

```bash
FOLIO_WATCH_DIRS="$HOME/Desktop:$HOME/Downloads:$HOME/Pictures/Screenshots" uvicorn main:app --port 8000
```

New PDFs, images and text files are ingested as they appear. Partial downloads (`.crdownload`, `.part`) are ignored and duplicates are detected by SHA-256. Set `FOLIO_WATCH_BACKFILL=1` to also import existing files. On Windows, separate paths with `;`.

### Browser extension

Supports Chrome, Edge and Firefox 121+.

1. Load the extension:
   - **Chrome or Edge:** open `chrome://extensions`, turn on Developer mode, choose **Load unpacked** and select `extension/`.
   - **Firefox:** open `about:debugging`, choose **Load Temporary Add-on** and select `extension/manifest.json`.
2. Click the toolbar icon to save the current tab with a note. Highlighted text is attached automatically.
3. Right-click to save a page, link, selection or image. Cross-origin images that can't be fetched are saved as links.
4. Press **Alt+Shift+S** to save instantly. The badge shows `✓` for saved, `=` for already saved and `!` for an error.

If the backend isn't at `localhost:8000`, set its URL in the extension's **Settings**.

### Update alerts

Folio compares each saved item with its current state:

- **Repos:** a link to a specific release, such as `/releases/tag/2.0.0`, records that version as the one you saved. Links to the repo itself use the latest release at save time.
- **Docs:** versioned pages, such as `/1.10/`, are compared with the latest PyPI or npm release.
- **Papers:** citing papers with at least `FOLIO_INFLUENTIAL_CITATIONS` citations are reported as follow-ups. Semantic Scholar's API returns at most 10,000 citations per paper, so follow-ups to very heavily cited papers may be missed.

## Architecture

```
folio/
├── backend/
│   ├── main.py          FastAPI routes and lifespan (watcher, maintenance loop)
│   ├── pipeline.py      Ingest, extract, enrich, analyse, embed; Q&A; maintenance
│   ├── database.py      SQLite schema, in-place migrations, Pydantic models, alerts, stats
│   ├── scraper.py       Page fetching and boilerplate removal
│   ├── ai_service.py    Ollama chat with JSON-schema output, validation, fallbacks, vision
│   ├── embeddings.py    Chunking, embeddings, sqlite-vec / NumPy, FTS5, hybrid search
│   ├── enrich.py        GitHub, arXiv, Semantic Scholar, Hugging Face, PyPI, npm
│   ├── files.py         PDF and image extraction, content-addressed file store
│   └── watcher.py       Folder watching (watchdog, with polling fallback)
├── frontend/            React, Tailwind and Framer Motion UI
└── extension/           Manifest V3 browser extension
```

```
URL / note / PDF / screenshot / extension / watched folder
       │
       ▼  POST /api/ingest · /api/ingest/file      (returns quickly, status=pending)
┌─ Background worker (FOLIO_AI_CONCURRENCY items at a time) ─────────────────┐
│ 1 extract   pypdf · vision model · arXiv id detection in PDFs              │
│ 2 enrich    repo metadata · paper metadata and citations · docs version    │
│ 3 analyse   gemma2:2b → summary, category, tags, next step                 │
│ 4 embed     chunks → nomic-embed-text → SQLite                             │
│ 5 check     raise alerts for saves that are already out of date            │
└────────────────────────────────────────────────────────────────────────────┘
       │
       ├─ /api/search   cosine + FTS5 BM25 → Reciprocal Rank Fusion
       ├─ /api/ask      top chunks → grounded answer with [id] citations
       └─ hourly        auto-archive · re-embed missing · update checks → alerts
```

### Design principles

- **The LLM doesn't decide structure.** Similarity scores come from embeddings, and unknown item ids are dropped from answers, so the model can't invent references.
- **Built for small models.** Replies are constrained by a JSON schema and validated with Pydantic. Repo, paper and docs metadata is passed as hints to improve categorisation.
- **Upgrades in place.** Missing columns are added with `ALTER TABLE`, so existing databases keep working.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Installed models, index stats and watcher status |
| `POST` | `/api/ingest` | Save `{url?, text?, title?}`. Returns `201`, or `200` with `X-Folio-Duplicate` if the URL is already saved |
| `POST` | `/api/ingest/file` | Upload multipart `uploads` (PDF, images, md, txt, html) |
| `GET` | `/api/items?category=&archived=false\|true\|all&type=` | List items |
| `PATCH` | `/api/items/{id}` | Update `{is_read, featured, kept, archived, category, next_step}` |
| `DELETE` | `/api/items/{id}` | Remove an item with its chunks, vectors, FTS rows and stored file |
| `POST` | `/api/items/{id}/reprocess` | Re-run the pipeline |
| `GET` | `/api/items/{id}/similar` | Nearest neighbours |
| `GET` | `/api/items/{id}/file` | Original file |
| `GET` | `/api/search?q=&mode=hybrid\|semantic\|keyword` | Search |
| `POST` | `/api/ask` | Answer `{question}` with cited ids and sources |
| `GET` | `/api/alerts` | List update alerts |
| `POST` | `/api/alerts/seen` | Mark alerts as seen |
| `POST` | `/api/alerts/refresh` | Queue an update check |
| `GET` | `/api/stats` | Saved vs read per week |
| `GET` | `/api/projects` | Build items with a first step |
| `POST` | `/api/maintenance` | Archive and re-embed now |
| `POST` | `/api/reindex` | Embed anything missing |

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `gemma2:2b` | Text model |
| `FOLIO_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `FOLIO_VISION_MODEL` | `gemma3:4b` | Vision model |
| `FOLIO_DB_PATH` | `backend/folio.db` | Database location |
| `FOLIO_FILES_DIR` | `backend/files/` | Stored file location |
| `FOLIO_WATCH_DIRS` | unset | Folders to watch, separated by `:` (`;` on Windows) |
| `FOLIO_WATCH_BACKFILL` | `0` | Set to `1` to import existing files |
| `FOLIO_ARCHIVE_AFTER_DAYS` | `60` | Days before untouched, unread, un-kept items are archived |
| `FOLIO_REFRESH_HOURS` | `24` | How often repos, papers and docs are re-checked |
| `FOLIO_STALE_DAYS` | `365` | Days without commits before a repo counts as stale |
| `FOLIO_INFLUENTIAL_CITATIONS` | `50` | Citations needed for a follow-up paper alert |
| `FOLIO_AI_CONCURRENCY` | `1` | Items processed by the models at once |
| `GITHUB_TOKEN` | unset | Raises GitHub's limit from 60 to 5,000 requests per hour |
| `S2_API_KEY` | unset | Semantic Scholar key. Without one, the shared pool is often rate-limited, which can delay follow-up alerts |
| `FOLIO_CORS` | `http://localhost:5173` | Allowed origins. Browser-extension origins are always allowed |

## Privacy and network use

Models run locally through Ollama. Folio makes network calls only to fetch the pages you save and to enrich them through public APIs: GitHub, arXiv, Semantic Scholar, Hugging Face, PyPI and npm. These requests identify the repo, paper or package being looked up. Your notes, files and library contents are not uploaded.
