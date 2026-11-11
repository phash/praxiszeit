/**
 * Szene „Import“: Eine Tabellendatei (.xls) wandert per Pfeil in eine Vorschau
 * auf dem Bildschirm. Die Praxisleitung prüft, eine Kollegin hält die Tasse.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 230;

/** Bildschirminhalt: Vorschau mit vier Zeilen, eine davon gelb (Hinweis). */
function PreviewContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Vorschau
      </text>
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <rect x={8} y={32 + i * 24} width={w - 16} height={18} rx={4} fill={i === 2 ? PALETTE.sun : PALETTE.greenLight} />
          <rect x={14} y={38 + i * 24} width={36} height={6} rx={3} fill={PALETTE.white} />
          <rect x={60} y={38 + i * 24} width={50} height={6} rx={3} fill={PALETTE.white} />
        </g>
      ))}
    </g>
  );
}

export function SceneImport({ className }: { className?: string }) {
  const monX = 270;
  const monY = 100;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Import: Eine Tabellendatei mit der Endung xls wandert per Pfeil in eine Vorschau auf dem Bildschirm, eine Zeile ist gelb. Die Praxisleitung prüft, eine Kollegin hält eine Tasse."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      <rect x={280} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={480} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <PreviewContent />
      </Screen>
      <rect x={264} y={deskTop} width={246} height={12} rx={6} fill="#FCE9C2" {...ln} />

      {/* Datei */}
      <g transform="translate(150,150)">
        <rect x={0} y={0} width={64} height={80} rx={8} fill={PALETTE.white} {...ln} />
        {[0, 1, 2, 3].map((i) => (
          <rect key={i} x={10} y={22 + i * 14} width={44} height={8} rx={2} fill={PALETTE.greenLight} stroke={O} strokeWidth={1.5} />
        ))}
        <text x={32} y={16} fontSize={12} fontWeight={700} fill={O} textAnchor="middle">
          .xls
        </text>
      </g>
      <path d="M222,190 L262,190" fill="none" {...ln} strokeWidth={4} />
      <path d="M252,178 L264,190 L252,202" fill="none" {...ln} strokeWidth={4} />

      <Person x={72} y={FLOOR} scale={1.15} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Erst Vorschau,\ndann bestätigen.'} tail="left" fontSize={15} />

      <Person x={570} y={FLOOR} scale={1.1} {...CAST.dana} pose="stand" facing="left" prop="mug" />
      <Plant x={520} y={FLOOR} scale={0.7} />
    </ComicSvg>
  );
}
