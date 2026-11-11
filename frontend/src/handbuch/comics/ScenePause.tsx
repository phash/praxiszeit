/**
 * Szene „Pause“: Eine Kollegin sitzt mit Tasse in der Pause, an der Wand
 * zeigt die Uhr halb eins. Die Praxisleitung erinnert an die Pausenregel
 * des § 4 ArbZG.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;

/** Wanduhr: 12:30 Uhr. */
function Clock({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={r} fill={PALETTE.white} {...ln} />
      {Array.from({ length: 12 }, (_, i) => {
        const a = (i * Math.PI) / 6;
        return (
          <line key={i} x1={Math.sin(a) * (r - 8)} y1={-Math.cos(a) * (r - 8)} x2={Math.sin(a) * (r - 3)} y2={-Math.cos(a) * (r - 3)} stroke={O} strokeWidth={2} strokeLinecap="round" />
        );
      })}
      {/* Stundenzeiger zwischen 12 und 1, Minutenzeiger auf der 6 */}
      <line x1={0} y1={0} x2={Math.sin(Math.PI / 12) * r * 0.5} y2={-Math.cos(Math.PI / 12) * r * 0.5} stroke={O} strokeWidth={4} strokeLinecap="round" />
      <line x1={0} y1={0} x2={0} y2={r * 0.72} stroke={O} strokeWidth={3} strokeLinecap="round" />
      <circle r={3.5} fill={O} />
    </g>
  );
}

export function ScenePause({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Pause: Eine Kollegin sitzt mit einer Tasse in der Mittagspause, die Wanduhr zeigt halb eins. Die Praxisleitung erinnert an die Pause nach mehr als sechs Stunden Arbeit."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.greenLight} />
      <Clock x={330} y={110} r={46} />
      <Plant x={250} y={FLOOR} scale={0.85} />

      <Person x={120} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Mehr als 6 Stunden?\nDann 30 Minuten Pause.'} tail="left" fontSize={15} />

      <Person x={500} y={FLOOR} scale={1.1} {...CAST.dana} pose="sit" facing="left" prop="mug" />
      <Bubble x={430} y={96} text="Mach ich!" tail="right" fontSize={16} />
    </ComicSvg>
  );
}
