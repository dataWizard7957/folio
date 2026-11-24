import { motion } from "framer-motion";
import { PlusIcon } from "./Icons.jsx";

export default function EmptyState({ kind, onIngest }) {
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
