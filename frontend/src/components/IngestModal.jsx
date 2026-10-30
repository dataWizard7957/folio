import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileIcon, ImageIcon, LinkIcon, NoteIcon, UploadIcon, XIcon } from "./Icons.jsx";

const isUrl = (s) => /^https?:\/\/\S+$/i.test(s.trim());
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.md,.markdown,.txt,.rst,.html,.htm";

export function Modal({ open, onClose, children, wide = false, label }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 px-4 py-10 backdrop-blur-sm md:py-16"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={label}
            className={`relative w-full rounded-2xl border border-slate-800 bg-slate-925 shadow-2xl ${wide ? "max-w-3xl" : "max-w-xl"}`}
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          >
            <button onClick={onClose} className="icon-btn absolute right-3 top-3" aria-label="Close">
              <XIcon />
            </button>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function IngestModal({ open, onClose, onSubmit, onUpload, initialFiles }) {
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [picked, setPicked] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    if (open) {
      setValue("");
      setNote("");
      setError("");
      setPicked(initialFiles?.length ? [...initialFiles] : []);
      setTimeout(() => ref.current?.focus(), 60);
    }
  }, [open, initialFiles]);

  const url = isUrl(value);
  const hasFiles = picked.length > 0;

  async function submit(e) {
    e?.preventDefault();
    if (!value.trim() && !hasFiles) return;
    setBusy(true);
    setError("");
    try {
      if (hasFiles) await onUpload(picked);
      if (value.trim()) await onSubmit(url ? { url: value.trim(), text: note.trim() || null } : { text: value });
      onClose();
    } catch (err) {
      setError(err.message || "Could not save that.");
    } finally {
      setBusy(false);
    }
  }

  const addFiles = (list) => setPicked((p) => [...p, ...Array.from(list)]);

  return (
    <Modal open={open} onClose={onClose} label="Save to Folio">
      <form onSubmit={submit} className="p-6 md:p-7">
        <p className="kicker">New entry</p>
        <h2 className="mt-1 text-2xl">Save something to your Folio</h2>
        <p className="mt-1.5 text-sm text-ivory-400">
          Paste a link, a snippet or a note, or drop in PDFs and screenshots. Your local models do the rest.
        </p>

        <div className="relative mt-5">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
            }}
            onPaste={(e) => {
              if (e.clipboardData.files?.length) {
                e.preventDefault();
                addFiles(e.clipboardData.files);
              }
            }}
            rows={url ? 1 : 5}
            placeholder="https://arxiv.org/abs/…  or  a thought worth keeping  (you can paste screenshots too)"
            className="field resize-none pr-24 font-sans leading-relaxed"
          />
          <span className="pointer-events-none absolute right-3 top-3 flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-wider text-ivory-500">
            {value.trim() ? (url ? <><LinkIcon size={12} /> Link</> : <><NoteIcon size={12} /> Note</>) : null}
          </span>
        </div>

        <AnimatePresence initial={false}>
          {url && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why are you saving this? (optional)" className="field mt-3" />
            </motion.div>
          )}
        </AnimatePresence>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
          onClick={() => fileRef.current?.click()}
          className={`mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-4 text-sm transition-colors ${
            dragging ? "border-cat-read/60 bg-cat-read/5 text-ivory-100" : "border-slate-800 text-ivory-400 hover:border-slate-700 hover:text-ivory-200"
          }`}
        >
          <UploadIcon size={15} />
          Drop PDFs or screenshots, or <span className="underline underline-offset-4">browse</span>
          <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => addFiles(e.target.files)} />
        </div>

        {hasFiles && (
          <ul className="mt-3 space-y-1.5">
            {picked.map((f, i) => (
              <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-[13px] text-ivory-200">
                {f.type.startsWith("image/") ? <ImageIcon size={14} /> : <FileIcon size={14} />}
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="font-mono text-[11px] text-ivory-500">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                <button type="button" onClick={() => setPicked((p) => p.filter((_, j) => j !== i))} className="icon-btn h-6 w-6" aria-label={`Remove ${f.name}`}>
                  <XIcon size={12} />
                </button>
              </li>
            ))}
          </ul>
        )}

        {error && <p className="mt-3 text-sm text-cat-cook">{error}</p>}

        <div className="mt-6 flex items-center justify-between">
          <span className="font-mono text-[11px] text-ivory-500">⌘ / Ctrl + Enter</span>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
            <button type="submit" disabled={busy || (!value.trim() && !hasFiles)} className="btn-primary">
              {busy ? (hasFiles ? "Uploading…" : url ? "Fetching…" : "Saving…") : hasFiles ? `Save ${picked.length + (value.trim() ? 1 : 0)} item${picked.length + (value.trim() ? 1 : 0) > 1 ? "s" : ""}` : "Save to Folio"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
