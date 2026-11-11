/**
 * Szene „Datensicherung“: Eine Datenbank (Zylinder) schickt per Pfeil eine
 * Sicherung auf einen USB-Stick mit Schloss; daneben ein Kalender mit Uhr für die
 * tägliche Sicherung. Die Praxisleitung zeigt den Daumen nach oben.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Sparkle } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;

export function SceneDatensicherung({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Datensicherung: Eine Datenbank schickt per Pfeil eine Sicherung auf einen USB-Stick mit Schloss, daneben ein Kalender mit Uhr für die tägliche Sicherung. Die Praxisleitung zeigt den Daumen nach oben."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      {/* Datenbank */}
      <g transform="translate(190,170)">
        <path d="M0,16 L0,86 Q0,104 40,104 Q80,104 80,86 L80,16 Z" fill={PALETTE.blue} {...ln} />
        <ellipse cx={40} cy={16} rx={40} ry={16} fill={PALETTE.blueLight} {...ln} />
        <path d="M0,46 Q40,64 80,46" fill="none" {...ln} />
        <path d="M0,74 Q40,92 80,74" fill="none" {...ln} />
      </g>

      {/* Pfeil */}
      <path d="M290,220 L350,220" fill="none" {...ln} strokeWidth={4} />
      <path d="M338,208 L352,220 L338,232" fill="none" {...ln} strokeWidth={4} />

      {/* USB-Stick mit Schloss */}
      <g transform="translate(368,196)">
        <rect x={0} y={0} width={100} height={46} rx={8} fill={PALETTE.green} {...ln} />
        <rect x={100} y={11} width={26} height={24} rx={3} fill={PALETTE.white} {...ln} />
        <rect x={34} y={18} width={22} height={18} rx={3} fill={PALETTE.sun} {...ln} strokeWidth={2.5} />
        <path d="M38,18 V13 Q38,6 45,6 Q52,6 52,13 V18" fill="none" {...ln} strokeWidth={2.5} />
      </g>

      {/* Kalender mit Uhr */}
      <g transform="translate(300,70)">
        <rect x={0} y={0} width={90} height={74} rx={8} fill={PALETTE.white} {...ln} />
        <rect x={0} y={0} width={90} height={20} rx={8} fill={PALETTE.coral} {...ln} />
        {[0, 1, 2].map((r) =>
          [0, 1, 2, 3].map((c) => (
            <rect key={`${r}-${c}`} x={10 + c * 19} y={28 + r * 14} width={12} height={8} rx={2} fill={PALETTE.blueLight} />
          )),
        )}
        <circle cx={80} cy={64} r={18} fill={PALETTE.sun} {...ln} />
        <path d="M80,64 V53 M80,64 L88,68" fill="none" {...ln} strokeWidth={2.5} />
      </g>

      <Sparkle x={500} y={170} size={14} />
      <Person x={90} y={FLOOR} scale={1.15} {...CAST.chris} pose="thumbsUp" facing="right" />
      <Bubble x={18} y={20} text={'Täglich sichern,\nKopie außer Haus.'} tail="left" fontSize={15} />

      <Person x={570} y={FLOOR} scale={1.1} {...CAST.bea} pose="stand" facing="left" prop="mug" />
      <Plant x={520} y={FLOOR} scale={0.7} />
    </ComicSvg>
  );
}
