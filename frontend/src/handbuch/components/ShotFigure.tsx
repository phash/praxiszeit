import { useEffect, useRef, useState } from 'react';
import { markerBadgePosition, paddedMarkerBox } from '../geometry';
import type { ManifestShot, ShotDef } from '../types';

export interface ShotFigureProps {
  shotId: string;
  def: ShotDef;
  m: ManifestShot;
  imgBase: string;
  active?: number | null;
  /**
   * Bild sofort (auch im vorab gerenderten HTML) statt erst in Sichtweite: Broschüre (wird gedruckt,
   * wenige Bilder) und das erste Bild eines Handbuchs. Alle anderen erscheinen erst, wenn die
   * Abbildung nahe an den Bildschirm kommt (SVG-<image> kennt kein loading="lazy"; ein Kapitel zog
   * sonst ~9 MB auf einmal, und <img loading="lazy"> im foreignObject lädt in Chromium trotzdem sofort).
   */
  eager?: boolean;
}

/** Markergroesse ist auf diese Breite (CSS px) bezogen und skaliert mit dem Ausschnitt. */
export const MARKER_REF_WIDTH = 700;

export default function ShotFigure({ shotId, def, m, imgBase, active = null, eager = false }: ShotFigureProps) {
  const src = `${imgBase}/${m.file}`;
  const ref = useRef<SVGSVGElement>(null);
  // Server-Render und erster Client-Render: nur `eager` zeigt das Bild (pzweb rendert per createRoot,
  // keine Hydration). Ohne IntersectionObserver (alte Browser, jsdom) gleich laden.
  const [show, setShow] = useState(eager);
  useEffect(() => {
    if (show) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShow(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) { setShow(true); io.disconnect(); }
      },
      { rootMargin: '800px 0px' },
    );
    io.observe(el);
    const onPrint = () => setShow(true); // gedruckt wird alles
    window.addEventListener('beforeprint', onPrint);
    return () => { io.disconnect(); window.removeEventListener('beforeprint', onPrint); };
  }, [show]);
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
        ref={ref}
        viewBox={`${x} ${y} ${w} ${h}`}
        role="img"
        aria-label={def.alt}
        className="block h-auto w-full"
      >
        {show && <image href={src} x={0} y={0} width={m.width} height={m.height} />}
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
