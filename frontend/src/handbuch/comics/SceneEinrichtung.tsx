/**
 * Szene „Erste Einrichtung“: Die Praxisleitung sitzt am Praxis-PC und hakt die
 * ersten Schritte ab – Einstellungen (Bundesland), Team anlegen, Arbeitszeit
 * hinterlegen. Eine Kollegin bringt Kaffee. Wortlaut der Checkliste wie in
 * Kapitel 1 des Handbuchs für die Praxisleitung.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 250;

const ITEMS = ['Einstellungen', 'Team anlegen', 'Arbeitszeit'];

/** Bildschirminhalt: Checkliste mit drei Punkten, zwei davon erledigt. */
function ChecklistContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Erste Schritte
      </text>
      {ITEMS.map((label, i) => {
        const y = 34 + i * 30;
        const done = i < 2;
        return (
          <g key={label}>
            <rect x={10} y={y} width={20} height={20} rx={5} fill={done ? PALETTE.greenLight : PALETTE.white} stroke={done ? PALETTE.greenDark : PALETTE.blueDark} strokeWidth={2} />
            {done && <path d={`M${14},${y + 10} L${19},${y + 15} L${27},${y + 5}`} fill="none" stroke={PALETTE.greenDark} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />}
            <text x={38} y={y + 15} fontSize={12} fontWeight={600} fill={O}>
              {label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export function SceneEinrichtung({ className }: { className?: string }) {
  const monX = 150;
  const monY = 100;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Erste Einrichtung: Die Praxisleitung sitzt am Praxis-PC und hakt die ersten Schritte ab – Einstellungen und Team anlegen sind erledigt, die Arbeitszeit folgt. Eine Kollegin bringt einen Kaffee."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      {/* Schreibtisch mit Monitor */}
      <rect x={160} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={380} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <ChecklistContent />
      </Screen>
      <rect x={144} y={deskTop} width={256} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Person x={88} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={20} y={20} text={'Einmal einrichten –\ndann läuft es.'} tail="left" fontSize={15} />

      <Person x={540} y={FLOOR} scale={1.1} {...CAST.dana} pose="stand" facing="left" prop="mug" />
      <Bubble x={470} y={48} text="Kaffee?" tail="right" fontSize={16} />
      <Sparkle x={430} y={96} size={11} />

      <Plant x={440} y={FLOOR} scale={0.75} />
    </ComicSvg>
  );
}
