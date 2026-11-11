/**
 * Szene „Auf dem Handy“: Eine Mitarbeiterin hält ihr Smartphone. Darauf die
 * Stempelkarte „Eingestempelt seit 07:45“ und die untere Leiste mit Home,
 * Journal, Abwes., Profil und dem runden grünen Stempel-Knopf in der Mitte –
 * wie in der App auf schmalen Bildschirmen.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const PHONE_W = 150;

function PhoneContent() {
  const { w, h } = screenInner('phone', PHONE_W);
  const barY = h - 34;
  const tabs = [
    { x: w * 0.12, label: 'Home' },
    { x: w * 0.32, label: 'Journal' },
    { x: w * 0.68, label: 'Abwes.' },
    { x: w * 0.88, label: 'Profil' },
  ];
  return (
    <g>
      {/* Kopfzeile mit Menü */}
      <rect x={0} y={0} width={w} height={26} fill={PALETTE.white} />
      <text x={8} y={18} fontSize={12} fontWeight={700} fill={PALETTE.blueDark}>
        PraxisZeit
      </text>
      <path d={`M${w - 22},9 h12 M${w - 22},14 h12 M${w - 22},19 h12`} stroke={O} strokeWidth={2} strokeLinecap="round" />
      <rect x={0} y={26} width={w} height={h - 26} fill={PALETTE.sky} />
      {/* Stempelkarte */}
      <rect x={8} y={36} width={w - 16} height={58} rx={10} fill={PALETTE.greenLight} stroke={PALETTE.greenDark} strokeWidth={1.5} />
      <circle cx={18} cy={52} r={3.5} fill={PALETTE.greenDark} />
      <text x={24} y={56} fontSize={8} fontWeight={700} fill={O}>
        Eingestempelt seit 07:45
      </text>
      <rect x={16} y={66} width={w - 32} height={6} rx={3} fill={PALETTE.white} />
      <rect x={16} y={66} width={(w - 32) * 0.4} height={6} rx={3} fill={PALETTE.greenDark} />
      <text x={16} y={86} fontSize={8} fill={O}>
        2:45 von 8:00 h heute
      </text>
      {/* Kacheln */}
      <rect x={8} y={102} width={(w - 24) / 2} height={44} rx={8} fill={PALETTE.white} />
      <rect x={16 + (w - 24) / 2} y={102} width={(w - 24) / 2} height={44} rx={8} fill={PALETTE.white} />
      <rect x={16} y={114} width={30} height={8} rx={4} fill={PALETTE.blue} />
      <rect x={24 + (w - 24) / 2} y={114} width={30} height={8} rx={4} fill={PALETTE.green} />
      {/* untere Leiste */}
      <rect x={0} y={barY} width={w} height={34} fill={PALETTE.white} />
      <path d={`M0,${barY} L${w},${barY}`} stroke={PALETTE.blueLight} strokeWidth={1.5} />
      {tabs.map((t) => (
        <g key={t.label}>
          <rect x={t.x - 5} y={barY + 6} width={10} height={9} rx={2} fill="none" stroke={O} strokeWidth={1.5} />
          <text x={t.x} y={barY + 27} textAnchor="middle" fontSize={7} fill={O}>
            {t.label}
          </text>
        </g>
      ))}
      {/* runder Stempel-Knopf */}
      <circle cx={w / 2} cy={barY + 6} r={15} fill={PALETTE.greenDark} {...ln} strokeWidth={2} />
      <circle cx={w / 2} cy={barY + 7} r={6} fill="none" stroke={PALETTE.white} strokeWidth={2} />
      <path d={`M${w / 2},${barY + 7} L${w / 2},${barY + 3.5}`} stroke={PALETTE.white} strokeWidth={2} strokeLinecap="round" />
    </g>
  );
}

export function SceneHandy({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Auf dem Smartphone: Eine Mitarbeiterin zeigt PraxisZeit auf ihrem Handy – oben die Stempelkarte „Eingestempelt seit 07:45“, unten die Leiste mit Home, Journal, Abwes. und Profil und in der Mitte der runde Stempel-Knopf."
      className={className}
      background={PALETTE.sky}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      <Person x={150} y={FLOOR} scale={1.5} {...CAST.dana} pose="point" facing="right" />
      <Screen kind="phone" x={232} y={58} width={PHONE_W}>
        <PhoneContent />
      </Screen>
      <Bubble x={36} y={30} text={'Ein Tipp –\neingestempelt!'} tail="right" fontSize={16} />
      <Sparkle x={404} y={86} size={13} />
      <Sparkle x={214} y={262} size={9} color={PALETTE.blue} />

      <Person x={510} y={FLOOR} scale={1.3} {...CAST.chris} pose="wave" facing="left" prop="phone" />
      <Bubble x={440} y={96} text="Guten Morgen!" tail="right" fontSize={15} />

      <Plant x={600} y={FLOOR} scale={0.8} />
    </ComicSvg>
  );
}
