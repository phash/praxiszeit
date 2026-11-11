/**
 * Szene „Arbeitszeit-Blöcke“: Auf dem Praxis-PC steht eine Woche mit zwei
 * Blöcken je Tag (vormittags und nachmittags) und der Mittagslücke dazwischen.
 * Die Praxisleitung zeigt auf die Lücke, eine Kollegin hält ihr Klemmbrett.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Screen, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 270;
const DAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'];

/** Bildschirminhalt: Wochenraster mit Blöcken (Fr nur vormittags). */
function WeekContent() {
  const { w } = screenInner('monitor', MON_W);
  const left = 30;
  const span = w - left - 10;
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Arbeitszeit-Blöcke
      </text>
      {DAYS.map((d, i) => {
        const y = 30 + i * 22;
        return (
          <g key={d}>
            <text x={8} y={y + 13} fontSize={11} fontWeight={700} fill={O}>
              {d}
            </text>
            <rect x={left} y={y + 2} width={span * 0.45} height={14} rx={4} fill={PALETTE.blue} stroke={PALETTE.blueDark} strokeWidth={1.5} />
            {i < 4 && (
              <rect x={left + span * 0.72} y={y + 2} width={span * 0.22} height={14} rx={4} fill={PALETTE.blue} stroke={PALETTE.blueDark} strokeWidth={1.5} />
            )}
          </g>
        );
      })}
      {/* Mittagslücke hervorgehoben */}
      <rect x={left + span * 0.47} y={28} width={span * 0.23} height={90} rx={6} fill="none" stroke={PALETTE.coral} strokeWidth={2} strokeDasharray="4 4" />
    </g>
  );
}

export function SceneBloecke({ className }: { className?: string }) {
  const monX = 170;
  const monY = 96;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Arbeitszeit-Blöcke: Auf dem Praxis-PC steht eine Woche mit Vormittags- und Nachmittagsblöcken; die Mittagslücke dazwischen ist markiert. Die Praxisleitung zeigt darauf, eine Kollegin hält ihr Klemmbrett."
      className={className}
      background={PALETTE.mint}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.greenLight} />

      <rect x={180} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={420} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <WeekContent />
      </Screen>
      <rect x={164} y={deskTop} width={282} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Person x={96} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Die Mittagslücke\nzählt nicht mit.'} tail="left" fontSize={15} />

      <Person x={550} y={FLOOR} scale={1.1} {...CAST.dana} pose="thumbsUp" facing="left" prop="clipboard" />
      <Bubble x={480} y={44} text="Alles klar!" tail="right" fontSize={16} />
    </ComicSvg>
  );
}
