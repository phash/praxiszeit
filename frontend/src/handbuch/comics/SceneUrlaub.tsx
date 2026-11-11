/**
 * SceneUrlaub – Broschüren-Szene „Urlaub & Anträge“.
 *
 * Links stellt eine Mitarbeiterin auf dem Smartphone einen Urlaubsantrag
 * (Typ „Urlaub“, „Speichern“ → Meldung „Urlaubsantrag gestellt“). Ein Papierflieger
 * trägt den Antrag zur Kalenderkarte, die Verwaltung rechts genehmigt ihn
 * (Status „Genehmigt“). Koffer und Sonnenschirm als kleiner Urlaubsgruß.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const PHONE_W = 104;

/** Inhalt des Smartphones: Abwesenheit „Urlaub“ mit markiertem Zeitraum und „Speichern“. */
function PhoneContent() {
  const { w } = screenInner('phone', PHONE_W);
  const cell = (w - 16) / 5;
  return (
    <g>
      <rect x={0} y={0} width={w} height={26} fill={PALETTE.greenLight} />
      <text x={w / 2} y={18} textAnchor="middle" fontSize={13} fontWeight={700} fill={O}>
        Urlaub
      </text>
      {/* kleine Monatsansicht: 3 Wochen × 5 Arbeitstage, eine Woche markiert */}
      {Array.from({ length: 15 }, (_, i) => {
        const r = Math.floor(i / 5);
        const c = i % 5;
        const marked = r === 1;
        return (
          <rect
            key={i}
            x={8 + c * cell + 1.5}
            y={36 + r * (cell + 2)}
            width={cell - 3}
            height={cell - 3}
            rx={3}
            fill={marked ? PALETTE.green : PALETTE.sky}
            stroke={marked ? PALETTE.greenDark : 'none'}
            strokeWidth={1.5}
          />
        );
      })}
      <rect x={8} y={104} width={w - 16} height={8} rx={4} fill={PALETTE.blueLight} />
      <rect x={8} y={118} width={(w - 16) * 0.6} height={8} rx={4} fill={PALETTE.blueLight} />
      <rect x={8} y={136} width={w - 16} height={22} rx={11} fill={PALETTE.blueDark} />
      <text x={w / 2} y={151.5} textAnchor="middle" fontSize={11.5} fontWeight={700} fill={PALETTE.white}>
        Speichern
      </text>
    </g>
  );
}

/** Kalenderkarte der Verwaltung mit genehmigtem Zeitraum. */
function CalendarCard({ x, y }: { x: number; y: number }) {
  const w = 176;
  const h = 168;
  const cell = 28;
  const gx = 18;
  const gy = 50;
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={16} fill={PALETTE.white} {...ln} />
      <path d={`M3,16 Q3,3 16,3 L${w - 16},3 Q${w - 3},3 ${w - 3},16 L${w - 3},36 L3,36 Z`} fill={PALETTE.blue} />
      <path d={`M1.5,36 L${w - 1.5},36`} {...ln} />
      <rect x={0} y={0} width={w} height={h} rx={16} fill="none" {...ln} />
      {/* Ringe oben */}
      {[44, w - 44].map((rx) => (
        <rect key={rx} x={rx - 4} y={-10} width={8} height={20} rx={4} fill={PALETTE.lilac} {...ln} strokeWidth={2.5} />
      ))}
      <text x={18} y={27} fontSize={15} fontWeight={700} fill={O}>
        Urlaub
      </text>
      {/* Raster 5 × 3, mittlere Woche genehmigt */}
      {Array.from({ length: 15 }, (_, i) => {
        const r = Math.floor(i / 5);
        const c = i % 5;
        const marked = r === 1;
        return (
          <rect
            key={i}
            x={gx + c * cell + 2}
            y={gy + r * cell + 2}
            width={cell - 4}
            height={cell - 4}
            rx={6}
            fill={marked ? PALETTE.green : PALETTE.sky}
            stroke={marked ? PALETTE.greenDark : 'none'}
            strokeWidth={2}
          />
        );
      })}
      {/* Status-Pille */}
      <rect x={18} y={gy + 3 * cell + 8} width={110} height={26} rx={13} fill={PALETTE.greenLight} stroke={PALETTE.greenDark} strokeWidth={2} />
      <text x={73} y={gy + 3 * cell + 26} textAnchor="middle" fontSize={14} fontWeight={700} fill={O}>
        Genehmigt
      </text>
      {/* großes Häkchen */}
      <g transform={`translate(${w - 28},${gy + 3 * cell + 21})`}>
        <circle r={17} fill={PALETTE.green} {...ln} />
        <path d="M-8,0 L-2,6 L9,-6" fill="none" {...ln} strokeWidth={4} />
      </g>
    </g>
  );
}

/** Kleiner Rollkoffer. */
function Suitcase({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <path d="M-10,-50 L-10,-60 Q-10,-64 -6,-64 L6,-64 Q10,-64 10,-60 L10,-50" fill="none" {...ln} />
      <rect x={-24} y={-52} width={48} height={44} rx={9} fill={PALETTE.coral} {...ln} />
      <path d="M-10,-44 L-10,-16 M10,-44 L10,-16" {...ln} strokeWidth={2.5} stroke={PALETTE.white} />
      <circle cx={-14} cy={-4} r={4} fill={PALETTE.shoe} {...ln} strokeWidth={2} />
      <circle cx={14} cy={-4} r={4} fill={PALETTE.shoe} {...ln} strokeWidth={2} />
    </g>
  );
}

/** Kleiner Sonnenschirm (Fuß auf x, y). */
function Umbrella({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <path d="M0,0 L0,-70" {...ln} />
      <path d="M-38,-62 Q0,-104 38,-62 Q28,-70 19,-62 Q10,-70 0,-62 Q-10,-70 -19,-62 Q-28,-70 -38,-62 Z" fill={PALETTE.sun} {...ln} />
      <path d="M0,-62 Q-6,-84 0,-90 M0,-62 Q6,-84 0,-90" fill="none" {...ln} strokeWidth={2} />
      <path d="M-14,0 L14,0" {...ln} />
    </g>
  );
}

export function SceneUrlaub({ className }: { className?: string }) {
  const floor = 352;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Urlaubsantrag: Eine Mitarbeiterin stellt auf dem Smartphone einen Urlaubsantrag, die Verwaltung genehmigt ihn unter „Anträge“, danach steht der Urlaub im Kalender."
      className={className}
      background={PALETTE.sky}
    >
      {/* Boden */}
      <rect x={14} y={floor} width={612} height={14} rx={7} fill={PALETTE.mint} />

      {/* Weg des Antrags: gestrichelter Bogen mit Papierflieger */}
      <path d="M262,150 Q312,64 372,96" fill="none" stroke={PALETTE.blueDark} strokeWidth={3} strokeDasharray="2 9" strokeLinecap="round" />
      <g transform="translate(318,84) rotate(14)">
        <path d="M-18,-8 L20,0 L-18,10 L-10,1 Z" fill={PALETTE.white} {...ln} strokeWidth={2.5} />
        <path d="M-10,1 L20,0" fill="none" {...ln} strokeWidth={2} />
      </g>

      {/* Mitarbeiterin mit Smartphone */}
      <Person
        x={102}
        y={floor}
        scale={1.45}
        {...CAST.dana}
        pose="point"
      />
      <Screen kind="phone" x={168} y={128} width={PHONE_W}>
        <PhoneContent />
      </Screen>
      <Bubble x={70} y={22} text={'Urlaubsantrag\ngestellt'} tail="left" fontSize={18} />

      {/* Kalenderkarte der Verwaltung */}
      <CalendarCard x={352} y={96} />
      <Sparkle x={540} y={100} size={12} />

      {/* Verwaltung genehmigt */}
      <Person
        x={578}
        y={floor}
        scale={1.25}
        {...CAST.bea}
        pose="thumbsUp"
        facing="left"
      />
      <Bubble x={470} y={22} text="Genehmigt!" tail="right" fontSize={18} />

      {/* Urlaubsgruß */}
      <Umbrella x={314} y={floor} />
      <Suitcase x={392} y={floor} />
    </ComicSvg>
  );
}
