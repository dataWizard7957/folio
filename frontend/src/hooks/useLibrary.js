import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

const POLL_MS = 2000;

/** Live + archived items, side-panel data (stats, alerts, health) and polling
 *  while anything is still being curated in the background. */
export default function useLibrary() {
  const [items, setItems] = useState([]);
  const [archived, setArchived] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [backendDown, setBackendDown] = useState(false);
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [live, arch] = await Promise.all([api.listItems("false"), api.listItems("true")]);
      setItems(live);
      setArchived(arch);
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  const refreshSide = useCallback(() => {
    api.stats().then(setStats).catch(() => {});
    api.alerts().then(setAlerts).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    refreshSide();
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [refresh, refreshSide]);

  // Poll only while something is still being curated in the background.
  const anyProcessing = items.some((i) => i.status === "pending" || i.status === "processing");
  useEffect(() => {
    if (!anyProcessing) {
      refreshSide();
      return;
    }
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [anyProcessing, refresh, refreshSide]);

  /** Apply a patch to an item wherever it lives locally. */
  const patchLocal = useCallback((id, patch) => {
    const apply = (xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x));
    setItems(apply);
    setArchived(apply);
  }, []);

  const removeLocal = useCallback((id) => {
    setItems((xs) => xs.filter((x) => x.id !== id));
    setArchived((xs) => xs.filter((x) => x.id !== id));
  }, []);

  /** Prepend new items, skipping any already present. */
  const addLocal = useCallback((created) => {
    setItems((xs) => [...created.filter((c) => !xs.some((x) => x.id === c.id)), ...xs]);
  }, []);

  return {
    items, archived, loaded, backendDown, health, stats, alerts,
    refresh, refreshSide, patchLocal, removeLocal, addLocal,
  };
}
