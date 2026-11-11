import { C, DiagramSvg, fmt } from './common';
import { MONTHS } from './values';

const ALT =
  'Balkendiagramm mit Monatssalden von Januar bis April: plus 1,5, minus 8, plus 6 und plus 2,5 Stunden. ' +
  'Darunter das kumulierte Überstundenkonto: plus 1,5, minus 6,5, minus 0,5 und plus 2 Stunden.';

const PX = 9; // Pixel je Stunde
const CX = [90, 230, 370, 510];

function Panel({ title, y0, values, color }: { title: string; y0: number; values: number[]; color: string }) {
  const zero = y0 + 28 + 6 * PX + 26; // Platz für Titel + Wertlabels oben
  return (
    <g>
      <text x={20} y={y0 + 18} fontSize={18} fontWeight={700} fill={C.text}>{title}</text>
      <line x1={20} x2={580} y1={zero} y2={zero} stroke={C.muted} strokeWidth={1.5} />
      {values.map((v, i) => {
        const h = Math.abs(v) * PX;
        const top = v >= 0 ? zero - h : zero;
        const fill = v >= 0 ? color : C.red;
        return (
          <g key={MONTHS[i].name}>
            <rect x={CX[i] - 28} y={top} width={56} height={h} rx={3} fill={fill} />
            <text
              x={CX[i]} y={v >= 0 ? top - 6 : top + h + 18} fontSize={17} fontWeight={700} textAnchor="middle" fill={C.text}
            >
              {fmt(v, 2, true)}
            </text>
            <text x={CX[i]} y={zero + 8 * PX + 42} fontSize={17} textAnchor="middle" fill={C.muted}>{MONTHS[i].name}</text>
          </g>
        );
      })}
    </g>
  );
}

export function MonthBalanceBars() {
  return (
    <DiagramSvg w={600} h={462} label={ALT}>
      <Panel title="Monatssaldo (Ist − Soll, in h)" y0={0} values={MONTHS.map((x) => x.saldo)} color={C.green} />
      <Panel title="Überstundenkonto (Summe der Monate, in h)" y0={232} values={MONTHS.map((x) => x.konto)} color={C.blue} />
    </DiagramSvg>
  );
}
