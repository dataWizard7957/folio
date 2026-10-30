"""
Local Ollama integration (Gemma 2B by default) with strict JSON extraction.

Jobs:
  * analyze_item()     -> ItemAnalysis   summary, category, tags, next_step
  * answer_question()  -> Answer          RAG answer over retrieved chunks, with citations
  * describe_image()   -> str             screenshot -> text via a local vision model

Every call asks Ollama for schema-constrained JSON, validates it with Pydantic,
and degrades to a deterministic fallback on any failure so nothing crashes.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Literal, Optional

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger("folio.ai")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
VISION_MODEL = os.getenv("FOLIO_VISION_MODEL", "gemma3:4b")  # or "llava"
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))
MAX_PROMPT_CHARS = 6_000  # Gemma 2B has an 8k context; leave room for the reply

CATEGORIES = ("read", "cook", "buy", "explore", "build")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
def _norm_tags(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,;]", v)
    seen, out = set(), []
    for t in v or []:
        t = re.sub(r"[^a-z0-9+#.\- ]", "", str(t).lower()).strip().replace(" ", "-")
        if t and t not in seen:
            seen.add(t)
            out.append(t[:30])
    return out[:6]


class ItemAnalysis(BaseModel):
    summary: str = Field(min_length=1, max_length=700)
    category: Literal["read", "cook", "buy", "explore", "build", "uncategorized"]
    tags: list[str] = Field(default_factory=list)
    next_step: Optional[str] = Field(default=None, max_length=300)

    @field_validator("category", mode="before")
    @classmethod
    def _norm_category(cls, v):
        v = str(v or "").strip().lower()
        return v if v in CATEGORIES else "uncategorized"

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v):
        return _norm_tags(v)

    @field_validator("next_step", mode="before")
    @classmethod
    def _step(cls, v):
        v = (str(v).strip() if v else "") or None
        return v[:300] if v else None


class Answer(BaseModel):
    answer: str
    cited_ids: list[int] = Field(default_factory=list)


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "tags": {"type": "array", "items": {"type": "string"}},
        "next_step": {"type": "string"},
    },
    "required": ["summary", "category", "tags", "next_step"],
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "cited_ids": {"type": "array", "items": {"type": "integer"}}},
    "required": ["answer", "cited_ids"],
}


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
ANALYSIS_SYSTEM = """You are Folio's librarian. You read one saved item and classify it.
Respond with ONLY a JSON object, no prose, no markdown fences, matching exactly:
{"summary": string, "category": one of ["read","cook","buy","explore","build"], "tags": [string], "next_step": string}

Rules:
- summary: exactly two plain sentences describing what the item is and why it is useful.
- category:
    read    = articles, essays, papers, documentation to study
    cook    = recipes, food, drinks
    buy     = products, tools or services to purchase, shopping lists
    explore = places, travel, events, ideas or topics to look into
    build   = code repositories, tutorials, side-project ideas, things to make
- tags: 2 to 5 short lowercase keywords (e.g. "rag", "pytorch", "sourdough").
- next_step: ONE concrete first action that takes under 30 minutes and is specific to this item
  (e.g. "Clone the repo and run the quickstart example", "Read the abstract and results section")."""

ANSWER_SYSTEM = """You answer questions using ONLY the reader's saved library excerpts below.
Each excerpt starts with [id]. Cite the items you use inline like [12].
If the excerpts don't contain the answer, say so plainly and suggest what to search for.
Respond with ONLY JSON: {"answer": string, "cited_ids": [int]}.
Keep the answer under 180 words."""

VISION_PROMPT = """This is a screenshot or image the user saved. Transcribe any visible text
(code, titles, URLs, captions) faithfully, then add one line starting with "Description:"
that says what the image shows. Plain text only."""


# --------------------------------------------------------------------------- #
# Low-level Ollama call + JSON extraction
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply, tolerating fences/prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found in model output")


def chat_json(system: str, user: str, schema: dict, temperature: float = 0.2,
              model: str | None = None) -> dict:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model or OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            # Ollama >= 0.5 enforces this JSON schema during decoding.
            "format": schema,
            "options": {"temperature": temperature, "num_ctx": 8192},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return _extract_json(resp.json().get("message", {}).get("content", ""))


def ollama_status() -> dict:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        def has(name: str) -> bool:
            # "gemma2:2b" must match exactly; a bare "nomic-embed-text" matches any tag of it.
            return any(m == name or m.split(":")[0] == name for m in models)

        from embeddings import EMBED_MODEL  # local import avoids a cycle at module load

        return {"online": True, "model": OLLAMA_MODEL, "model_installed": has(OLLAMA_MODEL),
                "embed_model": EMBED_MODEL, "embed_installed": has(EMBED_MODEL),
                "vision_model": VISION_MODEL, "vision_installed": has(VISION_MODEL)}
    except Exception:
        return {"online": False, "model": OLLAMA_MODEL, "model_installed": False,
                "embed_installed": False, "vision_installed": False}


# --------------------------------------------------------------------------- #
# Item analysis
# --------------------------------------------------------------------------- #
def _first_sentences(text: str, n: int = 2) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", flat)
    out = " ".join(parts[:n]).strip()
    return (out[:400] + "…") if len(out) > 400 else out


def fallback_analysis(title: str, text: str) -> ItemAnalysis:
    summary = _first_sentences(text) or title or "Saved item."
    return ItemAnalysis(summary=summary, category="uncategorized", tags=[])


def analyze_item(title: str, text: str, content_type: str = "article", hints: str = "",
                 model: str | None = None) -> tuple[ItemAnalysis, str | None]:
    """Returns (analysis, error). Never raises."""
    body = (text or "")[:MAX_PROMPT_CHARS]
    prompt = (f"TYPE: {content_type}\nTITLE: {title}\n"
              + (f"METADATA: {hints}\n" if hints else "")
              + f"\nCONTENT:\n{body or '(no body text; infer from title)'}")
    err = None
    for attempt in range(2):
        try:
            analysis = ItemAnalysis.model_validate(chat_json(ANALYSIS_SYSTEM, prompt, ANALYSIS_SCHEMA, model=model))
            return analysis, None
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            log.warning("Ollama returned invalid JSON (attempt %s): %s", attempt + 1, exc)
            err = f"invalid model output: {exc}"
        except requests.RequestException as exc:
            log.warning("Ollama unreachable: %s", exc)
            err = f"ollama unavailable: {exc.__class__.__name__}"
            break  # no point retrying a dead server
    return fallback_analysis(title, text), err


# --------------------------------------------------------------------------- #
# Q&A over the library
# --------------------------------------------------------------------------- #
def answer_question(question: str, contexts: list[tuple[int, str, str]]) -> tuple[Answer, str | None]:
    """contexts: [(item_id, title, excerpt)]. Returns (answer, error). Never raises."""
    if not contexts:
        return Answer(answer="Nothing in your Folio matches that yet. Try different words, or save a source first."), None
    blocks, budget = [], MAX_PROMPT_CHARS
    for iid, title, text in contexts:
        block = f"[{iid}] {title}\n{text.strip()}"
        if len(block) > budget:
            block = block[:budget]
        blocks.append(block)
        budget -= len(block)
        if budget <= 200:
            break
    prompt = "LIBRARY EXCERPTS:\n\n" + "\n\n---\n\n".join(blocks) + f"\n\nQUESTION: {question}"
    valid = {c[0] for c in contexts}
    try:
        ans = Answer.model_validate(chat_json(ANSWER_SYSTEM, prompt, ANSWER_SCHEMA, temperature=0.2))
        inline = {int(x) for x in re.findall(r"\[(\d+)\]", ans.answer)}
        ans.cited_ids = [i for i in dict.fromkeys([*ans.cited_ids, *inline]) if i in valid]
        # Drop hallucinated citations from the prose too.
        ans.answer = re.sub(r"\s*\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid else "", ans.answer).strip()
        return ans, None
    except Exception as exc:  # noqa: BLE001
        log.warning("Q&A failed, returning sources only: %s", exc)
        titles = "; ".join(f"[{c[0]}] {c[1]}" for c in contexts[:5])
        return Answer(answer=f"The local model is unavailable, but these saved items look most relevant: {titles}.",
                      cited_ids=[c[0] for c in contexts[:5]]), f"{exc.__class__.__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Vision: screenshots -> text
# --------------------------------------------------------------------------- #
def describe_image(image_bytes: bytes) -> tuple[str, str | None]:
    """Returns (text, error). Never raises."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": VISION_MODEL, "stream": False, "options": {"temperature": 0.1},
                  "messages": [{"role": "user", "content": VISION_PROMPT,
                                "images": [base64.b64encode(image_bytes).decode()]}]},
            timeout=max(OLLAMA_TIMEOUT, 180),
        )
        resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "").strip()
        return (text, None) if text else ("", "vision model returned no text")
    except Exception as exc:  # noqa: BLE001
        log.warning("Vision model failed: %s", exc)
        return "", f"{exc.__class__.__name__}: {exc}"
