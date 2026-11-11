import { C, DiagramSvg, fmt } from './common';
import { DAY_TARGET, HOLIDAYS, IST_HOURS, SALDO_HOURS, SOLL_DAYS, SOLL_HOURS, VACATION_DAYS_TAKEN, WORKDAYS } from './values';

const ALT =
  'Soll und Ist eines Monats im Vergleich: 22 Werktage minus 1 Feiertag minus 4 Urlaubstage ergeben 17 Tage zu je 8 Stunden, also 136 Stunden Soll. ' +
  'Gearbeitet wurden 137,5 Stunden. Der Saldo beträgt plus 1,5 Stunden.';

// Achse beginnt bei 130 h (Unterbrechung ist beschriftet), sonst wäre der Unterschied nicht zu sehen.
const AXIS_FROM = 130;
const AXIS_TO = 140;
const bx = (h: number) => 28 + ((h - AXIS_FROM) / (AXIS_TO - AXIS_FROM)) * 544;

export function SollIstScale() {
  return (
    <DiagramSvg w={600} h={330} label={ALT}>
      <text x={28} y={26} fontSize={18} fontWeight={700} fill={C.text}>Soll: Tage mal Tagessoll</text>
      {[
        { t: `${WORKDAYS} Werktage`, w: 150, fill: C.blueSoft, c: C.text },
        { t: `−${HOLIDAYS} Feiertag`, w: 140, fill: C.amberSoft, c: C.text },
        { t: `−${VACATION_DAYS_TAKEN} Urlaub`, w: 130, fill: C.violetSoft, c: C.text },
      ].map((p, i, a) => {
        const x = 28 + a.slice(0, i).reduce((s, q) => s + q.w + 6, 0);
        return (
          <g key={p.t}>
            <rect x={x} y={38} width={p.w} height={34} rx={6} fill={p.fill} />
            <text x={x + p.w / 2} y={61} fontSize={17} textAnchor="middle" fill={p.c}>{p.t}</text>
          </g>
        );
      })}
      <text x={28} y={104} fontSize={17} fill={C.text}>
        = {SOLL_DAYS} Tage × {fmt(DAY_TARGET)} h = {fmt(SOLL_HOURS)} h Soll
      </text>

      <text x={28} y={150} fontSize={18} fontWeight={700} fill={C.text}>Vergleich (Achse ab 130 h)</text>
      <rect x={28} y={162} width={bx(SOLL_HOURS) - 28} height={34} rx={4} fill={C.blue} />
      <text x={38} y={185} fontSize={17} fill="#FFFFFF" fontWeight={700}>Soll {fmt(SOLL_HOURS)} h</text>
      <rect x={28} y={204} width={bx(IST_HOURS) - 28} height={34} rx={4} fill={C.green} />
      <text x={38} y={227} fontSize={17} fill="#FFFFFF" fontWeight={700}>Ist {fmt(IST_HOURS)} h</text>
      <line x1={bx(SOLL_HOURS)} x2={bx(SOLL_HOURS)} y1={156} y2={244} stroke={C.text} strokeWidth={2} strokeDasharray="4 3" />

      <text x={28} y={272} fontSize={17} fill={C.text}>
        Ist: 14 × {fmt(8)} h + 3 × {fmt(8.5)} h = {fmt(IST_HOURS)} h
      </text>
      <rect x={28} y={286} width={260} height={36} rx={8} fill={C.greenSoft} stroke={C.green} strokeWidth={2} />
      <text x={158} y={310} fontSize={19} fontWeight={700} textAnchor="middle" fill={C.text}>
        Saldo {fmt(SALDO_HOURS, 2, true)} h
      </text>
      <text x={304} y={310} fontSize={17} fill={C.muted}>Ist − Soll</text>
    </DiagramSvg>
  );
}
