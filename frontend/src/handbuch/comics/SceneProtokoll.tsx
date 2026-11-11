/**
 * Szene „Änderungsprotokoll“: Auf dem Bildschirm eine Liste von Protokollzeilen,
 * die wie Kettenglieder miteinander verbunden sind, daneben ein Schild mit Haken.
 * Die Praxisleitung zeigt darauf, eine Kollegin hält ein Klemmbrett.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 250;

/** Bildschirminhalt: vier Zeilen, links ein Glied der Kette. */
function LogContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueDark} />
      <text x={10} y={16} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Änderungsprotokoll
      </text>
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <rect x={8} y={32 + i * 26} width={w - 16} height={20} rx={4} fill={PALETTE.blueLight} />
          <rect x={14} y={38 + i * 26} width={34} height={8} rx={3} fill={PALETTE.white} />
          <rect x={56} y={38 + i * 26} width={60} height={8} rx={3} fill={PALETTE.white} />
          <rect x={124} y={38 + i * 26} width={w - 146} height={8} rx={3} fill={PALETTE.white} />
          <circle cx={w - 16} cy={42 + i * 26} r={3.5} fill={PALETTE.greenDark} />
        </g>
      ))}
    </g>
  );
}

export function SceneProtokoll({ className }: { className?: string }) {
  const monX = 250;
  const monY = 96;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Änderungsprotokoll: Auf dem Bildschirm steht eine Liste von Protokollzeilen mit grünen Punkten, daneben ein Schild mit Haken. Die Praxisleitung zeigt auf den Bildschirm, eine Kollegin hält ein Klemmbrett."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      <rect x={262} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={470} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <LogContent />
      </Screen>
      <rect x={246} y={deskTop} width={266} height={12} rx={6} fill="#FCE9C2" {...ln} />

      {/* Schild mit Haken */}
      <g transform="translate(150,150)">
        <path d="M0,0 L40,0 L40,40 Q40,66 20,76 Q0,66 0,40 Z" fill={PALETTE.green} {...ln} />
        <path d="M10,36 L18,46 L32,26" fill="none" {...ln} strokeWidth={4} />
      </g>

      <Person x={72} y={FLOOR} scale={1.15} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Wer hat wann\nwas geändert?'} tail="left" fontSize={15} />

      <Person x={570} y={FLOOR} scale={1.1} {...CAST.dana} pose="stand" facing="left" prop="clipboard" />
      <Plant x={525} y={FLOOR} scale={0.7} />
    </ComicSvg>
  );
}
