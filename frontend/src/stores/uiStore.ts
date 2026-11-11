import { create } from 'zustand';

interface UIState {
  isStampSheetOpen: boolean;
  stampVersion: number;
  /** antrag-16: Antrags-Badges im Menü neu laden (nach Genehmigen/Ablehnen). */
  requestVersion: number;
  notifyRequestChange: () => void;
  openStampSheet: () => void;
  closeStampSheet: () => void;
  notifyStampChange: () => void;
}

export const useUIStore = create<UIState>()((set) => ({
  isStampSheetOpen: false,
  stampVersion: 0,
  requestVersion: 0,
  notifyRequestChange: () => set((s) => ({ requestVersion: s.requestVersion + 1 })),
  openStampSheet: () => set({ isStampSheetOpen: true }),
  closeStampSheet: () => set({ isStampSheetOpen: false }),
  notifyStampChange: () => set((s) => ({ stampVersion: s.stampVersion + 1 })),
}));
