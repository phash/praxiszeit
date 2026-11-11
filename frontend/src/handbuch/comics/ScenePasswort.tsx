/**
 * Szene „Admin-Passwort verloren“: Die Praxisleitung sitzt am Server, auf dem
 * dunklen Bildschirm steht eine Eingabeaufforderung mit Schlüssel-Symbol. Das
 * Passwort wird nicht angezeigt (Punkte statt Text).
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 250;

/** Bildschirminhalt: Eingabeaufforderung, Passwortzeile mit Punkten. */
function TerminalContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={200} fill="#1F2A36" />
      <rect x={10} y={14} width={40} height={7} rx={3} fill={PALETTE.green} />
      <rect x={56} y={14} width={110} height={7} rx={3} fill={PALETTE.blueLight} />
      <rect x={10} y={36} width={90} height={7} rx={3} fill={PALETTE.blueLight} />
      <text x={10} y={72} fontSize={11} fill={PALETTE.sun} fontFamily="monospace">
        Neues Passwort:
      </text>
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
        <circle key={i} cx={140 + i * 11} cy={69} r={3.5} fill={PALETTE.white} />
      ))}
      <rect x={10} y={90} width={6} height={10} fill={PALETTE.white} />
    </g>
  );
}

export function ScenePasswort({ className }: { className?: string }) {
  const monX = 250;
  const monY = 96;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Admin-Passwort verloren: Die Praxisleitung arbeitet am Server, auf dem dunklen Bildschirm steht eine Eingabeaufforderung mit der Zeile Neues Passwort und Punkten statt Text. Ein Schlüssel liegt auf dem Tisch."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      <rect x={262} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={470} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W} screen="#1F2A36">
        <TerminalContent />
      </Screen>
      <rect x={246} y={deskTop} width={266} height={12} rx={6} fill="#FCE9C2" {...ln} />

      {/* Schlüssel */}
      <g transform="translate(150,170)">
        <circle cx={22} cy={22} r={16} fill={PALETTE.sun} {...ln} />
        <circle cx={22} cy={22} r={5} fill={PALETTE.sky} {...ln} strokeWidth={2} />
        <path d="M38,22 H82 M70,22 V36 M58,22 V32" fill="none" {...ln} />
      </g>

      <Person x={72} y={FLOOR} scale={1.15} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={18} y={20} text={'Am Server,\nnicht im Browser.'} tail="left" fontSize={15} />

      <Person x={570} y={FLOOR} scale={1.1} {...CAST.dana} pose="stand" facing="left" prop="mug" />
      <Plant x={525} y={FLOOR} scale={0.7} />
    </ComicSvg>
  );
}
