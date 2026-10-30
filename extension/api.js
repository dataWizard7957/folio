// Shared helpers for the popup, options page and background worker.
export const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  appUrl: "http://localhost:5173",
};

export async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function base() {
  const { apiUrl } = await getSettings();
  return apiUrl.replace(/\/+$/, "");
}

async function parse(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/** Save a URL (optionally with a note) or free text. Returns {item, duplicate}. */
export async function saveToFolio({ url, text, title }) {
  const res = await fetch(`${await base()}/api/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url || null, text: text || null, title: title || null }),
  });
  const item = await parse(res);
  return { item, duplicate: res.headers.get("X-Folio-Duplicate") === "1" || res.status === 200 };
}

/** Upload a Blob (image / PDF) as a file. */
export async function uploadToFolio(blob, filename) {
  const form = new FormData();
  form.append("uploads", blob, filename);
  const res = await fetch(`${await base()}/api/ingest/file`, { method: "POST", body: form });
  const items = await parse(res);
  return { item: items[0], duplicate: res.status === 200 };
}

export async function ping() {
  try {
    const res = await fetch(`${await base()}/api/health`, { signal: AbortSignal.timeout(2500) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export function isSavable(url) {
  return /^https?:\/\//i.test(url || "");
}
