// Demo mode (VITE_DEMO=true): the real Folio UI over in-browser sample data.
// No backend, no Ollama, nothing leaves the browser. Changes last until reload.
// Search, answers and summaries here are pre-written to show what the local
// models produce in the real app.

const DAY = 86_400_000;
const now = Date.now();
const ago = (days) => new Date(now - days * DAY).toISOString();

let nextId = 100;

function item(id, fields) {
  const created = fields.created ?? 10;
  return {
    id,
    url: null,
    source: null,
    content_type: "link",
    summary: null,
    category: "uncategorized",
    tags: [],
    status: "done",
    is_read: false,
    featured: false,
    kept: false,
    archived: false,
    next_step: null,
    meta: {},
    file_name: null,
    error: null,
    created_at: ago(created),
    updated_at: ago(Math.max(0, created - 1)),
    read_at: fields.is_read ? ago(Math.max(0, created - 2)) : null,
    archived_at: fields.archived ? ago(2) : null,
    last_touched_at: ago(Math.max(0, created - 1)),
    ...fields,
  };
}

let items = [
  item(1, {
    title: "vercel/next.js",
    url: "https://github.com/vercel/next.js",
    source: "github.com",
    content_type: "repo",
    category: "build",
    tags: ["react", "framework", "ssr"],
    featured: true,
    summary: "The React framework for full-stack web apps: routing, server rendering and bundling in one package. You saved it for the side project's marketing site.",
    next_step: "Read the upgrade guide before moving the site to the new major version.",
    meta: { kind: "repo", stars: 128000, language: "JavaScript", latest_release: "v15.0.0", license: "MIT" },
    created: 41,
  }),
  item(2, {
    title: "Attention Is All You Need",
    url: "https://arxiv.org/abs/1706.03762",
    source: "arxiv.org",
    content_type: "paper",
    category: "read",
    tags: ["transformers", "nlp", "attention"],
    is_read: true,
    kept: true,
    summary: "Introduces the Transformer, which drops recurrence and relies only on attention. It trains faster than RNN models and set new translation results.",
    meta: { kind: "paper", authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"], arxiv_id: "1706.03762", citations: 140000, code_links: ["https://github.com/tensorflow/tensor2tensor"] },
    created: 52,
  }),
  item(3, {
    title: "Pydantic documentation: Models",
    url: "https://docs.pydantic.dev/1.10/usage/models/",
    source: "docs.pydantic.dev",
    content_type: "docs",
    category: "build",
    tags: ["python", "validation"],
    summary: "How to define models, validate data and customise fields. These pages are for v1; the current major version changed the validator and config APIs.",
    next_step: "Switch the bookmark to the v2 docs.",
    meta: { kind: "docs", package: "pydantic", doc_version: "1.10", latest_version: "2.9", outdated: true },
    created: 33,
  }),
  item(4, {
    title: "tiangolo/full-stack-fastapi-template",
    url: "https://github.com/fastapi/full-stack-fastapi-template",
    source: "github.com",
    content_type: "repo",
    category: "explore",
    tags: ["fastapi", "template", "postgres"],
    summary: "A starter with FastAPI, React, Postgres and Docker Compose. Good reference for project layout and auth.",
    meta: { kind: "repo", stars: 27000, language: "TypeScript", latest_release: "0.7.1", license: "MIT" },
    created: 19,
  }),
  item(5, {
    title: "old-org/markdown-preview-kit",
    url: "https://example.com/markdown-preview-kit",
    source: "example.com",
    content_type: "repo",
    category: "explore",
    tags: ["markdown", "editor"],
    summary: "A small markdown preview component. Folio flagged it: no commits for over a year and the repo is now archived.",
    meta: { kind: "repo", stars: 840, language: "TypeScript", stale: true, archived: true, days_since_push: 412 },
    created: 88,
  }),
  item(6, {
    title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    url: "https://arxiv.org/abs/2005.11401",
    source: "arxiv.org",
    content_type: "paper",
    category: "read",
    tags: ["rag", "retrieval", "llm"],
    summary: "Combines a retriever with a generator so answers are grounded in fetched documents. The basis for 'ask your library' features like Folio's.",
    meta: { kind: "paper", authors: ["Patrick Lewis", "Ethan Perez", "Aleksandra Piktus"], arxiv_id: "2005.11401", citations: 6200, code_links: ["https://github.com/huggingface/transformers"] },
    created: 12,
  }),
  item(7, {
    title: "Local embeddings with nomic-embed-text",
    content_type: "note",
    category: "build",
    tags: ["embeddings", "ollama", "notes"],
    is_read: true,
    summary: "Your note: nomic-embed-text runs fine on CPU, needs 'search_document:' / 'search_query:' prefixes, and 768-dim vectors are plenty for a personal library.",
    created: 9,
  }),
  item(8, {
    title: "SQLite as an application file format",
    url: "https://www.sqlite.org/appfileformat.html",
    source: "sqlite.org",
    content_type: "article",
    category: "read",
    tags: ["sqlite", "databases"],
    summary: "Argues that a single SQLite file beats a folder of custom files for app data: atomic writes, easy queries and one file to back up.",
    created: 6,
  }),
  item(9, {
    title: "Weeknight dal tadka",
    url: "https://example.com/recipes/dal-tadka",
    source: "example.com",
    content_type: "article",
    category: "cook",
    tags: ["recipe", "lentils", "quick"],
    summary: "Yellow lentils simmered with turmeric, finished with a ghee tempering of cumin, garlic and chilli. About 30 minutes.",
    next_step: "Buy toor dal and fresh curry leaves.",
    created: 4,
  }),
  item(10, {
    title: "Mechanical keyboard shortlist",
    content_type: "screenshot",
    category: "buy",
    tags: ["keyboard", "shopping"],
    file_name: "keyboard-shortlist.png",
    summary: "Screenshot read by the vision model: three 75% boards compared on switches, hot-swap support and price. The cheapest hot-swap option is the second one.",
    created: 3,
  }),
  item(11, {
    title: "Designing Data-Intensive Applications, ch. 3 notes",
    content_type: "pdf",
    category: "read",
    tags: ["databases", "storage", "book"],
    file_name: "ddia-ch3.pdf",
    summary: "Storage engines: log-structured merge trees versus B-trees, and why write amplification matters for SSDs.",
    meta: { kind: "pdf", pages: 42, author: "Martin Kleppmann" },
    created: 2,
  }),
  item(12, {
    title: "react-hook-form docs: useForm",
    url: "https://react-hook-form.com/docs/useform",
    source: "react-hook-form.com",
    content_type: "docs",
    category: "build",
    tags: ["react", "forms"],
    summary: "Reference for useForm options: validation modes, default values and resolver integration.",
    meta: { kind: "docs", package: "react-hook-form", latest_version: "7.53", outdated: false },
    created: 1,
  }),
  item(13, {
    title: "Old conference schedule",
    url: "https://example.com/conf-2024",
    source: "example.com",
    content_type: "link",
    category: "explore",
    tags: ["events"],
    archived: true,
    summary: "Talk schedule from last year's conference. Archived automatically after it went untouched.",
    created: 120,
  }),
];

let alerts = [
  { id: 1, item_id: 1, kind: "major_release", message: "vercel/next.js released v15.0.0, a new major version since you saved it.", url: "https://github.com/vercel/next.js/releases", seen: false, created_at: ago(1), item_title: "vercel/next.js" },
  { id: 2, item_id: 6, kind: "followup_paper", message: "An influential follow-up cites a paper you saved: 'Self-RAG: Learning to Retrieve, Generate, and Critique'.", url: "https://arxiv.org/abs/2310.11511", seen: false, created_at: ago(2), item_title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" },
  { id: 3, item_id: 3, kind: "outdated_docs", message: "You saved pydantic v1.10 docs, but v2.9 is current.", url: "https://docs.pydantic.dev/latest/", seen: false, created_at: ago(3), item_title: "Pydantic documentation: Models" },
  { id: 4, item_id: 5, kind: "stale", message: "old-org/markdown-preview-kit was archived and has had no commits in 412 days.", url: null, seen: true, created_at: ago(6), item_title: "old-org/markdown-preview-kit" },
];

const ANSWERS = [
  {
    match: /rag|retriev|ground|ask/i,
    answer: "Retrieval-augmented generation pairs a retriever with a language model so answers are grounded in documents it fetched [6]. Folio does the same over your own library: your note says nomic-embed-text works well on CPU for the embeddings [7], and storing everything in one SQLite file keeps it simple to back up [8].",
    cited: [6, 7, 8],
  },
  {
    match: /transformer|attention/i,
    answer: "The Transformer replaces recurrence with attention alone, which makes training more parallel and faster [2]. Retrieval-augmented models build on Transformer generators and add a document retriever [6].",
    cited: [2, 6],
  },
  {
    match: /upgrade|outdated|version|pydantic|next/i,
    answer: "Two saved sources are behind: your Pydantic bookmark points at v1.10 docs while v2.9 is current [3], and Next.js shipped a new major release since you saved it [1]. Both have a next step attached.",
    cited: [3, 1],
  },
  {
    match: /sqlite|database|storage/i,
    answer: "SQLite works well as an application file format: atomic writes, easy queries and a single file to back up [8]. Your DDIA notes compare the storage engines underneath, LSM trees versus B-trees [11].",
    cited: [8, 11],
  },
  {
    match: /cook|dinner|recipe|eat/i,
    answer: "You saved a 30-minute dal tadka, finished with a cumin, garlic and chilli tempering [9]. Its next step is to buy toor dal and curry leaves.",
    cited: [9],
  },
];

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const live = () => items.filter((i) => !i.archived);

function words(text) {
  return (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 2);
}

function rank(query, limit) {
  const terms = words(query);
  const scored = items
    .map((it) => {
      const hay = [it.title, it.summary, it.tags.join(" "), it.source, it.meta?.package].filter(Boolean).join(" ").toLowerCase();
      const matched = terms.filter((t) => hay.includes(t));
      return { it, matched, score: matched.length / Math.max(terms.length, 1) };
    })
    .filter((s) => s.matched.length > 0)
    .sort((a, b) => b.score - a.score || b.it.created_at.localeCompare(a.it.created_at))
    .slice(0, limit);
  return scored.map(({ it, matched, score }) => ({
    item: it,
    score: Number(score.toFixed(3)),
    similarity: Number((0.55 + score * 0.4).toFixed(3)),
    snippet: it.summary,
    matched,
  }));
}

function weeks() {
  const saved = [3, 5, 2, 6, 4, 7, 3, 5];
  const read = [2, 3, 1, 2, 3, 4, 2, 3];
  const archived = [0, 1, 0, 2, 1, 0, 1, 1];
  return saved.map((s, i) => {
    const start = new Date(now - (7 - i) * 7 * DAY);
    return { week_start: start.toISOString().slice(0, 10), saved: s, read: read[i], archived: archived[i] };
  });
}

function find(id) {
  const it = items.find((i) => i.id === Number(id));
  if (!it) throw new Error("Item not found");
  return it;
}

function newItem(fields) {
  const it = item(nextId++, { status: "processing", created: 0, ...fields });
  items = [it, ...items];
  // Simulate the local pipeline: scrape, summarise, categorise, embed.
  setTimeout(() => {
    Object.assign(it, {
      status: "done",
      category: it.category === "uncategorized" ? "explore" : it.category,
      tags: it.tags.length ? it.tags : ["demo"],
      summary:
        it.summary ??
        "Demo mode: in the real app a local Ollama model reads this, writes a summary, picks a category and tags, and indexes it for search. Nothing was sent anywhere.",
      updated_at: new Date().toISOString(),
    });
  }, 2500);
  return it;
}

export const demoApi = {
  health: async () => ({
    ok: true,
    ollama: {
      online: true,
      model: "gemma2:2b",
      model_installed: true,
      embed_model: "nomic-embed-text",
      embed_installed: true,
      vision_model: "gemma3:4b",
      vision_installed: true,
    },
    index: { items: items.length, vectors: items.length, backend: "sqlite-vec" },
    watcher: { mode: "off", dirs: [] },
  }),
  listItems: async (archived = "false") =>
    (archived === "true" ? items.filter((i) => i.archived) : archived === "false" ? live() : items).map((i) => ({ ...i })),
  ingest: async (body) => {
    await wait(400);
    if (body?.url) {
      let source = null;
      try {
        source = new URL(body.url).hostname;
      } catch {
        throw new Error("That doesn't look like a URL.");
      }
      return newItem({ title: body.title || body.url, url: body.url, source });
    }
    const text = (body?.text || "").trim();
    return newItem({ title: body?.title || text.slice(0, 60) || "Untitled note", content_type: "note" });
  },
  uploadFiles: async (fileList) => {
    await wait(400);
    return [...fileList].map((f) =>
      newItem({
        title: f.name,
        file_name: f.name,
        content_type: /\.pdf$/i.test(f.name) ? "pdf" : /\.(png|jpe?g|webp|gif)$/i.test(f.name) ? "screenshot" : "file",
        summary: "Demo mode: the file stays in your browser. In the real app it is read locally (PDF text, or the vision model for screenshots) and summarised.",
      }),
    );
  },
  updateItem: async (id, patch) => {
    const it = find(id);
    Object.assign(it, patch, { updated_at: new Date().toISOString() });
    if (patch.is_read === true) it.read_at = new Date().toISOString();
    if (patch.archived === true) it.archived_at = new Date().toISOString();
    return { ...it };
  },
  deleteItem: async (id) => {
    items = items.filter((i) => i.id !== Number(id));
    return null;
  },
  reprocess: async (id) => {
    const it = find(id);
    it.status = "processing";
    setTimeout(() => (it.status = "done"), 2000);
    return { ...it };
  },
  similar: async (id) => {
    const it = find(id);
    return rank(`${it.tags.join(" ")} ${it.title}`, 5)
      .filter((h) => h.item.id !== it.id)
      .slice(0, 4)
      .map((h) => ({ item: h.item, similarity: h.similarity }));
  },
  fileUrl: () => "#",
  search: async (q) => {
    await wait(350);
    return { query: q, retrieval: { semantic: true, keyword: true, demo: true }, results: rank(q, 24) };
  },
  ask: async (question) => {
    await wait(900);
    const canned = ANSWERS.find((a) => a.match.test(question));
    const hits = rank(question, 6);
    const cited = canned ? canned.cited : hits.slice(0, 2).map((h) => h.item.id);
    const pool = new Map(hits.map((h) => [h.item.id, h]));
    for (const id of cited) if (!pool.has(id)) pool.set(id, { item: find(id), snippet: find(id).summary });
    const sources = [...pool.values()].map((h) => ({
      id: h.item.id,
      title: h.item.title,
      url: h.item.url,
      category: h.item.category,
      snippet: h.snippet,
      cited: cited.includes(h.item.id),
    }));
    const answer = canned
      ? canned.answer
      : sources.length
        ? `In the real app a local model writes an answer from these saved items and cites them, like this [${cited.join("] [")}]. This demo has pre-written answers for questions about RAG, transformers, outdated docs, SQLite or dinner.`
        : "Nothing in your Folio matches that yet. Try asking about RAG, transformers, outdated docs, SQLite or dinner.";
    return { question, answer, cited_ids: cited, sources, retrieval: { semantic: true, demo: true }, error: null };
  },
  stats: async () => {
    const series = weeks();
    const saved = series.reduce((n, w) => n + w.saved, 0);
    const read = series.reduce((n, w) => n + w.read, 0);
    return {
      weeks: series,
      this_week: series[series.length - 1],
      read_ratio: Number((read / saved).toFixed(3)),
      unread: live().filter((i) => !i.is_read).length,
      kept: items.filter((i) => i.kept).length,
      archived: items.filter((i) => i.archived).length,
      archive_after_days: 60,
    };
  },
  alerts: async () => alerts,
  markAlertsSeen: async (ids) => {
    alerts = alerts.map((a) => (!ids || ids.includes(a.id) ? { ...a, seen: true } : a));
    return null;
  },
  refreshAlerts: async () => ({ queued: true }),
};
