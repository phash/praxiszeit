import { useTypeColorsStore, pickTextColor } from '../stores/typeColorsStore';

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
  /**
   * When the surrounding row already renders the name + type as text (e.g. the
   * mobile list), set this so the badge is hidden from screen readers and not
   * announced twice. The `title` tooltip stays available for mouse users.
   */
  decorative?: boolean;
}

/**
 * #157: per-employee absence badge for the team calendar.
 * - ring  = employee colour (~20 % of the radius)
 * - centre = absence-type colour (admin-configurable; neutral grey for masked "absent")
 * - initials in white with a thin dark contour so they stay legible on any centre colour.
 */
export default function AbsenceBadge({ type, userColor, initials, title, size = 26, decorative = false }: AbsenceBadgeProps) {
  const colors = useTypeColorsStore((s) => s.colors);
  const centre = (colors as Record<string, string>)[type] ?? '#6B7280';
  const ring = Math.max(2, Math.round(size * 0.1)); // 10 % of diameter = 20 % of radius
  // Contrast-safe text + matching contour so initials stay legible on any
  // admin-chosen centre colour (Review HIGH: no white-on-yellow).
  const textColor = pickTextColor(centre);
  const contour = textColor === '#FFFFFF' ? 'rgba(0,0,0,0.55)' : 'rgba(255,255,255,0.85)';

  return (
    <span
      title={title}
      aria-label={decorative ? undefined : title}
      aria-hidden={decorative || undefined}
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
        color: textColor,
        WebkitTextStroke: `0.6px ${contour}`,
        // Fallback contour for engines without -webkit-text-stroke.
        textShadow: `0 0 1px ${contour}`,
        userSelect: 'none',
        flexShrink: 0,
      }}
    >
      {initials || '?'}
    </span>
  );
}
