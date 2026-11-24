import { useCallback, useState } from "react";
import { api } from "../api.js";

/** Search / ask-your-library state. */
export default function useSearch(onError) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("search");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null); // {order, items, hits, retrieval}
  const [answer, setAnswer] = useState(null);

  const clear = useCallback(() => {
    setQuery("");
    setResults(null);
    setAnswer(null);
  }, []);

  async function run() {
    setSearching(true);
    setAnswer(null);
    setResults(null);
    try {
      if (mode === "ask") {
        setAnswer(await api.ask(query));
      } else {
        const res = await api.search(query);
        setResults({
          order: res.results.map((r) => r.item.id),
          items: Object.fromEntries(res.results.map((r) => [r.item.id, r.item])),
          hits: Object.fromEntries(res.results.map((r) => [r.item.id, r])),
          retrieval: res.retrieval,
        });
      }
    } catch (e) {
      onError(e.message);
    } finally {
      setSearching(false);
    }
  }

  /** Keep a search result in sync with an optimistic item update. */
  const patchResult = useCallback((id, patch) => {
    setResults((r) => (r && r.items[id] ? { ...r, items: { ...r.items, [id]: { ...r.items[id], ...patch } } } : r));
  }, []);

  return { query, setQuery, mode, setMode, searching, results, answer, run, clear, patchResult };
}
