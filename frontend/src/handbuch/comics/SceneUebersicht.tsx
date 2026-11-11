/**
 * Szene „Übersichten“: Praxisleitung am Schreibtisch, auf dem Monitor das
 * Dashboard (Saldo, Urlaub, „Arbeitszeiten im Team“); eine Kollegin zeigt
 * darauf, ein Kollege hebt den Daumen.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, UiCard, screenInner } from './ComicKit';

const O = PALETTE.outline;
const line = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const W = 720;
const H = 420;
const FLOOR = 386;
const DESK_TOP = 312;
const MON_W = 300;
const MON_X = 172;

/** Mini-Version der Teamübersicht: je Zeile Arbeitszeit-Blöcke als Balken. */
function TeamTimeline({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  const pad = 10;
  const titleH = 16;
  const rowsTop = pad + titleH + 8;
  const rowH = (h - rowsTop - pad) / 3;
  const left = pad + 16;
  const span = w - left - pad;
  // Blöcke als Anteil der Zeitachse [start, ende]
  const rows: { color: string; blocks: [number, number][] }[] = [
    { color: PALETTE.blueDark, blocks: [[0.05, 0.45], [0.62, 0.92]] },
    { color: PALETTE.greenDark, blocks: [[0.12, 0.58]] },
    { color: PALETTE.lilacDark, blocks: [[0.3, 0.55], [0.65, 0.98]] },
  ];
  const dots = [PALETTE.blue, PALETTE.green, PALETTE.lilac];
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={12} fill={PALETTE.sky} {...line} />
      <text x={pad} y={pad + titleH * 0.8} fontSize={14} fontWeight={700} fill={O}>
        Arbeitszeiten im Team
      </text>
      {rows.map((r, i) => {
        const cy = rowsTop + rowH * i + rowH / 2;
        return (
          <g key={i}>
            <circle cx={pad + 5} cy={cy} r={5.5} fill={dots[i]} stroke={O} strokeWidth={1.6} />
            <rect x={left} y={cy - 5} width={span} height={10} rx={5} fill={PALETTE.white} />
            {r.blocks.map(([a, b]) => (
              <rect key={a} x={left + span * a} y={cy - 5} width={span * (b - a)} height={10} rx={5} fill={r.color} />
            ))}
          </g>
        );
      })}
    </g>
  );
}

function Desk() {
  return (
    <g>
      {/* Beine */}
      <rect x={224} y={DESK_TOP + 6} width={14} height={FLOOR - DESK_TOP - 6} rx={5} fill={PALETTE.lilacDark} {...line} />
      <rect x={462} y={DESK_TOP + 6} width={14} height={FLOOR - DESK_TOP - 6} rx={5} fill={PALETTE.lilacDark} {...line} />
      {/* Platte */}
      <rect x={128} y={DESK_TOP} width={366} height={16} rx={8} fill={PALETTE.cream} {...line} />
    </g>
  );
}

export function SceneUebersicht({ className }: { className?: string }) {
  const inner = screenInner('monitor', MON_W);
  const monH = Math.round(MON_W * 0.62);
  const monY = DESK_TOP - 28 - monH;
  const gap = 8;
  const cardW = (inner.w - 3 * gap) / 2;
  const cardH = 68;
  return (
    <ComicSvg
      viewBox={`0 0 ${W} ${H}`}
      title="Übersichten in PraxisZeit: Am Schreibtisch zeigt PraxisZeit Saldo, Urlaub und die Übersicht „Arbeitszeiten im Team“; eine Kollegin zeigt darauf, eine weitere Kollegin hebt den Daumen."
      className={className}
      background={PALETTE.cream}
    >
      {/* Boden und Wanddekor */}
      <path d={`M0,${FLOOR - 4} H${W} V${H - 24} Q${W},${H} ${W - 24},${H} H24 Q0,${H} 0,${H - 24} Z`} fill={PALETTE.mint} />
      <line x1={18} y1={FLOOR - 4} x2={W - 18} y2={FLOOR - 4} {...line} opacity={0.25} />
      <g transform="translate(46,40)">
        <rect x={0} y={0} width={70} height={84} rx={10} fill={PALETTE.sky} {...line} />
        <path d="M35,0 V84 M0,42 H70" fill="none" {...line} strokeWidth={2.4} />
      </g>
      <Plant x={36} y={FLOOR} scale={0.75} />

      <Desk />
      <Screen kind="monitor" x={MON_X} y={monY} width={MON_W}>
        <UiCard x={gap} y={gap} w={cardW} h={cardH} title="Saldo" tint="green" variant="chart" count={5} check />
        <UiCard x={gap * 2 + cardW} y={gap} w={cardW} h={cardH} title="Urlaub" tint="cream" variant="bars" count={2} />
        <TeamTimeline x={gap} y={gap * 2 + cardH} w={inner.w - 2 * gap} h={inner.h - cardH - 3 * gap} />
      </Screen>
      {/* Tasse auf dem Tisch */}
      <g transform={`translate(404,${DESK_TOP - 10})`}>
        <path d="M8,-6 Q15,-6 15,0 Q15,6 8,6" fill="none" {...line} />
        <rect x={-9} y={-10} width={18} height={18} rx={4} fill={PALETTE.white} {...line} />
      </g>

      {/* Praxisleitung am Schreibtisch */}
      <Person x={122} y={FLOOR} scale={1.55} shirt="green" hair="bob" hairColor={PALETTE.hair.lightGrey} skin={PALETTE.skin.olive} pose="sit" />
      {/* Kollegin zeigt auf den Monitor */}
      <Person {...CAST.anna} x={548} y={FLOOR} scale={1.45} pose="point" facing="left" />
      {/* Kollegin mit Daumen hoch */}
      <Person {...CAST.bea} x={664} y={FLOOR} scale={1.3} pose="thumbsUp" facing="left" />

      <Bubble x={520} y={28} text={'Alles auf\neinen Blick!'} tail="left" fontSize={18} />
      <Sparkle x={492} y={86} size={11} />
      <Sparkle x={134} y={70} size={8} color={PALETTE.blue} />
    </ComicSvg>
  );
}
