/**
 * Szene „Einstellungen“: Auf dem Bildschirm stehen drei Schalter (zwei an, einer
 * aus). Die Praxisleitung zeigt darauf, eine Kollegin schaut zu.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 250;

const SWITCHES: { label: string; on: boolean }[] = [
  { label: 'Willkommens-Tour', on: true },
  { label: 'Genehmigung', on: false },
  { label: 'Pausenausnahme', on: true },
];

/** Bildschirminhalt: drei Schalter mit Beschriftung. */
function SwitchesContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Einstellungen
      </text>
      {SWITCHES.map((s, i) => {
        const y = 34 + i * 30;
        return (
          <g key={s.label}>
            <text x={10} y={y + 15} fontSize={12} fontWeight={600} fill={O}>
              {s.label}
            </text>
            <rect x={w - 52} y={y + 2} width={40} height={20} rx={10} fill={s.on ? PALETTE.greenDark : '#D9DDE2'} stroke={O} strokeWidth={2} />
            <circle cx={s.on ? w - 22 : w - 42} cy={y + 12} r={7} fill={PALETTE.white} stroke={O} strokeWidth={2} />
          </g>
        );
      })}
    </g>
  );
}

export function SceneEinstellungen({ className }: { className?: string }) {
  const monX = 150;
  const monY = 100;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Einstellungen: Auf dem Bildschirm stehen drei Schalter, zwei sind an, einer ist aus. Die Praxisleitung zeigt darauf, eine Kollegin schaut zu."
      className={className}
      background={PALETTE.mint}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.greenLight} />

      <rect x={160} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={380} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <SwitchesContent />
      </Screen>
      <rect x={144} y={deskTop} width={256} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Person x={88} y={FLOOR} scale={1.15} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={20} y={20} text={'Gilt für die\nganze Praxis.'} tail="left" fontSize={15} />

      <Person x={540} y={FLOOR} scale={1.1} {...CAST.dana} pose="stand" facing="left" />
      <Sparkle x={430} y={96} size={11} />

      <Plant x={440} y={FLOOR} scale={0.75} />
    </ComicSvg>
  );
}
