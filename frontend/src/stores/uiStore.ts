import { create } from 'zustand';

interface UIState {
  isStampSheetOpen: boolean;
  openStampSheet: () => void;
  closeStampSheet: () => void;
}

export const useUIStore = create<UIState>()((set) => ({
  isStampSheetOpen: false,
  openStampSheet: () => set({ isStampSheetOpen: true }),
  closeStampSheet: () => set({ isStampSheetOpen: false }),
}));
