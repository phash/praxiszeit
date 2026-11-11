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
        <image href={src} x={0} y={0} width={m.width} height={m.height} />
        {def.markers.map((mk) => {
          const r = m.markers[mk.id];
          if (!r) return null;
          const state = active == null ? '' : active === mk.n ? ' hb-act' : ' hb-dim';
          return (
            <g key={mk.id} data-marker={mk.n} className={`hb-g${state}`}>
              <rect className="hb-hl" x={r.x} y={r.y} width={r.w} height={r.h} rx={10 * k} strokeWidth={(active === mk.n ? 5 : 3) * k} />
              <g className="hb-mk">
                <circle cx={r.x} cy={r.y} r={17 * k} strokeWidth={4 * k} />
                <text x={r.x} y={r.y} fontSize={22 * k}>{mk.n}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </a>
  );
}
