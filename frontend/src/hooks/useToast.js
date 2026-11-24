import { useEffect, useState } from "react";

/** A single transient message that clears itself after `ms`. */
export default function useToast(ms = 2800) {
  const [toast, setToast] = useState("");
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), ms);
    return () => clearTimeout(t);
  }, [toast, ms]);
  return [toast, setToast];
}
