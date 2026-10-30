import { DEFAULTS, getSettings, ping } from "./api.js";

const $ = (id) => document.getElementById(id);

(async () => {
  const s = await getSettings();
  $("apiUrl").value = s.apiUrl;
  $("appUrl").value = s.appUrl;
})();

$("save").addEventListener("click", async () => {
  const apiUrl = $("apiUrl").value.trim() || DEFAULTS.apiUrl;
  const appUrl = $("appUrl").value.trim() || DEFAULTS.appUrl;
  await chrome.storage.sync.set({ apiUrl, appUrl });
  const ok = await ping();
  $("msg").textContent = ok ? "Saved · connected to Folio ✓" : "Saved, but the API isn't reachable at that URL.";
  $("msg").className = `msg ${ok ? "ok" : "err"}`;
});
