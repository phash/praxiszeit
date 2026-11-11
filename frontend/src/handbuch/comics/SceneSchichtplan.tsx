/**
 * Szene „Schichtplan“: Zwei Kolleginnen vor dem ausgedruckten Wochenplan
 * (Aushang über den Knopf „PDF“) mit den Spalten Mo–Fr und farbigen
 * Einteilungen. Eine zeigt auf ihren Mittwoch an der Anmeldung.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Sparkle } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const DAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'];

/** Aushang: Wochenraster mit zwei Arbeitsplätzen je Tag (blau = Anmeldung, grün = Labor). */
function WeekBoard({ x, y }: { x: number; y: number }) {
  const w = 300;
  const h = 196;
  const colW = (w - 32) / 5;
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={14} fill={PALETTE.white} {...ln} />
      <text x={16} y={28} fontSize={16} fontWeight={700} fill={O}>
        Wochenplan
      </text>
      {DAYS.map((d, i) => {
        const cx = 16 + i * colW;
        return (
          <g key={d}>
            <text x={cx + colW / 2} y={52} textAnchor="middle" fontSize={12} fontWeight={700} fill={O}>
              {d}
            </text>
            <rect x={cx + 3} y={60} width={colW / 2 - 5} height={62} rx={5} fill={PALETTE.blueLight} stroke={PALETTE.blueDark} strokeWidth={1.5} />
            <rect x={cx + colW / 2 + 2} y={64} width={colW / 2 - 5} height={50} rx={5} fill={PALETTE.greenLight} stroke={PALETTE.greenDark} strokeWidth={1.5} />
            <rect x={cx + 3} y={128} width={colW / 2 - 5} height={52} rx={5} fill={PALETTE.blueLight} stroke={PALETTE.blueDark} strokeWidth={1.5} />
            {i >= 1 && i <= 3 ? (
              <rect x={cx + colW / 2 + 2} y={128} width={colW / 2 - 5} height={52} rx={5} fill={PALETTE.greenLight} stroke={PALETTE.greenDark} strokeWidth={1.5} />
            ) : null}
          </g>
        );
      })}
      {/* hervorgehobene eigene Einteilung (Mittwoch, Anmeldung) */}
      <rect x={16 + 2 * colW + 1} y={58} width={colW / 2 - 1} height={66} rx={6} fill="none" stroke={PALETTE.coral} strokeWidth={4} />
    </g>
  );
}

export function SceneSchichtplan({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Schichtplan: Zwei Kolleginnen stehen vor dem ausgehängten Wochenplan mit den Tagen Montag bis Freitag und farbigen Einteilungen; eine zeigt auf ihren Mittwoch an der Anmeldung."
      className={className}
      background={PALETTE.cream}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />
      <rect x={140} y={20} width={340} height={8} rx={4} fill={PALETTE.lilacDark} />
      <WeekBoard x={160} y={40} />

      <Person x={96} y={FLOOR} scale={1.3} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={20} y={58} text={'Mittwoch:\nAnmeldung!'} tail="right" fontSize={15} />

      <Person x={540} y={FLOOR} scale={1.25} {...CAST.dana} pose="thumbsUp" facing="left" prop="mug" />
      <Bubble x={478} y={140} text="Ich: Labor." tail="right" fontSize={15} />
      <Sparkle x={520} y={70} size={12} />
    </ComicSvg>
  );
}
