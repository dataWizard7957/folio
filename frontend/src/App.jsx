import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api, CATEGORIES } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import BentoGrid from "./components/BentoGrid.jsx";
import IngestModal from "./components/IngestModal.jsx";
import SearchBar from "./components/SearchBar.jsx";
import AlertsPanel from "./components/AlertsPanel.jsx";
import AnswerPanel from "./components/AnswerPanel.jsx";
import EmptyState from "./components/EmptyState.jsx";
import { UploadIcon } from "./components/Icons.jsx";
import useToast from "./hooks/useToast.js";
import useLibrary from "./hooks/useLibrary.js";
import useSearch from "./hooks/useSearch.js";
import useGlobalShortcuts from "./hooks/useGlobalShortcuts.js";
import useItemActions from "./hooks/useItemActions.js";

export default function App() {
  const [toast, setToast] = useToast();
  const library = useLibrary();
  const { items, archived, loaded, backendDown, health, stats, alerts, refreshSide, addLocal } = library;
  const search = useSearch(setToast);
  const { query, setQuery, mode, setMode, searching, results, answer } = search;
  const clearSearch = search.clear;
  const runSearch = search.run;
  const actions = useItemActions({ library, patchResult: search.patchResult, setToast });

  const [category, setCategory] = useState("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState(null);

  const openIngest = (files = null) => {
    setDroppedFiles(files);
    setIngestOpen(true);
  };
  const dragOver = useGlobalShortcuts({ onNew: () => openIngest(), onDropFiles: openIngest });

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

  // ---- ingest ----
  async function handleIngest(body) {
    const item = await api.ingest(body);
    addLocal([item]);
    clearSearch();
    setCategory("all");
    setToast(item.status === "done" ? "Already in your Folio." : "Saved — your local model is curating it.");
  }

  async function handleUpload(fileList) {
    const created = await api.uploadFiles(fileList);
    addLocal(created);
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
        onIngest={() => openIngest()}
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
            onIngest={() => openIngest()}
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
