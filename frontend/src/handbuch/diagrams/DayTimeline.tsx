import { C, DiagramSvg, Swatch } from './common';
import { BLOCKS, ENTRY_A, ENTRY_B, GAP_SHRUNK, GRACE, HULL, hhmm } from './values';

const X0 = 28;
const PER_MIN = 544 / 600; // 07:00–17:00
const x = (min: number) => X0 + (min - 7 * 60) * PER_MIN;

const ALT =
  'Zeitstrahl eines Arbeitstags mit Arbeitszeit-Blöcken 08 bis 12 und 15 bis 16 Uhr, Hülle von 07:45 bis 16:15 Uhr und zwei Zeiteinträgen. ' +
  'Der erste Eintrag 07:30 bis 12:10 wird ab 07:45 angerechnet, 15 Minuten nicht. Der zweite Eintrag 13:00 bis 16:30 verliert 105 Minuten in der Lücke und 15 Minuten nach der Hülle.';

function Seg({ a, b, y, fill }: { a: number; b: number; y: number; fill: string }) {
  return <rect x={x(a)} y={y} width={x(b) - x(a)} height={30} fill={fill} />;
}

export function DayTimeline() {
  const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16];
    return (
    <DiagramSvg w={600} h={394} label={ALT}>
      {hours.map((h) => (
        <g key={h}>
          <line x1={x(h * 60)} x2={x(h * 60)} y1={30} y2={294} stroke={C.line} strokeWidth={1} />
          <text x={x(h * 60)} y={22} fontSize={17} textAnchor="middle" fill={C.muted}>{String(h).padStart(2, '0')}</text>
        </g>
      ))}

      <text x={X0} y={56} fontSize={18} fontWeight={700} fill={C.text}>Arbeitszeit-Blöcke (Vertrag)</text>
      <rect x={x(GAP_SHRUNK.start)} y={64} width={x(GAP_SHRUNK.end) - x(GAP_SHRUNK.start)} height={30} fill={C.amberSoft} />
      <text x={(x(GAP_SHRUNK.start) + x(GAP_SHRUNK.end)) / 2} y={85} fontSize={17} textAnchor="middle" fill={C.amber}>Lücke</text>
      {BLOCKS.map((b) => (
        <rect key={b.start} x={x(b.start)} y={64} width={x(b.end) - x(b.start)} height={30} rx={4} fill={C.blue} />
      ))}
      <rect x={x(HULL.start)} y={60} width={x(HULL.end) - x(HULL.start)} height={38} rx={6} fill="none" stroke={C.blue} strokeWidth={2} strokeDasharray="6 4" />
      <text x={x(HULL.start)} y={116} fontSize={17} fill={C.blue}>Hülle {hhmm(HULL.start)}–{hhmm(HULL.end)} (Block ± {GRACE} min)</text>

      <text x={X0} y={152} fontSize={18} fontWeight={700} fill={C.text}>Zeiteintrag 1 · gestempelt {ENTRY_A.stamp}</text>
      <Seg a={ENTRY_A.start} b={ENTRY_A.effStart} y={160} fill={C.red} />
      <Seg a={ENTRY_A.effStart} b={ENTRY_A.effEnd} y={160} fill={C.green} />
      <text x={X0} y={208} fontSize={17} fill={C.text}>
        angerechnet {ENTRY_A.credited} h · nicht angerechnet {ENTRY_A.notCreditedMin} min
      </text>

      <text x={X0} y={246} fontSize={18} fontWeight={700} fill={C.text}>Zeiteintrag 2 · gestempelt {ENTRY_B.stamp}</text>
      <Seg a={ENTRY_B.effStart} b={GAP_SHRUNK.end} y={254} fill={C.red} />
      <Seg a={GAP_SHRUNK.end} b={ENTRY_B.effEnd} y={254} fill={C.green} />
      <Seg a={ENTRY_B.effEnd} b={ENTRY_B.end} y={254} fill={C.red} />
      <text x={X0} y={302} fontSize={17} fill={C.text}>
        angerechnet {ENTRY_B.credited} h · nicht angerechnet {ENTRY_B.notCreditedMin} min
      </text>

      <Swatch x={X0} y={340} color={C.green} />
      <text x={X0 + 24} y={340} fontSize={17} fill={C.text}>angerechnet</text>
      <Swatch x={X0 + 150} y={340} color={C.red} />
      <text x={X0 + 174} y={340} fontSize={17} fill={C.text}>nicht angerechnet</text>
      <text x={X0} y={364} fontSize={17} fill={C.muted}>Lücke = Pause abzüglich Puffer an beiden Rändern.</text>
      <text x={X0} y={386} fontSize={17} fill={C.muted}>Der Beginn in der Lücke wird nicht verschoben.</text>
    </DiagramSvg>
  );
}
