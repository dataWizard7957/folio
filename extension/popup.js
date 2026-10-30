import { getSettings, isSavable, ping, saveToFolio } from "./api.js";

const $ = (id) => document.getElementById(id);
const KIND = [
  [/^https?:\/\/(www\.)?github\.com\/[^/]+\/[^/]+/i, "Repository"],
  [/^https?:\/\/(www\.)?arxiv\.org\//i, "Paper"],
  [/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\//i, "Video"],
  [/^https?:\/\/(docs\.|developer\.)|\/docs?\//i, "Docs"],
];

let tab;
let selection = "";

async function init() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $("title").textContent = tab?.title || "Untitled";
  try {
    $("host").textContent = new URL(tab.url).hostname.replace(/^www\./, "");
  } catch {
    $("host").textContent = "";
  }
  $("kind").textContent = KIND.find(([re]) => re.test(tab?.url || ""))?.[1] ?? "This page";

  if (!isSavable(tab?.url)) {
    $("save").disabled = true;
    $("msg").textContent = "This page can't be saved (browser-internal URL).";
  } else {
    // Grab any highlighted text to store with the link.
    try {
      const [res] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => window.getSelection()?.toString().trim().slice(0, 4000) || "",
      });
      selection = res?.result || "";
      if (selection) $("note").placeholder = `Selected text will be saved: “${selection.slice(0, 60)}…”`;
    } catch {
      /* restricted page (e.g. Chrome Web Store) */
    }
  }

  const health = await ping();
  $("status").className = `dot ${health ? "on" : "off"}`;
  $("status").title = health ? "Connected to Folio" : "Folio API not reachable";
  if (!health) {
    $("msg").textContent = "Can't reach Folio. Is the backend running?";
    $("msg").className = "msg err";
  }
  $("note").focus();
}

async function save() {
  $("save").disabled = true;
  $("save").textContent = "Saving…";
  const note = [$("note").value.trim(), selection && `> ${selection}`].filter(Boolean).join("\n\n");
  try {
    const { item, duplicate } = await saveToFolio({ url: tab.url, text: note || null, title: tab.title });
    $("msg").textContent = duplicate ? "Already in your Folio." : `Saved — curating “${item.title.slice(0, 50)}”.`;
    $("msg").className = "msg ok";
    $("save").textContent = duplicate ? "Already saved" : "Saved ✓";
    setTimeout(() => window.close(), 1400);
  } catch (err) {
    $("msg").textContent = `Couldn't save: ${err.message}`;
    $("msg").className = "msg err";
    $("save").disabled = false;
    $("save").textContent = "Try again";
  }
}

$("save").addEventListener("click", save);
$("note").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
});
$("open").addEventListener("click", async (e) => {
  e.preventDefault();
  const { appUrl } = await getSettings();
  chrome.tabs.create({ url: appUrl });
});

init();
