import { useState } from "react";

// Validated (dataviz validate_palette.js, dark mode on #131820): both in the
// L 0.48–0.67 band, chroma >= 0.1, CVD ΔE ≥ 23.
const SAVED = "#4a8fe0";
const READ = "#b8792a";

function weekLabel(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** The honest number: saved vs read per week, last 8 weeks. */
export default function StatsCard({ stats }) {
  const [hover, setHover] = useState(null);
  if (!stats) return null;
  const weeks = stats.weeks ?? [];
  const max = Math.max(1, ...weeks.flatMap((w) => [w.saved, w.read]));
  const t = stats.this_week ?? { saved: 0, read: 0 };
  const shown = hover != null ? weeks[hover] : null;
  const H = 44;

  return (
    <div className="rounded-xl border border-slate-800 p-3">
      <p className="kicker">This week</p>
      <p className="mt-1 font-serif text-[15px] text-ivory-100">
        {t.saved} saved · {t.read} read
      </p>

      <div className="relative mt-3" onMouseLeave={() => setHover(null)}>
        <div className="flex items-end justify-between border-b border-slate-800" style={{ height: H }} role="img"
             aria-label={`Saved versus read per week, last ${weeks.length} weeks`}>
          {weeks.map((w, i) => (
            <div
              key={w.week_start}
              className="flex h-full flex-1 cursor-default items-end justify-center gap-[2px]"
              onMouseEnter={() => setHover(i)}
            >
              <span className="w-[5px] rounded-t-[2px]" style={{ height: Math.max(w.saved ? 2 : 0, (w.saved / max) * H), background: SAVED, opacity: hover == null || hover === i ? 1 : 0.4 }} />
              <span className="w-[5px] rounded-t-[2px]" style={{ height: Math.max(w.read ? 2 : 0, (w.read / max) * H), background: READ, opacity: hover == null || hover === i ? 1 : 0.4 }} />
            </div>
          ))}
        </div>
        <p className="mt-1.5 h-4 font-mono text-[10.5px] text-ivory-400">
          {shown ? `Wk of ${weekLabel(shown.week_start)}: ${shown.saved} saved · ${shown.read} read` : `last ${weeks.length} weeks`}
        </p>
        <table className="sr-only">
          <caption>Items saved and read per week</caption>
          <thead><tr><th>Week</th><th>Saved</th><th>Read</th><th>Archived</th></tr></thead>
          <tbody>
            {weeks.map((w) => (
              <tr key={w.week_start}><td>{w.week_start}</td><td>{w.saved}</td><td>{w.read}</td><td>{w.archived}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[11px] text-ivory-400">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: SAVED }} /> Saved</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: READ }} /> Read</span>
        {stats.read_ratio != null && <span className="ml-auto font-mono">{Math.round(stats.read_ratio * 100)}% read</span>}
      </div>
    </div>
  );
}
