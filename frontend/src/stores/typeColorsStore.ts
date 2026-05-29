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
 * Inline-Style für einen Typ-Chip aus einem konfigurierten Hex-Wert:
 * leichter Hintergrund + kräftige Schrift/Border in derselben Farbe.
 */
export function chipStyle(hex: string): React.CSSProperties {
  return {
    backgroundColor: `${hex}1A`, // ~10% Deckkraft
    color: hex,
    borderColor: `${hex}55`,
  };
}
