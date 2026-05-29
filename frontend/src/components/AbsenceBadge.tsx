import { useTypeColorsStore } from '../stores/typeColorsStore';

interface AbsenceBadgeProps {
  /** Absence type key ("vacation" … or masked "absent"). */
  type: string;
  /** Employee colour — rendered as the ring. */
  userColor: string;
  /** Initials shown in outline (Konturschrift), e.g. "EM". */
  initials: string;
  /** Tooltip / aria text (employee + type). */
  title?: string;
  /** Diameter in px. */
  size?: number;
}

/**
 * #157: per-employee absence badge for the team calendar.
 * - ring  = employee colour (~20 % of the radius)
 * - centre = absence-type colour (admin-configurable; neutral grey for masked "absent")
 * - initials in white with a thin dark contour so they stay legible on any centre colour.
 */
export default function AbsenceBadge({ type, userColor, initials, title, size = 26 }: AbsenceBadgeProps) {
  const colors = useTypeColorsStore((s) => s.colors);
  const centre = (colors as Record<string, string>)[type] ?? '#6B7280';
  const ring = Math.max(2, Math.round(size * 0.1)); // 10 % of diameter = 20 % of radius

  return (
    <span
      title={title}
      aria-label={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: centre,
        border: `${ring}px solid ${userColor}`,
        boxSizing: 'border-box',
        fontSize: Math.round(size * 0.4),
        fontWeight: 700,
        lineHeight: 1,
        letterSpacing: '-0.02em',
        color: '#fff',
        WebkitTextStroke: '0.6px rgba(0,0,0,0.7)',
        // Fallback contour for engines without -webkit-text-stroke.
        textShadow: '0 0 1px rgba(0,0,0,0.55)',
        userSelect: 'none',
        flexShrink: 0,
      }}
    >
      {initials}
    </span>
  );
}
