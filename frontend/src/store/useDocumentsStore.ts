import { create } from "zustand";
import * as api from "../lib/api";
import type { DocumentRecord, WatchedFolder } from "../lib/types";

interface DocumentsState {
  documents: DocumentRecord[];
  tags: string[];
  watchedFolders: WatchedFolder[];
  loading: boolean;
  pollHandle: ReturnType<typeof setInterval> | null;

  load: () => Promise<void>;
  loadWatchedFolders: () => Promise<void>;
  upload: (files: File[], tags: string[]) => Promise<void>;
  ingestUrl: (url: string, tags: string[]) => Promise<void>;
  remove: (id: string) => Promise<void>;
  reindex: (id: string) => Promise<void>;
  setTags: (id: string, tags: string[]) => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
}

export const useDocumentsStore = create<DocumentsState>((set, get) => ({
  documents: [],
  tags: [],
  watchedFolders: [],
  loading: false,
  pollHandle: null,

  load: async () => {
    set({ loading: true });
    try {
      const [documents, tags] = await Promise.all([api.listDocuments(), api.listAllTags()]);
      set({ documents, tags });
    } finally {
      set({ loading: false });
    }
  },

  loadWatchedFolders: async () => {
    const watchedFolders = await api.listWatchedFolders();
    set({ watchedFolders });
  },

  upload: async (files, tags) => {
    for (const file of files) {
      await api.uploadDocument(file, tags);
    }
    await get().load();
    get().startPolling();
  },

  ingestUrl: async (url, tags) => {
    await api.ingestUrl(url, tags);
    await get().load();
    get().startPolling();
  },

  remove: async (id) => {
    await api.deleteDocument(id);
    set((s) => ({ documents: s.documents.filter((d) => d.id !== id) }));
  },

  reindex: async (id) => {
    await api.reindexDocument(id);
    await get().load();
    get().startPolling();
  },

  setTags: async (id, tags) => {
    const updated = await api.setDocumentTags(id, tags);
    set((s) => ({ documents: s.documents.map((d) => (d.id === id ? updated : d)) }));
    const allTags = await api.listAllTags();
    set({ tags: allTags });
  },

  startPolling: () => {
    if (get().pollHandle) return;
    const handle = setInterval(async () => {
      const docs = await api.listDocuments();
      set({ documents: docs });
      const stillBusy = docs.some((d) => d.status === "pending" || d.status === "processing");
      if (!stillBusy) {
        get().stopPolling();
      }
    }, 1500);
    set({ pollHandle: handle });
  },

  stopPolling: () => {
    const handle = get().pollHandle;
    if (handle) clearInterval(handle);
    set({ pollHandle: null });
  },
}));
