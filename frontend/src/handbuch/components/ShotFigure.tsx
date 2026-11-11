import { markerBadgePosition, paddedMarkerBox } from '../geometry';
import type { ManifestShot, ShotDef } from '../types';

export interface ShotFigureProps {
  shotId: string;
  def: ShotDef;
  m: ManifestShot;
  imgBase: string;
  active?: number | null;
}

/** Markergroesse ist auf diese Breite (CSS px) bezogen und skaliert mit dem Ausschnitt. */
export const MARKER_REF_WIDTH = 700;

export default function ShotFigure({ shotId, def, m, imgBase, active = null }: ShotFigureProps) {
  const src = `${imgBase}/${m.file}`;
  const { x, y, w, h } = m.crop;
  const k = w / MARKER_REF_WIDTH;
  return (
    <a
      href={src}
      target="_blank"
      rel="noopener"
      className="block overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
      data-shot={shotId}
    >
      <svg
        viewBox={`${x} ${y} ${w} ${h}`}
        role="img"
        aria-label={def.alt}
        className="block h-auto w-full"
      >
        {/* SVG-<image> kennt kein loading="lazy" (ein Kapitel zog ~9 MB auf einmal): <img> in einem
            foreignObject laedt nativ erst in Sichtweite, auch im vorab gerenderten HTML ohne JS. */}
        <foreignObject x={0} y={0} width={m.width} height={m.height}>
          <img
            src={src}
            alt=""
            width={m.width}
            height={m.height}
            loading="lazy"
            decoding="async"
            className="block h-auto max-w-none"
          />
        </foreignObject>
        {def.markers.map((mk) => {
          const box = m.markers[mk.id];
          if (!box) return null;
          const r = paddedMarkerBox(box, k, m.crop); // R20
          const state = active == null ? '' : active === mk.n ? ' hb-act' : ' hb-dim';
          const radius = 17 * k;
          const { cx, cy } = markerBadgePosition(r, radius, m.crop, mk.badge);
          return (
            <g key={mk.id} data-marker={mk.n} className={`hb-g${state}`}>
              <rect className="hb-hl" x={r.x} y={r.y} width={r.w} height={r.h} rx={10 * k} strokeWidth={(active === mk.n ? 5 : 3) * k} />
              <g className="hb-mk">
                <circle cx={cx} cy={cy} r={radius} strokeWidth={4 * k} />
                <text x={cx} y={cy} fontSize={22 * k}>{mk.n}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </a>
  );
}
