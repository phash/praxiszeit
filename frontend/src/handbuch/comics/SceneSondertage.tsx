/**
 * Szene „Sondertage“: An der Wand hängt der Dezember-Kalender. Der 24.12. ist
 * halb gelb (halber Tag), der 31.12. grau (frei). Die Praxisleitung zeigt darauf,
 * eine Kollegin mit Tasse freut sich.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const CAL_X = 210;
const CAL_Y = 92;
const CELL = 30;
const COLS = 7;
/** 01.12.2026 ist ein Dienstag: eine leere Zelle vorweg (Wochenbeginn Montag). */
const OFFSET = 1;

function Calendar() {
  const w = COLS * CELL + 20;
  const days = Array.from({ length: 31 }, (_, i) => i + 1);
  return (
    <g transform={`translate(${CAL_X},${CAL_Y})`}>
      <rect x={0} y={0} width={w} height={34 + 5 * CELL + 14} rx={10} fill={PALETTE.white} {...ln} />
      <rect x={0} y={0} width={w} height={30} rx={10} fill={PALETTE.coral} {...ln} />
      <text x={w / 2} y={21} fontSize={15} fontWeight={700} fill={O} textAnchor="middle">
        Dezember
      </text>
      {days.map((d) => {
        const idx = d - 1 + OFFSET;
        const col = idx % COLS;
        const row = Math.floor(idx / COLS);
        const x = 10 + col * CELL;
        const y = 38 + row * CELL;
        const weekend = col >= 5;
        let fill: string = weekend ? PALETTE.lilac : PALETTE.white;
        if (d === 25 || d === 26) fill = '#D9DDE2';
        if (d === 31) fill = '#D9DDE2';
        return (
          <g key={d}>
            <rect x={x + 2} y={y + 2} width={CELL - 4} height={CELL - 4} rx={5} fill={fill} stroke={O} strokeWidth={1.5} />
            {d === 24 && (
              <path d={`M${x + 2},${y + CELL - 2} L${x + CELL - 2},${y + 2} L${x + CELL - 2},${y + CELL - 7} Q${x + CELL - 2},${y + CELL - 2} ${x + CELL - 7},${y + CELL - 2} Z`} fill={PALETTE.sun} />
            )}
            <text x={x + CELL / 2} y={y + CELL / 2 + 5} fontSize={12} fontWeight={d === 24 || d === 31 ? 700 : 400} fill={O} textAnchor="middle">
              {d}
            </text>
            {(d === 24 || d === 31) && (
              <rect x={x} y={y} width={CELL} height={CELL} rx={7} fill="none" stroke={PALETTE.coral} strokeWidth={3} />
            )}
          </g>
        );
      })}
    </g>
  );
}

export function SceneSondertage({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Sondertage: Am Dezember-Kalender ist der 24.12. halb gelb markiert (halber Tag) und der 31.12. grau (frei). Die Praxisleitung zeigt darauf, eine Kollegin mit Tasse freut sich."
      className={className}
      background={PALETTE.cream}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.greenLight} />
      <Calendar />
      <Plant x={470} y={FLOOR} scale={0.9} />

      <Person x={110} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Heiligabend halber Tag,\nSilvester frei.'} tail="left" fontSize={15} />

      <Person x={560} y={FLOOR} scale={1.1} {...CAST.bea} pose="stand" facing="left" prop="mug" />
      <Bubble x={500} y={70} text="Prima!" tail="right" fontSize={16} />
    </ComicSvg>
  );
}
