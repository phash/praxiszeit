/**
 * SceneHero – Titelbild der Broschüre: ein kleines, gut gelauntes Praxisteam
 * vor dem Anmeldetresen; der Monitor zeigt die persönliche Stempelkarte
 * (Profilsymbol = angemeldete Person) im Zustand „Eingestempelt“. Breitformat 16:9.
 */
import { CAST, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, Bubble, screenInner } from './ComicKit';

const O = PALETTE.outline;
const line = {
  stroke: O,
  strokeWidth: 3,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const MONITOR_W = 280;
const MONITOR_X = 340;
const MONITOR_Y = 92;

/** Inhalt des Monitors: Stempelkarte im Zustand „Eingestempelt“. */
function StampCard() {
  const { w, h } = screenInner('monitor', MONITOR_W);
  const cx = w / 2;
  return (
    <g>
      {/* App-Kopfzeile: Logo-Punkt, Platzhalterbalken, rechts das Profil der angemeldeten Person */}
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueLight} />
      <circle cx={13} cy={11} r={5} fill={PALETTE.blueDark} />
      <rect x={24} y={7} width={54} height={8} rx={4} fill={PALETTE.blue} />
      <g transform={`translate(${w - 14},11)`}>
        <circle r={8} fill={PALETTE.white} stroke={PALETTE.blueDark} strokeWidth={1.5} />
        <circle cy={-2} r={2.6} fill={PALETTE.blueDark} />
        <path d="M-4.5,5 Q0,-0.5 4.5,5" fill={PALETTE.blueDark} />
      </g>
      {/* Karte – nur große Schlüsselwörter, damit sie auch auf 320 px lesbar bleiben */}
      <rect x={14} y={30} width={w - 28} height={h - 40} rx={10} fill={PALETTE.mint} stroke={PALETTE.greenDark} strokeWidth={2} />
      {/* großer Haken */}
      <g transform={`translate(${cx},${52})`}>
        <circle r={15} fill={PALETTE.green} {...line} />
        <path d="M-6,0 L-1.5,5 L7,-5" fill="none" {...line} strokeWidth={3.5} />
      </g>
      <text x={cx} y={98} textAnchor="middle" fontSize={28} fontWeight={800} fill={O}>
        Eingestempelt
      </text>
      <text x={cx} y={131} textAnchor="middle" fontSize={24} fontWeight={700} fill={PALETTE.shoe}>
        seit 07:45
      </text>
    </g>
  );
}

/** Hero-Szene: Team vor dem Anmeldetresen, Monitor zeigt „Eingestempelt“. */
export function SceneHero({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 960 540"
      title="Ein fröhliches Praxisteam steht vor dem Anmeldetresen. Auf dem Monitor zeigt die persönliche Stempelkarte einer angemeldeten Mitarbeiterin „Eingestempelt seit 07:45“, eine Kollegin winkt."
      className={className}
      background={PALETTE.sky}
    >
      {/* Boden */}
      <path d="M0,430 L960,430 L960,516 Q960,540 936,540 L24,540 Q0,540 0,516 Z" fill={PALETTE.cream} />
      <path d="M0,430 L960,430" {...line} strokeWidth={2.5} opacity={0.35} />

      {/* Fenster links */}
      <g transform="translate(56,56)">
        <rect x={0} y={0} width={150} height={120} rx={12} fill={PALETTE.white} {...line} />
        <rect x={10} y={10} width={130} height={100} rx={7} fill="#D9ECF8" />
        <circle cx={108} cy={38} r={14} fill={PALETTE.sun} />
        <path d="M22,92 Q48,62 74,84 Q98,66 128,92 Z" fill={PALETTE.green} />
        <path d="M75,10 L75,110 M10,60 L140,60" {...line} strokeWidth={4} stroke={PALETTE.white} />
        <rect x={0} y={0} width={150} height={120} rx={12} fill="none" {...line} />
      </g>

      {/* Wanduhr rechts */}
      <g transform="translate(830,96)">
        <circle r={36} fill={PALETTE.white} {...line} />
        <circle r={29} fill={PALETTE.cream} />
        {[0, 90, 180, 270].map((a) => (
          <rect key={a} x={-2} y={-27} width={4} height={7} rx={2} fill={O} transform={`rotate(${a})`} />
        ))}
        {/* 7:50 Uhr – passt zu „seit 07:45“ und „Guten Morgen!“ */}
        <path d="M0,0 L-12,8 M0,0 L-19,-11" {...line} />
        <circle r={3} fill={O} />
      </g>

      {/* Anmeldetresen */}
      <g>
        <rect x={150} y={300} width={660} height={130} rx={10} fill={PALETTE.white} {...line} />
        <rect x={168} y={326} width={624} height={88} rx={8} fill={PALETTE.greenLight} />
        <path d="M168,360 L792,360" stroke={PALETTE.green} strokeWidth={6} strokeLinecap="round" />
        <rect x={136} y={288} width={688} height={18} rx={9} fill={PALETTE.lilac} {...line} />
      </g>

      {/* Schild „Anmeldung“ am Tresen */}
      <g transform="translate(410,346)">
        <rect x={0} y={0} width={140} height={40} rx={20} fill={PALETTE.lilac} {...line} />
        <text x={70} y={27} textAnchor="middle" fontSize={18} fontWeight={700} fill={O}>
          Anmeldung
        </text>
      </g>

      {/* Monitor auf dem Tresen */}
      <Screen kind="monitor" x={MONITOR_X} y={MONITOR_Y} width={MONITOR_W}>
        <StampCard />
      </Screen>
      <Sparkle x={644} y={104} size={13} />
      <Sparkle x={316} y={150} size={9} color={PALETTE.green} />

      {/* Pflanze auf dem Tresen links */}
      <Plant x={760} y={290} scale={0.95} />

      {/* Team */}
      <Person
        x={150}
        y={526}
        scale={1.75}
        {...CAST.anna}
        pose="wave"
      />
      <Person
        x={320}
        y={530}
        scale={1.75}
        {...CAST.bea}
        pose="thumbsUp"
      />
      <Person
        x={640}
        y={530}
        scale={1.75}
        {...CAST.chris}
        pose="stand"
        prop="phone"
        facing="left"
      />
      <Person
        x={812}
        y={526}
        scale={1.75}
        {...CAST.dana}
        pose="stand"
        prop="tablet"
        facing="left"
      />

      {/* Sprechblase der winkenden Kollegin */}
      <Bubble x={36} y={192} text="Guten Morgen!" tail="right" fontSize={17} />
    </ComicSvg>
  );
}
