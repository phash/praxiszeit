import { C, DiagramSvg, Swatch } from './common';
import { BLOCKS, ENTRY_A, ENTRY_B, GRACE } from './values';

const X0 = 28;
const PER_MIN = 544 / 600; // 07:00–17:00
const x = (min: number) => X0 + (min - 7 * 60) * PER_MIN;
const m = (h: number, mi = 0) => h * 60 + mi;

const ALT =
  'Zeitstrahl eines Arbeitstags mit Arbeitszeit-Blöcken 08 bis 12 und 15 bis 16 Uhr, Hülle von 07:45 bis 16:15 Uhr und zwei Zeiteinträgen. ' +
  'Der erste Eintrag 07:30 bis 12:10 wird ab 07:45 angerechnet, 15 Minuten nicht. Der zweite Eintrag 13:00 bis 16:30 verliert 105 Minuten in der Lücke und 15 Minuten nach der Hülle.';

function Seg({ a, b, y, fill }: { a: number; b: number; y: number; fill: string }) {
  return <rect x={x(a)} y={y} width={x(b) - x(a)} height={30} fill={fill} />;
}

export function DayTimeline() {
  const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16];
  const hullA = BLOCKS[0].start - GRACE;
  const hullB = BLOCKS[1].end + GRACE;
  return (
    <DiagramSvg w={600} h={372} label={ALT}>
      {hours.map((h) => (
        <g key={h}>
          <line x1={x(m(h))} x2={x(m(h))} y1={30} y2={294} stroke={C.line} strokeWidth={1} />
          <text x={x(m(h))} y={22} fontSize={17} textAnchor="middle" fill={C.muted}>{String(h).padStart(2, '0')}</text>
        </g>
      ))}

      <text x={X0} y={56} fontSize={18} fontWeight={700} fill={C.text}>Arbeitszeit-Blöcke (Vertrag)</text>
      <rect x={x(m(12, 15))} y={64} width={x(m(14, 45)) - x(m(12, 15))} height={30} fill={C.amberSoft} />
      <text x={(x(m(12, 15)) + x(m(14, 45))) / 2} y={85} fontSize={17} textAnchor="middle" fill={C.amber}>Lücke</text>
      {BLOCKS.map((b) => (
        <rect key={b.start} x={x(b.start)} y={64} width={x(b.end) - x(b.start)} height={30} rx={4} fill={C.blue} />
      ))}
      <rect x={x(hullA)} y={60} width={x(hullB) - x(hullA)} height={38} rx={6} fill="none" stroke={C.blue} strokeWidth={2} strokeDasharray="6 4" />
      <text x={x(hullA)} y={116} fontSize={17} fill={C.blue}>Hülle 07:45–16:15 (Block ± 15 min)</text>

      <text x={X0} y={152} fontSize={18} fontWeight={700} fill={C.text}>Zeiteintrag 1 · gestempelt {ENTRY_A.stamp}</text>
      <Seg a={m(7, 30)} b={m(7, 45)} y={160} fill={C.red} />
      <Seg a={m(7, 45)} b={m(12, 10)} y={160} fill={C.green} />
      <text x={X0} y={208} fontSize={17} fill={C.text}>
        angerechnet {ENTRY_A.credited} h · nicht angerechnet {ENTRY_A.notCreditedMin} min
      </text>

      <text x={X0} y={246} fontSize={18} fontWeight={700} fill={C.text}>Zeiteintrag 2 · gestempelt {ENTRY_B.stamp}</text>
      <Seg a={m(13)} b={m(14, 45)} y={254} fill={C.red} />
      <Seg a={m(14, 45)} b={m(16, 15)} y={254} fill={C.green} />
      <Seg a={m(16, 15)} b={m(16, 30)} y={254} fill={C.red} />
      <text x={X0} y={302} fontSize={17} fill={C.text}>
        angerechnet {ENTRY_B.credited} h · nicht angerechnet {ENTRY_B.notCreditedMin} min
      </text>

      <Swatch x={X0} y={340} color={C.green} />
      <text x={X0 + 24} y={340} fontSize={17} fill={C.text}>angerechnet</text>
      <Swatch x={X0 + 150} y={340} color={C.red} />
      <text x={X0 + 174} y={340} fontSize={17} fill={C.text}>nicht angerechnet</text>
      <text x={X0} y={364} fontSize={17} fill={C.muted}>Der Beginn in der Lücke wird nicht verschoben.</text>
    </DiagramSvg>
  );
}
