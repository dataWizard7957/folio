import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api, CATEGORIES } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import BentoGrid from "./components/BentoGrid.jsx";
import IngestModal from "./components/IngestModal.jsx";
import SearchBar from "./components/SearchBar.jsx";
import AlertsPanel from "./components/AlertsPanel.jsx";
import { PlusIcon, SparkIcon, UploadIcon } from "./components/Icons.jsx";

const POLL_MS = 2000;

export default function App() {
  const [items, setItems] = useState([]);
  const [archived, setArchived] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [category, setCategory] = useState("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState(null);
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [toast, setToast] = useState("");
  const [backendDown, setBackendDown] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // search / ask
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("search");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null); // {hits, items, retrieval}
  const [answer, setAnswer] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [live, arch] = await Promise.all([api.listItems("false"), api.listItems("true")]);
      setItems(live);
      setArchived(arch);
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  const refreshSide = useCallback(() => {
    api.stats().then(setStats).catch(() => {});
    api.alerts().then(setAlerts).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    refreshSide();
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [refresh, refreshSide]);

  // Poll only while something is still being curated in the background.
  const anyProcessing = items.some((i) => i.status === "pending" || i.status === "processing");
  useEffect(() => {
    if (!anyProcessing) {
      refreshSide();
      return;
    }
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [anyProcessing, refresh, refreshSide]);

  // "n" opens the ingest modal; files dropped anywhere open it pre-filled.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
        e.preventDefault();
        setDroppedFiles(null);
        setIngestOpen(true);
      }
    };
    const onDragOver = (e) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        e.preventDefault();
        setDragOver(true);
      }
    };
    const onDrop = (e) => {
      if (!e.dataTransfer?.files?.length) return;
      e.preventDefault();
      setDragOver(false);
      setDroppedFiles(Array.from(e.dataTransfer.files));
      setIngestOpen(true);
    };
    const onLeave = (e) => e.relatedTarget === null && setDragOver(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragleave", onLeave);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragleave", onLeave);
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  // ---- derived ----
  const showingArchive = category === "archived";
  const all = useMemo(() => [...items, ...archived], [items, archived]);
  const byId = useMemo(() => Object.fromEntries(all.map((i) => [i.id, i])), [all]);

  const visible = useMemo(() => {
    if (results) return results.order.map((id) => byId[id] ?? results.items[id]).filter(Boolean);
    if (answer) {
      const cited = new Set(answer.cited_ids);
      return [...answer.sources].sort((a, b) => cited.has(b.id) - cited.has(a.id)).map((s) => byId[s.id]).filter(Boolean);
    }
    const pool = showingArchive ? archived : items;
    return pool.filter((i) => (showingArchive || category === "all" || i.category === category) && (!unreadOnly || !i.is_read));
  }, [results, answer, byId, items, archived, category, unreadOnly, showingArchive]);

  const counts = useMemo(() => {
    const c = { all: items.length, archived: archived.length };
    for (const i of items) c[i.category] = (c[i.category] ?? 0) + 1;
    return c;
  }, [items, archived]);

  // ---- search / ask ----
  function clearSearch() {
    setQuery("");
    setResults(null);
    setAnswer(null);
  }

  async function runSearch() {
    setSearching(true);
    setAnswer(null);
    setResults(null);
    try {
      if (mode === "ask") {
        setAnswer(await api.ask(query));
      } else {
        const res = await api.search(query);
        setResults({
          order: res.results.map((r) => r.item.id),
          items: Object.fromEntries(res.results.map((r) => [r.item.id, r.item])),
          hits: Object.fromEntries(res.results.map((r) => [r.item.id, r])),
          retrieval: res.retrieval,
        });
      }
    } catch (e) {
      setToast(e.message);
    } finally {
      setSearching(false);
    }
  }

  // ---- mutations (optimistic) ----
  const patchLocal = (id, patch) => {
    const apply = (xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x));
    setItems(apply);
    setArchived(apply);
    setResults((r) => (r && r.items[id] ? { ...r, items: { ...r.items, [id]: { ...r.items[id], ...patch } } } : r));
  };

  async function patch(item, change, failMsg = "Couldn't update that item.") {
    const before = Object.fromEntries(Object.keys(change).map((k) => [k, item[k]]));
    patchLocal(item.id, change);
    try {
      await api.updateItem(item.id, change);
      return true;
    } catch {
      patchLocal(item.id, before);
      setToast(failMsg);
      return false;
    }
  }

  const actions = {
    toggleRead: (item) => patch(item, { is_read: !item.is_read }),
    toggleFeatured: (item) => patch(item, { featured: !item.featured }),
    toggleKept: async (item) => {
      if (await patch(item, { kept: !item.kept })) setToast(item.kept ? "No longer kept." : "Kept — Folio won't auto-archive this.");
    },
    archive: async (item) => {
      if (await patch(item, { archived: !item.archived })) {
        setToast(item.archived ? "Restored to your shelves." : "Let go. It's in the Archive if you change your mind.");
        refresh();
      }
    },
    remove: async (item) => {
      setItems((xs) => xs.filter((x) => x.id !== item.id));
      setArchived((xs) => xs.filter((x) => x.id !== item.id));
      try {
        await api.deleteItem(item.id);
        setToast("Removed from your Folio.");
      } catch {
        refresh();
        setToast("Couldn't delete that item.");
      }
    },
    reprocess: async (item) => {
      patchLocal(item.id, { status: "pending" });
      await api.reprocess(item.id).catch(() => null);
      refresh();
    },
  };

  async function handleIngest(body) {
    const item = await api.ingest(body);
    setItems((xs) => (xs.some((x) => x.id === item.id) ? xs : [item, ...xs]));
    clearSearch();
    setCategory("all");
    setToast(item.status === "done" ? "Already in your Folio." : "Saved — your local model is curating it.");
  }

  async function handleUpload(fileList) {
    const created = await api.uploadFiles(fileList);
    setItems((xs) => [...created.filter((c) => !xs.some((x) => x.id === c.id)), ...xs]);
    clearSearch();
    setCategory("all");
    setToast(`${created.length} file${created.length > 1 ? "s" : ""} saved — reading them now.`);
  }
  function openItem(item) {
    if (item.url) {
      window.open(item.url, "_blank", "noreferrer");
      return;
    }
    clearSearch();
    setCategory(byId[item.id]?.archived ? "archived" : "all");
    setUnreadOnly(false);
    setTimeout(() => document.getElementById(`item-${item.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 350);
  }

  const activeLabel = results
    ? `“${query}”`
    : answer
      ? "Ask your library"
      : showingArchive
        ? "Archive"
        : CATEGORIES.find((c) => c.id === category)?.label ?? "Everything";
  const unread = items.filter((i) => !i.is_read).length;

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <Sidebar
        active={category}
        onSelect={(c) => {
          clearSearch();
          setCategory(c);
        }}
        counts={counts}
        onIngest={() => {
          setDroppedFiles(null);
          setIngestOpen(true);
        }}
        ollama={health?.ollama}
        stats={stats}
        unreadOnly={unreadOnly}
        onToggleUnread={() => setUnreadOnly((v) => !v)}
      />

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-24 pt-6 md:px-8 lg:px-12 lg:pt-10">
        <div className="mb-8 flex items-center gap-3">
          <SearchBar value={query} onChange={setQuery} mode={mode} onModeChange={setMode} onSubmit={runSearch} onClear={clearSearch} busy={searching} />
          <AlertsPanel alerts={alerts} onChanged={refreshSide} />
        </div>

        <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-slate-800/70 pb-6">
          <div className="min-w-0">
            <p className="kicker">
              {results
                ? `${visible.length} results · ${results.retrieval.semantic ? "semantic + keyword" : "keyword only (embedding model offline)"}`
                : showingArchive
                  ? `auto-archived after ${stats?.archive_after_days ?? 60} days untouched · restore anything`
                  : new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
            </p>
            <AnimatePresence mode="wait" initial={false}>
              <motion.h2
                key={activeLabel}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="mt-1 truncate pb-1 text-3xl font-medium leading-tight md:text-4xl"
              >
                {activeLabel}
              </motion.h2>
            </AnimatePresence>
          </div>
          {!results && !answer && (
            <p className="font-serif italic text-ivory-400">
              {visible.length} {visible.length === 1 ? "piece" : "pieces"} · {unread} unread overall
            </p>
          )}
        </header>

        {backendDown && (
          <div className="mb-6 rounded-xl border border-cat-cook/30 bg-cat-cook/5 p-4 text-sm text-ivory-200">
            Can't reach the Folio API. Start it with <code className="font-mono text-cat-read">uvicorn main:app --reload</code> in{" "}
            <code className="font-mono">backend/</code>.
          </div>
        )}

        {answer && <AnswerPanel answer={answer} byId={byId} onOpen={openItem} />}

        {loaded && visible.length === 0 ? (
          <EmptyState
            kind={results || answer ? "search" : showingArchive ? "archive" : items.length ? "filtered" : "empty"}
            onIngest={() => setIngestOpen(true)}
          />
        ) : (
          <BentoGrid items={visible} hits={results?.hits} actions={actions} />
        )}
      </main>

      <IngestModal
        open={ingestOpen}
        onClose={() => setIngestOpen(false)}
        onSubmit={handleIngest}
        onUpload={handleUpload}
        initialFiles={droppedFiles}
      />

      <AnimatePresence>
        {dragOver && !ingestOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="pointer-events-none fixed inset-3 z-50 flex items-center justify-center rounded-3xl border-2 border-dashed border-cat-read/50 bg-slate-950/80"
          >
            <p className="flex items-center gap-3 font-serif text-2xl text-ivory-100">
              <UploadIcon size={22} /> Drop to save PDFs and screenshots
            </p>
          </motion.div>
        )}
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full border border-slate-800 bg-slate-900 px-4 py-2 text-sm text-ivory-200 shadow-card"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Answer with inline [id] citations rendered as links to the cited items. */
function AnswerPanel({ answer, byId, onOpen }) {
  const parts = answer.answer.split(/(\[\d+\])/g);
  const sourceTitle = Object.fromEntries(answer.sources.map((s) => [s.id, s]));
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-8 rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-card md:p-8"
    >
      <p className="kicker flex items-center gap-1.5">
        <SparkIcon size={12} /> Answered from your library{answer.error ? " · model offline, showing closest sources" : ""}
      </p>
      <p className="mt-2 font-serif text-sm italic text-ivory-400">{answer.question}</p>
      <p className="mt-4 max-w-3xl font-serif text-[18px] leading-relaxed text-ivory-100">
        {parts.map((p, i) => {
          const m = p.match(/^\[(\d+)\]$/);
          if (!m) return <span key={i}>{p}</span>;
          const id = Number(m[1]);
          const it = byId[id] ?? sourceTitle[id];
          return (
            <button
              key={i}
              onClick={() => it && onOpen(it)}
              title={it?.title}
              className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded border border-cat-read/40 bg-cat-read/10 px-1 font-mono text-[11px] text-cat-read hover:bg-cat-read/20"
            >
              {id}
            </button>
          );
        })}
      </p>
      {answer.cited_ids.length > 0 && (
        <ol className="mt-5 space-y-1 border-t border-slate-800 pt-4">
          {answer.cited_ids.map((id) => (
            <li key={id} className="flex gap-2 text-[13px] text-ivory-300">
              <span className="font-mono text-cat-read">[{id}]</span>
              <button onClick={() => onOpen(byId[id] ?? sourceTitle[id])} className="text-left hover:text-ivory-50 hover:underline">
                {(byId[id] ?? sourceTitle[id])?.title}
              </button>
            </li>
          ))}
        </ol>
      )}
    </motion.section>
  );
}

function EmptyState({ kind, onIngest }) {
  const copy = {
    empty: ["An empty Folio", "Every paper, repo, screenshot and half-formed idea, finally in one place. Start with a link."],
    filtered: ["Nothing on this shelf", "Try another shelf, or turn off “Unread only”."],
    archive: ["The archive is empty", "Items you let go, or that sit untouched for 60 days, land here."],
    search: ["Nothing matched", "Try describing it differently. Search understands meaning, not just keywords."],
  }[kind];
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mx-auto mt-16 max-w-md rounded-2xl border border-dashed border-slate-800 px-8 py-14 text-center">
      <h3 className="text-2xl">{copy[0]}</h3>
      <p className="mt-2 font-serif italic text-ivory-400">{copy[1]}</p>
      {kind === "empty" && (
        <button onClick={onIngest} className="btn-primary mt-6">
          <PlusIcon /> Save your first piece
        </button>
      )}
      <p className="mt-4 font-mono text-[11px] text-ivory-500">tip: press “n” to save, “/” to search, or drop files anywhere</p>
    </motion.div>
  );
}
