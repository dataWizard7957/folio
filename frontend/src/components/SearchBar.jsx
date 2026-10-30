import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { SearchIcon, SparkIcon, XIcon } from "./Icons.jsx";

/**
 * One box, two modes:
 *   Search — hybrid semantic + keyword search; results replace the grid.
 *   Ask    — a question answered from your own library, with citations.
 */
export default function SearchBar({ value, onChange, mode, onModeChange, onSubmit, onClear, busy }) {
  const ref = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSubmit();
      }}
      className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/70 p-1.5 focus-within:border-slate-700"
    >
      <div className="relative flex rounded-lg bg-slate-950/60 p-0.5" role="tablist" aria-label="Search mode">
        {[
          ["search", "Search", SearchIcon],
          ["ask", "Ask", SparkIcon],
        ].map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            onClick={() => onModeChange(id)}
            className={`relative flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
              mode === id ? "text-ivory-50" : "text-ivory-400 hover:text-ivory-200"
            }`}
          >
            {mode === id && (
              <motion.span layoutId="search-mode" className="absolute inset-0 rounded-md bg-slate-850"
                           transition={{ type: "spring", stiffness: 420, damping: 34 }} />
            )}
            <Icon size={13} className="relative" />
            <span className="relative">{label}</span>
          </button>
        ))}
      </div>
      <input
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onClear()}
        placeholder={mode === "ask" ? "Ask your library… “what have I saved about RAG evaluation?”" : "Find anything… “that paper about attention sparsity”"}
        className="min-w-0 flex-1 bg-transparent px-1 text-sm text-ivory-100 placeholder:text-ivory-500 focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0"
        aria-label={mode === "ask" ? "Ask a question" : "Search"}
      />
      {busy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-ivory-500 border-t-transparent" aria-label="Loading" />}
      {value && (
        <button type="button" onClick={onClear} className="icon-btn" aria-label="Clear">
          <XIcon size={14} />
        </button>
      )}
      <kbd className="mr-1 hidden rounded border border-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-ivory-500 md:block">⌘K</kbd>
    </form>
  );
}
