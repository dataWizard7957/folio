// Thin fetch wrapper around the FastAPI backend. In dev, Vite proxies /api.
const BASE = import.meta.env.VITE_API_URL ?? "";

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    headers: isForm ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

const post = (path, body) => request(path, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });

export const api = {
  health: () => request("/api/health"),
  listItems: (archived = "false") => request(`/api/items?archived=${archived}`),
  ingest: (body) => post("/api/ingest", body),
  uploadFiles: (fileList) => {
    const form = new FormData();
    for (const f of fileList) form.append("uploads", f, f.name);
    return post("/api/ingest/file", form);
  },
  updateItem: (id, patch) => request(`/api/items/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteItem: (id) => request(`/api/items/${id}`, { method: "DELETE" }),
  reprocess: (id) => post(`/api/items/${id}/reprocess`),
  similar: (id) => request(`/api/items/${id}/similar?limit=4`),
  fileUrl: (id) => `${BASE}/api/items/${id}/file`,
  search: (q, mode = "hybrid") => request(`/api/search?q=${encodeURIComponent(q)}&mode=${mode}&limit=24`),
  ask: (question) => post("/api/ask", { question }),
  stats: () => request("/api/stats?weeks=8"),
  alerts: () => request("/api/alerts"),
  markAlertsSeen: (ids) => post("/api/alerts/seen", { ids: ids ?? null }),
  refreshAlerts: () => post("/api/alerts/refresh"),
};

export const CATEGORIES = [
  { id: "all", label: "Everything" },
  { id: "read", label: "Read" },
  { id: "build", label: "Build" },
  { id: "explore", label: "Explore" },
  { id: "cook", label: "Cook" },
  { id: "buy", label: "Buy" },
  { id: "uncategorized", label: "Unsorted" },
];
