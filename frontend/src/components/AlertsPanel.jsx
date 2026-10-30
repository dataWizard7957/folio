import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api.js";
import { AlertIcon, ArchiveIcon, BellIcon, CodeIcon, FileIcon, RefreshIcon } from "./Icons.jsx";

const KIND = {
  major_release: { label: "Major release", icon: CodeIcon, tone: "text-cat-build" },
  release: { label: "Release", icon: CodeIcon, tone: "text-ivory-400" },
  stale: { label: "Gone quiet", icon: AlertIcon, tone: "text-cat-cook" },
  archived: { label: "Archived repo", icon: ArchiveIcon, tone: "text-cat-cook" },
  followup_paper: { label: "Follow-up paper", icon: FileIcon, tone: "text-cat-read" },
  outdated_docs: { label: "Outdated docs", icon: AlertIcon, tone: "text-cat-cook" },
};

/** Bell + dropdown: things that changed about what you saved. */
export default function AlertsPanel({ alerts, onChanged }) {
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  async function markAll() {
    await api.markAlertsSeen(null).catch(() => {});
    onChanged();
  }

  async function check() {
    setChecking(true);
    await api.refreshAlerts().catch(() => {});
    setTimeout(() => {
      onChanged();
      setChecking(false);
    }, 4000);
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} className="btn-ghost relative px-3" aria-label={`Updates (${alerts.length})`}>
        <BellIcon />
        <span className="hidden sm:inline">Updates</span>
        {alerts.length > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-cat-read px-1 font-mono text-[10px] font-medium text-slate-950">
            {alerts.length}
          </span>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="absolute right-0 z-40 mt-2 w-[380px] max-w-[calc(100vw-32px)] rounded-xl border border-slate-800 bg-slate-925 p-2 shadow-2xl"
          >
            <div className="flex items-center justify-between px-2 py-1.5">
              <p className="kicker">What changed in your library</p>
              <button onClick={check} disabled={checking} className="icon-btn" title="Check repos, papers & docs now" aria-label="Check now">
                <RefreshIcon size={14} className={checking ? "animate-spin" : ""} />
              </button>
            </div>
            {alerts.length === 0 ? (
              <p className="px-2 pb-3 pt-1 font-serif text-sm italic text-ivory-400">
                Nothing new. Folio checks your saved repos, papers and docs once a day.
              </p>
            ) : (
              <ul className="scrollbar-thin max-h-[60vh] overflow-y-auto">
                {alerts.map((a) => {
                  const k = KIND[a.kind] ?? { label: a.kind, icon: AlertIcon, tone: "text-ivory-400" };
                  const Icon = k.icon;
                  return (
                    <li key={a.id}>
                      <a
                        href={a.url || "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="flex gap-3 rounded-lg px-2 py-2.5 hover:bg-slate-850"
                      >
                        <Icon size={15} className={`mt-0.5 shrink-0 ${k.tone}`} />
                        <span className="min-w-0">
                          <span className="kicker block">{k.label}</span>
                          <span className="block text-[13px] leading-snug text-ivory-200">{a.message}</span>
                        </span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
            {alerts.length > 0 && (
              <button onClick={markAll} className="mt-1 w-full rounded-lg py-2 text-[12px] text-ivory-400 hover:bg-slate-850 hover:text-ivory-200">
                Mark all as seen
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
