/**
 * Szene „Nachweise & Sicherheit“ für die Broschüre.
 *
 * Links steht der Praxis-Rechner mit PraxisZeit (Monatsreport mit den Export-Knöpfen
 * Excel / ODS / PDF) und daneben der eigene Server mit Schloss-Schild – die Daten
 * bleiben in der Praxis. In der Mitte reicht eine MFA den ausgedruckten Monatsreport
 * weiter, rechts freut sich die Kollegin; an der Wand hängen die Karte „Datensicherung“
 * und die Tafel „ArbZG-Hinweise“ (§ 3 / § 4 / § 5, mit Lupe statt Haken: PraxisZeit
 * gibt Hinweise, es garantiert keine Einhaltung).
 */
import { CAST, ComicSvg, PALETTE, Person, Screen, UiCard, Bubble, Sparkle, Plant, screenInner } from './ComicKit';

const O = PALETTE.outline;
const line = {
  stroke: O,
  strokeWidth: 3,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const FLOOR = 318;

/** Grüner Haken im Kreis (wie im UiCard der Kit). */
function Check({ x, y, r = 8 }: { x: number; y: number; r?: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={r} fill={PALETTE.green} {...line} strokeWidth={2.2} />
      <path
        d={`M${-r * 0.44},0 L${-r * 0.12},${r * 0.35} L${r * 0.5},${-r * 0.38}`}
        fill="none"
        {...line}
        strokeWidth={2.2}
      />
    </g>
  );
}

/** Lupe im Kreis: „hier schaut PraxisZeit hin“ — bewusst kein Haken (keine Zusage „erfüllt“). */
function Magnifier({ x, y, r = 9 }: { x: number; y: number; r?: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={r} fill={PALETTE.white} {...line} strokeWidth={2.2} />
      <circle cx={-1.5} cy={-1.5} r={r * 0.42} fill={PALETTE.blueLight} {...line} strokeWidth={2} />
      <path d={`M${r * 0.18},${r * 0.18} L${r * 0.52},${r * 0.52}`} fill="none" {...line} strokeWidth={2.6} />
    </g>
  );
}

/** Kleiner Export-Knopf auf dem Bildschirm. */
function ExportButton({ x, y, w, label, fill }: { x: number; y: number; w: number; label: string; fill: string }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={30} rx={9} fill={fill} {...line} strokeWidth={2} />
      <text x={w / 2} y={20} textAnchor="middle" fontSize={13} fontWeight={700} fill={O}>
        {label}
      </text>
    </g>
  );
}

/** Server-Gehäuse mit Schild und Schloss: „läuft auf dem eigenen Rechner“. */
function ServerBox({ x, y }: { x: number; y: number }) {
  const w = 62;
  const h = FLOOR - y;
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={10} fill={PALETTE.blueLight} {...line} />
      {/* Laufwerksschächte */}
      <rect x={10} y={12} width={w - 20} height={9} rx={4} fill={PALETTE.white} {...line} strokeWidth={2} />
      <rect x={10} y={27} width={w - 20} height={9} rx={4} fill={PALETTE.white} {...line} strokeWidth={2} />
      <circle cx={w - 16} cy={16.5} r={2.4} fill={PALETTE.greenDark} />
      <circle cx={w - 16} cy={31.5} r={2.4} fill={PALETTE.greenDark} />
      {/* Schild mit Schloss */}
      <g transform={`translate(${w / 2},${h - 34})`}>
        <path
          d="M0,-24 C8,-19 15,-18 20,-18 C20,-2 14,10 0,17 C-14,10 -20,-2 -20,-18 C-15,-18 -8,-19 0,-24 Z"
          fill={PALETTE.green}
          {...line}
        />
        <path d="M-5.5,-4 v-4 a5.5,5.5 0 0 1 11,0 v4" fill="none" {...line} strokeWidth={2.4} />
        <rect x={-8} y={-4} width={16} height={12} rx={3} fill={PALETTE.sun} {...line} strokeWidth={2.4} />
        <circle cx={0} cy={1.5} r={1.6} fill={O} />
      </g>
    </g>
  );
}

/** Ausgedruckter Monatsreport, den die MFA weiterreicht. */
function ReportSheet({ x, y }: { x: number; y: number }) {
  const w = 84;
  const h = 98;
  const rows = [0, 1, 2, 3];
  return (
    <g transform={`translate(${x},${y}) rotate(-6)`}>
      <rect x={0} y={0} width={w} height={h} rx={6} fill={PALETTE.white} {...line} />
      <path d={`M${w - 18},0 L${w},18`} fill="none" {...line} strokeWidth={2} opacity={0.35} />
      <rect x={8} y={10} width={w * 0.55} height={8} rx={4} fill={PALETTE.blueDark} />
      <rect x={8} y={22} width={w - 16} height={7} rx={2} fill={PALETTE.blue} />
      {rows.map((i) => (
        <g key={i}>
          <rect x={8} y={34 + i * 11} width={26} height={5} rx={2.5} fill={PALETTE.lilacDark} opacity={0.8} />
          <rect x={38} y={34 + i * 11} width={16} height={5} rx={2.5} fill={PALETTE.greenDark} opacity={0.8} />
          <rect x={58} y={34 + i * 11} width={18} height={5} rx={2.5} fill={PALETTE.blueDark} opacity={0.8} />
        </g>
      ))}
      <Check x={w - 16} y={h - 13} r={7} />
    </g>
  );
}

/** Wandtafel: zu diesen ArbZG-Punkten gibt PraxisZeit Hinweise (Lupe statt Haken). */
function ArbzgBoard({ x, y }: { x: number; y: number }) {
  const w = 182;
  const items = ['§ 3 Arbeitszeit', '§ 4 Pause', '§ 5 Ruhezeit'];
  const h = 42 + items.length * 28;
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={14} fill={PALETTE.mint} {...line} />
      <text x={14} y={27} fontSize={16} fontWeight={700} fill={O}>
        ArbZG-Hinweise
      </text>
      {items.map((label, i) => (
        <g key={label}>
          <Magnifier x={24} y={50 + i * 28} />
          <text x={40} y={55.5 + i * 28} fontSize={15} fontWeight={600} fill={O}>
            {label}
          </text>
        </g>
      ))}
    </g>
  );
}

export interface SceneNachweiseProps {
  className?: string;
  /** Schrift für die Beschriftungen (Standard: geerbt). */
  fontFamily?: string;
}

export function SceneNachweise({ className, fontFamily }: SceneNachweiseProps) {
  const monX = 104;
  const monY = 92;
  const monW = 176;
  const inner = screenInner('monitor', monW);
  const deskTop = monY + Math.round(monW * 0.62) + 28; // Fuß des Monitors steht auf der Tischplatte
  const btnW = (inner.w - 4 * 2 - 2 * 4) / 3;

  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Nachweise und Sicherheit: Eine Mitarbeiterin reicht den ausgedruckten Monatsreport weiter. Daneben stehen der Praxis-Rechner mit den Exporten als Excel, ODS oder PDF und der eigene Server mit Schloss – die Daten bleiben in der Praxis. An der Wand: die Punkte des Arbeitszeitgesetzes, zu denen PraxisZeit Hinweise gibt."
      className={className}
      background={PALETTE.cream}
      fontFamily={fontFamily}
    >
      {/* Wand + Boden */}
      <rect x={16} y={16} width={608} height={FLOOR - 16} rx={18} fill={PALETTE.sky} />
      <rect x={16} y={FLOOR - 2} width={608} height={380 - FLOOR - 14} rx={14} fill={PALETTE.mint} />
      <path d={`M24,${FLOOR} L616,${FLOOR}`} {...line} strokeWidth={2.5} opacity={0.25} />

      {/* Wandtafel ArbZG */}
      <ArbzgBoard x={436} y={30} />
      <Sparkle x={418} y={58} size={11} />

      {/* Wandkarte Datensicherung über dem Server */}
      <g transform="translate(30,30)">
        <rect x={0} y={0} width={198} height={46} rx={12} fill={PALETTE.lilac} {...line} />
        <text x={12} y={29.5} fontSize={17} fontWeight={700} fill={O}>
          Datensicherung
        </text>
        <Check x={180} y={23} r={9} />
      </g>

      {/* Server mit Schloss */}
      <ServerBox x={30} y={194} />

      {/* Schreibtisch mit Monitor */}
      <rect x={110} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...line} />
      <rect x={262} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...line} />
      <Screen kind="monitor" x={monX} y={monY} width={monW}>
        <UiCard x={4} y={6} w={inner.w - 8} h={44} tint="sky" variant="rows" count={2} outline={false} />
        <ExportButton x={4} y={56} w={btnW} label="Excel" fill={PALETTE.green} />
        <ExportButton x={4 + btnW + 4} y={56} w={btnW} label="ODS" fill={PALETTE.blue} />
        <ExportButton x={4 + 2 * (btnW + 4)} y={56} w={btnW} label="PDF" fill={PALETTE.coral} />
      </Screen>
      <rect x={100} y={deskTop} width={184} height={12} rx={6} fill="#FCE9C2" {...line} />

      {/* MFA reicht den Monatsreport weiter */}
      <Person
        x={350}
        y={FLOOR}
        {...CAST.anna}
        pose="point"
        facing="right"
      />
      <ReportSheet x={392} y={226} />
      <Bubble x={296} y={140} text="Bitte schön!" tail="left" fontSize={14} />

      {/* Kollegin freut sich */}
      <Person
        x={530}
        y={FLOOR}
        {...CAST.bea}
        pose="thumbsUp"
        facing="left"
      />

      <Plant x={598} y={FLOOR} scale={0.8} />
      <Sparkle x={486} y={196} size={9} color={PALETTE.blue} />
    </ComicSvg>
  );
}
