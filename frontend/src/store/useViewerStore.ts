import { create } from "zustand";

export interface ViewerTarget {
  documentId: string;
  filename: string;
  fileType: string;
  page?: number | null;
  highlightText?: string | null;
}

interface ViewerState {
  target: ViewerTarget | null;
  open: (target: ViewerTarget) => void;
  close: () => void;
}

export const useViewerStore = create<ViewerState>((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}));
