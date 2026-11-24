import { motion } from "framer-motion";
import { SparkIcon } from "./Icons.jsx";

/** Answer with inline [id] citations rendered as links to the cited items. */
export default function AnswerPanel({ answer, byId, onOpen }) {
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
