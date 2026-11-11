import type { ManifestShot, ShotDef } from '../types';

export interface ShotFigureProps {
  shotId: string;
  def: ShotDef;
  m: ManifestShot;
  imgBase: string;
  active?: number | null;
}

export default function ShotFigure({ shotId, def, m, imgBase, active = null }: ShotFigureProps) {
  const src = `${imgBase}/${m.file}`;
  const { x, y, w, h } = m.crop;
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
              <rect className="hb-hl" x={r.x} y={r.y} width={r.w} height={r.h} rx={10} />
              <g className="hb-mk">
                <circle cx={r.x} cy={r.y} r={17} />
                <text x={r.x} y={r.y}>{mk.n}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </a>
  );
}
