import { create } from 'zustand';

interface UIState {
  isStampSheetOpen: boolean;
  stampVersion: number;
  openStampSheet: () => void;
  closeStampSheet: () => void;
  notifyStampChange: () => void;
}

export const useUIStore = create<UIState>()((set) => ({
  isStampSheetOpen: false,
  stampVersion: 0,
  openStampSheet: () => set({ isStampSheetOpen: true }),
  closeStampSheet: () => set({ isStampSheetOpen: false }),
  notifyStampChange: () => set((s) => ({ stampVersion: s.stampVersion + 1 })),
}));
