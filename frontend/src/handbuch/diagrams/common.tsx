import type { ReactNode } from 'react';

export const C = {
  text: '#1E293B',
  muted: '#64748B',
  line: '#CBD5E1',
  blue: '#3B82F6',
  blueSoft: '#DBEAFE',
  green: '#16A34A',
  greenSoft: '#DCFCE7',
  red: '#DC2626',
  redSoft: '#FEE2E2',
  amber: '#D97706',
  amberSoft: '#FEF3C7',
  violet: '#7C3AED',
  violetSoft: '#EDE9FE',
  grey: '#94A3B8',
} as const;

/** Deutsche Zahl mit Komma; `sign` setzt + vor positive Werte, Minus als U+2212. */
export function fmt(n: number, digits = 2, sign = false): string {
  const s = Math.abs(n).toFixed(digits).replace('.', ',');
  if (n < 0) return `−${s}`;
  return sign && n > 0 ? `+${s}` : s;
}

/** Gemeinsamer SVG-Rahmen: viewBox, 100 % Breite, Bild-Rolle mit Alt-Text, keine style-Attribute. */
export function DiagramSvg({ w, h, label, children }: { w: number; h: number; label: string; children: ReactNode }) {
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width="100%"
      role="img"
      aria-label={label}
      fontFamily="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
      className="block h-auto w-full max-w-[640px]"
    >
      {children}
    </svg>
  );
}

export function Swatch({ x, y, color }: { x: number; y: number; color: string }) {
  return <rect x={x} y={y - 13} width={16} height={16} rx={3} fill={color} />;
}
