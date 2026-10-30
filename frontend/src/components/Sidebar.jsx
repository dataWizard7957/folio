import { motion } from "framer-motion";
import { CATEGORIES } from "../api.js";
import { ArchiveIcon, PlusIcon } from "./Icons.jsx";
import StatsCard from "./StatsCard.jsx";

const DOT = {
  all: "bg-ivory-200",
  read: "bg-cat-read",
  build: "bg-cat-build",
  explore: "bg-cat-explore",
  cook: "bg-cat-cook",
  buy: "bg-cat-buy",
  uncategorized: "bg-cat-uncategorized",
};

function ShelfButton({ id, label, active, count, onSelect, compact, icon }) {
  return (
    <button
      onClick={() => onSelect(id)}
      className={`relative flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
        active ? "text-ivory-50" : "text-ivory-300 hover:text-ivory-100"
      } ${compact ? "" : "w-full"}`}
      aria-pressed={active}
    >
      {active && (
        <motion.span
          layoutId={compact ? "nav-active-compact" : "nav-active"}
          className="absolute inset-0 rounded-lg border border-slate-800 bg-slate-850"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}
      {icon ?? <span className={`relative h-1.5 w-1.5 rounded-full ${DOT[id]}`} />}
      <span className="relative flex-1">{label}</span>
      {!compact && <span className="relative font-mono text-[11px] tabular-nums text-ivory-500">{count}</span>}
    </button>
  );
}

export default function Sidebar({ active, onSelect, counts, onIngest, ollama, unreadOnly, onToggleUnread, stats }) {
  const visible = CATEGORIES.filter((c) => c.id !== "uncategorized" || counts.uncategorized > 0);
  const archive = (compact) => (
    <ShelfButton
      id="archived"
      label="Archive"
      active={active === "archived"}
      count={counts.archived ?? 0}
      onSelect={onSelect}
      compact={compact}
      icon={<ArchiveIcon size={12} className="relative text-ivory-500" />}
    />
  );

  return (
    <>
      <aside className="scrollbar-thin sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto border-r border-slate-800/70 bg-slate-925/80 px-4 py-7 backdrop-blur lg:flex">
        <div className="px-3">
          <h1 className="text-[28px] font-medium leading-none">Folio</h1>
          <p className="mt-2 font-serif text-sm italic text-ivory-400">Your digital life, curated.</p>
        </div>

        <div className="mt-8 space-y-2 px-1">
          <button onClick={onIngest} className="btn-primary w-full">
            <PlusIcon /> Save something
          </button>
        </div>

        <nav className="mt-8">
          <p className="kicker mb-2 px-3">Shelves</p>
          <div className="space-y-0.5">
            {visible.map((cat) => (
              <ShelfButton key={cat.id} id={cat.id} label={cat.label} active={active === cat.id}
                           count={counts[cat.id] ?? 0} onSelect={onSelect} />
            ))}
            <div className="my-2 border-t border-slate-800/70" />
            {archive(false)}
          </div>
        </nav>

        <label className="mt-5 flex cursor-pointer items-center justify-between px-3 text-sm text-ivory-300">
          Unread only
          <span className="relative inline-flex h-5 w-9 items-center">
            <input type="checkbox" className="peer sr-only" checked={unreadOnly} onChange={onToggleUnread} />
            <span className="absolute inset-0 rounded-full bg-slate-800 transition-colors peer-checked:bg-cat-read/70" />
            <span className="absolute left-0.5 h-4 w-4 rounded-full bg-ivory-100 transition-transform peer-checked:translate-x-4" />
          </span>
        </label>

        <div className="mt-auto space-y-3 px-1 pt-6">
          <StatsCard stats={stats} />
          <OllamaStatus ollama={ollama} />
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800/70 bg-slate-950/90 backdrop-blur lg:hidden">
        <div className="flex items-center justify-between px-4 pt-4">
          <h1 className="text-2xl font-medium">Folio</h1>
          <div className="flex gap-2">
            <button onClick={onIngest} className="btn-primary px-3" aria-label="Save something">
              <PlusIcon />
            </button>
          </div>
        </div>
        <nav className="scrollbar-thin flex gap-1 overflow-x-auto px-3 py-3">
          {visible.map((cat) => (
            <ShelfButton key={cat.id} id={cat.id} label={cat.label} active={active === cat.id} onSelect={onSelect} compact />
          ))}
          {archive(true)}
        </nav>
      </header>
    </>
  );
}

function OllamaStatus({ ollama }) {
  if (!ollama) return null;
  const rows = [
    ["LLM", ollama.model, ollama.model_installed],
    ["Embeddings", ollama.embed_model, ollama.embed_installed],
    ["Vision", ollama.vision_model, ollama.vision_installed],
  ];
  return (
    <div className="rounded-xl border border-slate-800 px-3 py-2.5">
      <p className="kicker mb-1.5">{ollama.online ? "Local models" : "Ollama offline · fallbacks on"}</p>
      {rows.map(([label, name, ok]) => (
        <div key={label} className="flex items-center gap-2 py-0.5" title={ok ? `${name} installed` : `Run: ollama pull ${name}`}>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${ok ? "bg-cat-buy" : "bg-cat-cook"}`} />
          <span className="w-[72px] shrink-0 text-[11px] text-ivory-400">{label}</span>
          <span className="truncate font-mono text-[10.5px] text-ivory-500">{ok ? name : `pull ${name}`}</span>
        </div>
      ))}
    </div>
  );
}
