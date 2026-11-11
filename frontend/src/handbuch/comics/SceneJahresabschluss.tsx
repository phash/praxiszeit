/**
 * Szene „Jahresabschluss“: Zwei Karten, 2026 und 2027, verbunden durch einen
 * Pfeil – darüber „Überstunden + Resturlaub“ wandern ins neue Jahr. Die
 * Praxisleitung hakt ab, eine Kollegin nickt.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Sparkle } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;

function YearCard({ x, year, done }: { x: number; year: string; done: boolean }) {
  return (
    <g transform={`translate(${x},120)`}>
      <rect x={0} y={0} width={120} height={110} rx={12} fill={done ? PALETTE.greenLight : PALETTE.blueLight} {...ln} />
      <rect x={0} y={0} width={120} height={32} rx={12} fill={done ? PALETTE.greenDark : PALETTE.blueDark} {...ln} />
      <text x={60} y={23} fontSize={18} fontWeight={700} fill={PALETTE.white} textAnchor="middle">
        {year}
      </text>
      <rect x={14} y={48} width={92} height={10} rx={5} fill={PALETTE.white} />
      <rect x={14} y={68} width={64} height={10} rx={5} fill={PALETTE.white} />
      <rect x={14} y={88} width={80} height={10} rx={5} fill={PALETTE.white} />
      {done && (
        <g transform="translate(100,22)">
          <circle r={12} fill={PALETTE.green} {...ln} strokeWidth={2.2} />
          <path d="M-5,0 L-1.5,4 L6,-5" fill="none" {...ln} strokeWidth={2.6} />
        </g>
      )}
    </g>
  );
}

export function SceneJahresabschluss({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Jahresabschluss: Von einer Karte 2026 führt ein Pfeil zu einer Karte 2027, darüber steht Überstunden und Resturlaub. Die Praxisleitung zeigt darauf, eine Kollegin nickt."
      className={className}
      background={PALETTE.cream}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.greenLight} />

      <YearCard x={190} year="2026" done />
      <YearCard x={370} year="2027" done={false} />
      <path d="M318,175 L360,175" fill="none" {...ln} strokeWidth={4} />
      <path d="M350,163 L362,175 L350,187" fill="none" {...ln} strokeWidth={4} />
      <text x={314} y={108} fontSize={14} fontWeight={700} fill={O} textAnchor="middle">
        Überstunden + Resturlaub
      </text>
      <Sparkle x={500} y={112} size={11} />

      <Person x={88} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={20} y={20} text={'Zum Jahreswechsel:\nÜbertrag prüfen.'} tail="left" fontSize={15} />

      <Person x={560} y={FLOOR} scale={1.1} {...CAST.bea} pose="thumbsUp" facing="left" />
      <Plant x={470} y={FLOOR} scale={0.8} />
    </ComicSvg>
  );
}
