import { create } from 'zustand';
import apiClient from '../api/client';
import type { AbsenceType } from '../constants/absenceTypes';

// #157: Admin-konfigurierbare Farben pro Typ. "work" = Anwesenheit (Zeiteintrag),
// die übrigen Keys entsprechen den AbsenceType-Werten.
export type ColorTypeKey = 'work' | AbsenceType;

// Muss mit DEFAULT_TYPE_COLORS in backend/app/services/type_colors_service.py
// übereinstimmen (Fallback, falls /me/type-colors (noch) nicht geladen ist).
export const DEFAULT_TYPE_COLORS: Record<ColorTypeKey, string> = {
  work: '#16A34A',
  training: '#15803D',
  vacation: '#2563EB',
  sick: '#DC2626',
  overtime: '#7C3AED',
  other: '#6B7280',
  paid_leave: '#0D9488',
};

interface TypeColorsState {
  colors: Record<ColorTypeKey, string>;
  isLoaded: boolean;
  fetch: () => Promise<void>;
  setColors: (colors: Record<string, string>) => void;
  colorFor: (type: ColorTypeKey | string) => string;
}

export const useTypeColorsStore = create<TypeColorsState>((set, get) => ({
  colors: { ...DEFAULT_TYPE_COLORS },
  isLoaded: false,

  fetch: async () => {
    try {
      const { data } = await apiClient.get<Record<string, string>>('/me/type-colors');
      set({ colors: { ...DEFAULT_TYPE_COLORS, ...data }, isLoaded: true });
    } catch {
      set({ colors: { ...DEFAULT_TYPE_COLORS }, isLoaded: true });
    }
  },

  // Nach dem Admin-Speichern: Store sofort mit der gemergten Map aktualisieren.
  setColors: (colors) => set({ colors: { ...DEFAULT_TYPE_COLORS, ...colors }, isLoaded: true }),

  colorFor: (type) => {
    const c = get().colors as Record<string, string>;
    return c[type] ?? DEFAULT_TYPE_COLORS[type as ColorTypeKey] ?? '#6B7280';
  },
}));

/**
 * Liefert eine gut lesbare Textfarbe (#111827 dunkel oder #FFFFFF weiß) für eine
 * gegebene Hintergrundfarbe — basierend auf WCAG-Relativhelligkeit. Verhindert
 * weiße Schrift auf hellen (z. B. gelben) Admin-Farben (Review-Finding HIGH).
 */
export function pickTextColor(hex: string): string {
  const h = (hex || '').replace('#', '');
  if (h.length !== 6) return '#111827';
  const toLin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const r = toLin(parseInt(h.slice(0, 2), 16));
  const g = toLin(parseInt(h.slice(2, 4), 16));
  const b = toLin(parseInt(h.slice(4, 6), 16));
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.5 ? '#111827' : '#FFFFFF';
}
