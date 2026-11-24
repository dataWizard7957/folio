import { useEffect, useRef, useState } from "react";

/** "n" opens the ingest modal; files dropped anywhere open it pre-filled.
 *  Returns whether files are currently being dragged over the window. */
export default function useGlobalShortcuts({ onNew, onDropFiles }) {
  const [dragOver, setDragOver] = useState(false);
  const handlers = useRef({ onNew, onDropFiles });
  handlers.current = { onNew, onDropFiles };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
        e.preventDefault();
        handlers.current.onNew();
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
      handlers.current.onDropFiles(Array.from(e.dataTransfer.files));
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

  return dragOver;
}
