/**
 * Szene „Eigene Abwesenheitsgründe“: Auf dem Bildschirm steht die Liste der
 * Gründe (Schule, Kind krank, Arztbesuch) mit je einem farbigen Punkt. Die
 * Praxisleitung zeigt darauf, eine Kollegin hält ein Klemmbrett.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 250;

const REASONS: { label: string; color: string }[] = [
  { label: 'Schule', color: '#3366cc' },
  { label: 'Kind krank', color: '#e67e22' },
  { label: 'Arztbesuch', color: '#16a085' },
];

/** Bildschirminhalt: drei Gründe mit farbigem Punkt. */
function ReasonsContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Eigene Abwesenheitsgründe
      </text>
      {REASONS.map((r, i) => {
        const y = 34 + i * 30;
        return (
          <g key={r.label}>
            <circle cx={20} cy={y + 10} r={8} fill={r.color} stroke={O} strokeWidth={2} />
            <text x={38} y={y + 15} fontSize={12} fontWeight={600} fill={O}>
              {r.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export function SceneGruende({ className }: { className?: string }) {
  const monX = 150;
  const monY = 100;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Eigene Abwesenheitsgründe: Auf dem Bildschirm stehen die Gründe Schule, Kind krank und Arztbesuch mit je einem farbigen Punkt. Die Praxisleitung zeigt darauf, eine Kollegin hält ein Klemmbrett."
      className={className}
      background={PALETTE.lilac}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      <rect x={160} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={380} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <ReasonsContent />
      </Screen>
      <rect x={144} y={deskTop} width={256} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Person x={88} y={FLOOR} scale={1.15} {...CAST.chris} pose="point" facing="right" />
      <Bubble x={20} y={20} text={'Jeder Grund hat\nsein Verhalten.'} tail="left" fontSize={15} />

      <Person x={540} y={FLOOR} scale={1.1} {...CAST.bea} pose="stand" facing="left" prop="clipboard" />
      <Bubble x={470} y={48} text="Kind krank?" tail="right" fontSize={16} />

      <Plant x={440} y={FLOOR} scale={0.75} />
    </ComicSvg>
  );
}
