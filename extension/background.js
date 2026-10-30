import { isSavable, saveToFolio, uploadToFolio } from "./api.js";

const MENU = {
  page: "folio-save-page",
  link: "folio-save-link",
  selection: "folio-save-selection",
  image: "folio-save-image",
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: MENU.page, title: "Save page to Folio", contexts: ["page"] });
    chrome.contextMenus.create({ id: MENU.link, title: "Save link to Folio", contexts: ["link"] });
    chrome.contextMenus.create({ id: MENU.selection, title: "Save selection to Folio", contexts: ["selection"] });
    chrome.contextMenus.create({ id: MENU.image, title: "Save image to Folio", contexts: ["image"] });
  });
});

// Badge feedback: ✓ saved, = already saved, ! error.
async function flash(tabId, text, color) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color, tabId });
    await chrome.action.setBadgeText({ text, tabId });
    setTimeout(() => chrome.action.setBadgeText({ text: "", tabId }).catch(() => {}), 2500);
  } catch {
    /* tab may be gone */
  }
}

async function run(tabId, fn) {
  try {
    const { duplicate } = await fn();
    await flash(tabId, duplicate ? "=" : "✓", duplicate ? "#6fa3c7" : "#8fae7e");
  } catch (err) {
    console.warn("[Folio] save failed:", err);
    await flash(tabId, "!", "#d97757");
  }
}

function filenameFor(srcUrl, type) {
  try {
    const name = new URL(srcUrl).pathname.split("/").pop();
    if (name && /\.[a-z0-9]{2,5}$/i.test(name)) return decodeURIComponent(name);
  } catch {
    /* data: or blob: URL */
  }
  const ext = (type.split("/")[1] || "png").replace("jpeg", "jpg").replace("svg+xml", "svg");
  return `image-${Date.now()}.${ext}`;
}

async function saveImage(info, tab) {
  try {
    // Works for same-origin, CORS-enabled and data: images.
    const res = await fetch(info.srcUrl);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    if (!blob.type.startsWith("image/")) throw new Error("not an image");
    return await uploadToFolio(blob, filenameFor(info.srcUrl, blob.type));
  } catch {
    // Cross-origin image we can't read: save it as a link instead.
    return saveToFolio({ url: info.srcUrl, text: `Image from ${tab?.title || info.pageUrl}`, title: tab?.title });
  }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const tabId = tab?.id;
  switch (info.menuItemId) {
    case MENU.page:
      if (isSavable(info.pageUrl)) run(tabId, () => saveToFolio({ url: info.pageUrl, title: tab?.title }));
      break;
    case MENU.link:
      run(tabId, () => saveToFolio({ url: info.linkUrl }));
      break;
    case MENU.selection:
      run(tabId, () =>
        saveToFolio({
          text: `${info.selectionText}\n\nSource: ${tab?.title || ""} ${info.pageUrl}`.trim(),
          title: `Quote from ${tab?.title || new URL(info.pageUrl).hostname}`.slice(0, 280),
        })
      );
      break;
    case MENU.image:
      run(tabId, () => saveImage(info, tab));
      break;
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "save-page") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && isSavable(tab.url)) run(tab.id, () => saveToFolio({ url: tab.url, title: tab.title }));
});
