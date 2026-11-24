import { api } from "../api.js";

/** Optimistic item mutations, rolled back with a toast on failure. */
export default function useItemActions({ library, patchResult, setToast }) {
  const { patchLocal, removeLocal, refresh } = library;

  const patchEverywhere = (id, change) => {
    patchLocal(id, change);
    patchResult(id, change);
  };

  async function patch(item, change, failMsg = "Couldn't update that item.") {
    const before = Object.fromEntries(Object.keys(change).map((k) => [k, item[k]]));
    patchEverywhere(item.id, change);
    try {
      await api.updateItem(item.id, change);
      return true;
    } catch {
      patchEverywhere(item.id, before);
      setToast(failMsg);
      return false;
    }
  }

  return {
    toggleRead: (item) => patch(item, { is_read: !item.is_read }),
    toggleFeatured: (item) => patch(item, { featured: !item.featured }),
    toggleKept: async (item) => {
      if (await patch(item, { kept: !item.kept })) setToast(item.kept ? "No longer kept." : "Kept — Folio won't auto-archive this.");
    },
    archive: async (item) => {
      if (await patch(item, { archived: !item.archived })) {
        setToast(item.archived ? "Restored to your shelves." : "Let go. It's in the Archive if you change your mind.");
        refresh();
      }
    },
    remove: async (item) => {
      removeLocal(item.id);
      try {
        await api.deleteItem(item.id);
        setToast("Removed from your Folio.");
      } catch {
        refresh();
        setToast("Couldn't delete that item.");
      }
    },
    reprocess: async (item) => {
      patchEverywhere(item.id, { status: "pending" });
      await api.reprocess(item.id).catch(() => null);
      refresh();
    },
  };
}
