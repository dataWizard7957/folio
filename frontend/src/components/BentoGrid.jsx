import { forwardRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { api } from "../api.js";
import {
  AlertIcon,
  ArchiveIcon,
  ArrowIcon,
  CheckIcon,
  CodeIcon,
  ExternalIcon,
  FileIcon,
  ImageIcon,
  LinkIcon,
  NoteIcon,
  PinIcon,
  RefreshIcon,
  StarIcon,
  TrashIcon,
  UndoIcon,
} from "./Icons.jsx";

const PILL = {
  read: "border-cat-read/30 bg-cat-read/10 text-cat-read",
  build: "border-cat-build/30 bg-cat-build/10 text-cat-build",
  explore: "border-cat-explore/30 bg-cat-explore/10 text-cat-explore",
  cook: "border-cat-cook/30 bg-cat-cook/10 text-cat-cook",
  buy: "border-cat-buy/30 bg-cat-buy/10 text-cat-buy",
  uncategorized: "border-slate-700 bg-slate-850 text-ivory-400",
};

const ACCENT = {
  read: "from-cat-read/50",
  build: "from-cat-build/50",
  explore: "from-cat-explore/50",
  cook: "from-cat-cook/50",
  buy: "from-cat-buy/50",
  uncategorized: "from-slate-700",
};

const TYPE_LABEL = {
  article: "Article",
  repo: "Repository",
  paper: "Paper",
  video: "Video",
  documentation: "Docs",
  note: "Note",
  text: "Clipping",
  pdf: "PDF",
  image: "Screenshot",
};

const spring = { type: "spring", stiffness: 380, damping: 36, mass: 0.9 };

function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const compact = (n) => (n == null ? "" : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));

/**
 * Asymmetric bento: starred items span two columns, and when nothing is
 * starred the first item leads as the featured card. `grid-flow-dense`
 * back-fills holes. In search mode `hits` carries snippets + match info.
 */
export default function BentoGrid({ items, hits, actions }) {
  const anyStarred = !hits && items.some((i) => i.featured);

  return (
    <LayoutGroup>
      <motion.div layout className="grid grid-flow-dense grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence mode="popLayout" initial={false}>
          {items.map((item, idx) => (
            <Card
              key={item.id}
              item={item}
              hit={hits?.[item.id]}
              wide={hits ? idx === 0 : item.featured || (!anyStarred && idx === 0)}
              actions={actions}
            />
          ))}
        </AnimatePresence>
      </motion.div>
    </LayoutGroup>
  );
}

// forwardRef is required: AnimatePresence mode="popLayout" measures exiting children via ref.
const Card = forwardRef(function Card({ item, hit, wide, actions }, ref) {
  const processing = item.status === "pending" || item.status === "processing";
  const usedFallback = item.status === "done" && item.error && item.category === "uncategorized";
  const m = item.meta || {};
  const isImage = item.content_type === "image" && m.file_path;
  const TypeIcon = item.content_type === "image" ? ImageIcon : item.content_type === "pdf" ? FileIcon : item.url ? LinkIcon : NoteIcon;

  return (
    <motion.article
      ref={ref}
      id={`item-${item.id}`}
      layout
      initial={{ opacity: 0, scale: 0.96, y: 12 }}
      animate={{ opacity: item.is_read || item.archived ? 0.55 : 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.18 } }}
      transition={spring}
      className={`group relative flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-card transition-colors hover:border-slate-700 ${
        wide ? "md:col-span-2" : ""
      }`}
    >
      <div className={`h-px w-full bg-gradient-to-r ${ACCENT[item.category]} to-transparent`} />

      {isImage && (
        <motion.a layout="position" href={api.fileUrl(item.id)} target="_blank" rel="noreferrer" className="block overflow-hidden border-b border-slate-800">
          <img
            src={api.fileUrl(item.id)}
            alt=""
            loading="lazy"
            onError={(e) => (e.currentTarget.parentElement.style.display = "none")}
            className={`w-full object-cover object-top opacity-90 transition-opacity group-hover:opacity-100 ${wide ? "h-56" : "h-36"}`}
          />
        </motion.a>
      )}

      <div className={`flex flex-1 flex-col ${wide ? "p-7 md:p-8" : "p-5"}`}>
        <motion.div layout="position" className="flex items-center justify-between gap-3">
          <span className="kicker flex min-w-0 items-center gap-1.5">
            <TypeIcon size={12} />
            <span className="truncate">
              {TYPE_LABEL[item.content_type] ?? item.content_type}
              {item.source ? ` · ${item.source}` : item.file_name && !isImage ? ` · ${item.file_name}` : ""}
            </span>
          </span>
          <span className="shrink-0 font-mono text-[11px] text-ivory-500">
            {hit?.similarity != null ? `${Math.round(hit.similarity * 100)}% match` : timeAgo(item.created_at)}
          </span>
        </motion.div>

        <motion.h3
          layout="position"
          className={`mt-3 font-medium leading-snug ${wide ? "text-[22px] md:text-[24px]" : "text-[19px]"}`}
        >
          {item.url ? (
            <a href={item.url} target="_blank" rel="noreferrer" className="decoration-ivory-500/40 underline-offset-4 hover:underline">
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </motion.h3>

        <motion.div layout="position" className="mt-3 flex flex-wrap items-center gap-2">
          {processing ? (
            <span className="pill border-slate-700 text-ivory-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cat-read" />
              {item.content_type === "image" ? "Reading screenshot" : item.content_type === "pdf" ? "Reading PDF" : "Curating"}
            </span>
          ) : (
            <span className={`pill ${PILL[item.category]}`}>{item.category === "uncategorized" ? "unsorted" : item.category}</span>
          )}
          {item.featured && (
            <span className="pill border-ivory-400/20 text-ivory-300">
              <StarIcon size={10} /> Featured
            </span>
          )}
          {item.kept && (
            <span className="pill border-ivory-400/20 text-ivory-300">
              <PinIcon size={10} /> Kept
            </span>
          )}
          {item.archived && <span className="pill border-slate-700 text-ivory-500">Archived</span>}
          {hit?.matched?.map((x) => (
            <span key={x} className="pill border-slate-700 text-ivory-500">{x}</span>
          ))}
        </motion.div>

        <DevMeta item={item} />

        <motion.div layout="position" className="mt-4 flex-1">
          {processing ? (
            <div className="space-y-2" aria-label="Summarizing">
              <div className="shimmer h-3 w-full rounded" />
              <div className="shimmer h-3 w-11/12 rounded" />
              <div className="shimmer h-3 w-2/3 rounded" />
            </div>
          ) : hit?.snippet ? (
            <p className="text-[14px] leading-relaxed text-ivory-300">
              <span className="text-ivory-500">“</span>
              {hit.snippet}
              <span className="text-ivory-500">”</span>
            </p>
          ) : (
            <p
              className={`text-ivory-300 ${
                wide ? "max-w-3xl font-serif text-[15px] leading-relaxed" : "line-clamp-4 text-[14px] leading-relaxed"
              }`}
            >
              {item.summary || "No summary yet."}
            </p>
          )}
          {usedFallback && <p className="mt-2 font-mono text-[11px] text-cat-cook/80">AI was offline · basic summary used</p>}
        </motion.div>

        {item.next_step && !item.is_read && !processing && (
          <motion.div layout="position" className="mt-4 flex items-start gap-2 rounded-lg border border-cat-build/25 bg-cat-build/[0.06] px-3 py-2.5">
            <ArrowIcon size={14} className="mt-0.5 shrink-0 text-cat-build" />
            <p className="text-[13px] leading-snug text-ivory-200">
              <span className="kicker mr-1.5 text-cat-build">First step</span>
              {item.next_step}
            </p>
          </motion.div>
        )}

        {item.tags?.length > 0 && (
          <motion.div layout="position" className="mt-4 flex flex-wrap gap-x-3 gap-y-1">
            {item.tags.map((t) => (
              <span key={t} className="font-mono text-[11px] text-ivory-500">
                #{t}
              </span>
            ))}
          </motion.div>
        )}

        <motion.footer layout="position" className="mt-5 flex items-center gap-1 border-t border-slate-800/80 pt-3">
          {item.archived ? (
            <button onClick={() => actions.archive(item)} className="btn px-2.5 py-1.5 text-[13px] text-ivory-200 hover:bg-slate-850">
              <UndoIcon size={14} /> Restore
            </button>
          ) : (
            <button
              onClick={() => actions.toggleRead(item)}
              className={`btn px-2.5 py-1.5 text-[13px] hover:bg-slate-850 ${item.is_read ? "text-ivory-400" : "text-ivory-200"}`}
            >
              {item.is_read ? <UndoIcon size={14} /> : <CheckIcon size={14} />}
              {item.is_read ? "Mark unread" : "Mark as read"}
            </button>
          )}
          <div className="ml-auto flex items-center gap-0.5">
            {usedFallback && (
              <IconBtn onClick={() => actions.reprocess(item)} label="Retry AI curation"><RefreshIcon size={15} /></IconBtn>
            )}
            {(item.url || m.file_path) && (
              <a href={item.url || api.fileUrl(item.id)} target="_blank" rel="noreferrer" className="icon-btn" title="Open source" aria-label="Open source">
                <ExternalIcon size={15} />
              </a>
            )}
            <IconBtn onClick={() => actions.toggleKept(item)} label={item.kept ? "Stop keeping" : "Keep (never auto-archive)"} active={item.kept}>
              <PinIcon size={15} />
            </IconBtn>
            <IconBtn onClick={() => actions.toggleFeatured(item)} label={item.featured ? "Unfeature" : "Feature"} active={item.featured}>
              <StarIcon size={15} fill={item.featured ? "currentColor" : "none"} />
            </IconBtn>
            {!item.archived && (
              <IconBtn onClick={() => actions.archive(item)} label="Let it go (archive)"><ArchiveIcon size={15} /></IconBtn>
            )}
            <ConfirmDelete onConfirm={() => actions.remove(item)} />
          </div>
        </motion.footer>
      </div>
    </motion.article>
  );
});

function IconBtn({ onClick, label, active, children }) {
  return (
    <button onClick={onClick} className={`icon-btn ${active ? "text-cat-read hover:text-cat-read" : ""}`} title={label} aria-label={label}>
      {children}
    </button>
  );
}

function ConfirmDelete({ onConfirm }) {
  const [armed, setArmed] = useState(false);
  if (armed)
    return (
      <button onClick={onConfirm} onMouseLeave={() => setArmed(false)} className="btn px-2 py-1 text-[12px] text-cat-cook hover:bg-cat-cook/10">
        Delete?
      </button>
    );
  return (
    <button onClick={() => setArmed(true)} className="icon-btn hover:!text-cat-cook" title="Delete" aria-label="Delete">
      <TrashIcon size={15} />
    </button>
  );
}

/** Developer-aware metadata: repos, papers, docs, PDFs. */
function DevMeta({ item }) {
  const m = item.meta || {};
  const row = "mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-ivory-400";
  if (m.kind === "repo")
    return (
      <motion.div layout="position" className={row}>
        {m.stars != null && <span>★ {compact(m.stars)}</span>}
        {m.language && <span>{m.language}</span>}
        {m.latest_release && <span className="text-ivory-300">{m.latest_release}</span>}
        {m.license && <span>{m.license}</span>}
        {m.stale && (
          <span className="flex items-center gap-1 text-cat-cook">
            <AlertIcon size={11} /> {m.archived ? "archived" : `no commits in ${m.days_since_push}d`}
          </span>
        )}
      </motion.div>
    );
  if (m.kind === "paper")
    return (
      <motion.div layout="position" className={row}>
        {m.authors?.length > 0 && (
          <span className="font-serif text-[12.5px] normal-case italic tracking-normal text-ivory-300">
            {m.authors.slice(0, 2).join(", ")}
            {m.authors.length > 2 ? " et al." : ""}
          </span>
        )}
        {m.arxiv_id && <span>arXiv:{m.arxiv_id}</span>}
        {m.citations != null && <span>{compact(m.citations)} citations</span>}
        {m.code_links?.[0] && (
          <a href={m.code_links[0]} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-cat-build hover:underline">
            <CodeIcon size={11} /> code
          </a>
        )}
      </motion.div>
    );
  if (m.kind === "docs")
    return (
      <motion.div layout="position" className={row}>
        <span>
          {m.package} {m.doc_version ? `v${m.doc_version}` : "· latest"}
        </span>
        {m.outdated ? (
          <span className="flex items-center gap-1 text-cat-cook">
            <AlertIcon size={11} /> outdated · v{m.latest_version} is out
          </span>
        ) : (
          m.latest_version && <span>current v{m.latest_version}</span>
        )}
      </motion.div>
    );
  if (m.kind === "pdf")
    return (
      <motion.div layout="position" className={row}>
        <span>{m.pages} page{m.pages === 1 ? "" : "s"}</span>
        {m.author && <span>{m.author}</span>}
        {m.scanned && <span>scanned · read by vision model</span>}
      </motion.div>
    );
  return null;
}
