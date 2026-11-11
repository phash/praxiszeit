/**
 * Broschüren-Szene „Stempeln“: Eine MFA kommt morgens in die Praxis, ist am Tablet
 * persönlich angemeldet (Profilsymbol in der Kopfzeile) und tippt auf „Einstempeln“.
 * Kein gemeinsames Stempel-Terminal — das gibt es (noch) nicht.
 * Rechts daneben das Smartphone (als App
 * installierte Web-Seite) mit der Kachel „4:15 von 8:00 h heute“.
 *
 * Alle Texte entsprechen echten Beschriftungen der App (StampWidget/Dashboard).
 */
import { useId } from 'react';
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, UiCard, screenInner } from './ComicKit';

const O = PALETTE.outline;
const line = {
  stroke: O,
  strokeWidth: 3,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

/** Fenster mit Sonnenaufgang (oben links an der Wand). */
function SunriseWindow({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  const clipId = `win-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return (
    <g transform={`translate(${x},${y})`}>
      <defs>
        <clipPath id={clipId}>
          <rect x={0} y={0} width={w} height={h} rx={10} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <rect x={0} y={0} width={w} height={h} fill="#FDEBD3" />
        <rect x={0} y={0} width={w} height={h * 0.45} fill={PALETTE.sky} />
        {/* Sonnenstrahlen */}
        <g {...line} strokeWidth={2.4} fill="none" opacity={0.7}>
          <path d={`M${w * 0.5},${h * 0.84 - 36} v-12`} />
          <path d={`M${w * 0.5 - 30},${h * 0.84 - 20} l-11,-7`} />
          <path d={`M${w * 0.5 + 30},${h * 0.84 - 20} l11,-7`} />
        </g>
        <circle cx={w * 0.5} cy={h * 0.84} r={28} fill={PALETTE.sun} {...line} />
        {/* Wolke */}
        <path
          d={`M${w * 0.14},${h * 0.32} q0,-10 11,-10 q4,-9 14,-6 q8,-6 15,2 q10,0 9,9 q0,5 -6,5 h-36 q-7,0 -7,0 Z`}
          fill={PALETTE.white}
          {...line}
          strokeWidth={2.4}
        />
        {/* Hügel */}
        <path d={`M-4,${h * 0.8} Q${w * 0.3},${h * 0.62} ${w * 0.62},${h * 0.86} L${w * 0.62},${h + 4} L-4,${h + 4} Z`} fill={PALETTE.green} {...line} />
        <path d={`M${w * 0.4},${h * 0.92} Q${w * 0.75},${h * 0.66} ${w + 4},${h * 0.8} L${w + 4},${h + 4} L${w * 0.4},${h + 4} Z`} fill={PALETTE.greenDark} {...line} />
      </g>
      {/* Rahmen + Sprossen */}
      <path d={`M${w / 2},0 V${h} M0,${h / 2} H${w}`} stroke={PALETTE.white} strokeWidth={6} />
      <path d={`M${w / 2},0 V${h} M0,${h / 2} H${w}`} fill="none" {...line} strokeWidth={1.6} opacity={0.35} />
      <rect x={0} y={0} width={w} height={h} rx={10} fill="none" {...line} />
      <rect x={-8} y={h} width={w + 16} height={10} rx={5} fill={PALETTE.white} {...line} />
    </g>
  );
}

/** Wanduhr, zeigt ca. 7:45 Uhr. */
function WallClock({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={24} fill={PALETTE.white} {...line} />
      {[0, 90, 180, 270].map((a) => (
        <path key={a} d="M0,-18 v4" {...line} strokeWidth={2.2} transform={`rotate(${a})`} />
      ))}
      {/* Stundenzeiger kurz vor 8, Minutenzeiger auf 9 */}
      <path d="M0,0 L-6,9" {...line} />
      <path d="M0,0 L-15,0" {...line} strokeWidth={2.4} />
      <circle r={2.5} fill={O} />
    </g>
  );
}

/** Inhalt des Empfangs-Tablets: Uhrzeit + Knopf „Einstempeln“. */
function TabletContent({ w, h }: { w: number; h: number }) {
  const bh = 34;
  const by = h - bh - 6;
  return (
    <g>
      <rect x={0} y={0} width={w} height={22} fill={PALETTE.blueLight} />
      <rect x={8} y={8} width={w * 0.4} height={6} rx={3} fill={PALETTE.blue} />
      {/* Profilsymbol: die Mitarbeiterin ist persönlich angemeldet */}
      <g transform={`translate(${w - 13},11)`}>
        <circle r={7.5} fill={PALETTE.white} stroke={PALETTE.blueDark} strokeWidth={1.5} />
        <circle cy={-2} r={2.4} fill={PALETTE.blueDark} />
        <path d="M-4.2,4.6 Q0,-0.5 4.2,4.6" fill={PALETTE.blueDark} />
      </g>
      <text x={w / 2} y={62} textAnchor="middle" fontSize={26} fontWeight={700} fill={O}>
        07:45
      </text>
      <rect x={w * 0.2} y={74} width={w * 0.6} height={6} rx={3} fill={PALETTE.blueLight} />
      {/* Einstempeln-Knopf */}
      <rect x={4} y={by} width={w - 8} height={bh} rx={10} fill={PALETTE.greenDark} {...line} strokeWidth={2.4} />
      <text x={w / 2} y={by + 21.5} textAnchor="middle" fontSize={12.5} fontWeight={700} fill={O}>
        Einstempeln
      </text>
    </g>
  );
}

/** Inhalt des Smartphones: Kachel Tagessaldo + großer Knopf unten in der Mitte. */
function PhoneContent({ w, h }: { w: number; h: number }) {
  return (
    <g>
      <rect x={0} y={0} width={w} height={h} fill={PALETTE.sky} />
      <rect x={10} y={10} width={w * 0.42} height={7} rx={3.5} fill={PALETTE.blue} />
      {/* Kachel „4:15 von 8:00 h heute“ – nur große Schrift, damit sie auch auf 320 px lesbar bleibt */}
      <g transform="translate(8,26)">
        <rect x={0} y={0} width={w - 16} height={114} rx={12} fill={PALETTE.greenLight} {...line} strokeWidth={2.4} />
        <circle cx={14} cy={15} r={4.5} fill={PALETTE.greenDark} {...line} strokeWidth={1.6} />
        <rect x={25} y={11} width={(w - 16) * 0.5} height={8} rx={4} fill={PALETTE.green} />
        <rect x={10} y={27} width={w - 36} height={8} rx={4} fill={PALETTE.white} {...line} strokeWidth={1.6} />
        <rect x={10} y={27} width={(w - 36) * 0.53} height={8} rx={4} fill={PALETTE.greenDark} {...line} strokeWidth={1.6} />
        <text x={10} y={68} fontSize={32} fontWeight={700} fill={O}>
          4:15
        </text>
        <text x={10} y={88} fontSize={18.5} fontWeight={600} fill={O}>
          von 8:00 h
        </text>
        <text x={10} y={106} fontSize={18.5} fontWeight={600} fill={O}>
          heute
        </text>
      </g>
      {/* weitere Kacheln, nur angedeutet */}
      <UiCard x={8} y={150} w={(w - 22) / 2} h={56} tint="blue" variant="bars" count={2} outline={false} />
      <UiCard x={14 + (w - 22) / 2} y={150} w={(w - 22) / 2} h={56} tint="cream" variant="bars" count={2} outline={false} />
      {/* Navigationsleiste mit großem Knopf in der Mitte */}
      <rect x={0} y={h - 40} width={w} height={40} fill={PALETTE.white} />
      <path d={`M0,${h - 40} H${w}`} stroke={PALETTE.blueLight} strokeWidth={2} />
      <rect x={16} y={h - 24} width={18} height={6} rx={3} fill={PALETTE.blue} />
      <rect x={w - 34} y={h - 24} width={18} height={6} rx={3} fill={PALETTE.blue} />
      <circle cx={w / 2} cy={h - 32} r={20} fill={PALETTE.greenDark} {...line} />
      <circle cx={w / 2} cy={h - 32} r={9} fill={PALETTE.white} {...line} strokeWidth={2} />
      <path d={`M${w / 2},${h - 37} V${h - 32} L${w / 2 + 4},${h - 30}`} fill="none" {...line} strokeWidth={1.8} />
    </g>
  );
}

export interface SceneStempelnProps {
  className?: string;
  /** Schrift für die Texte in der Szene (Standard: Schrift der Seite). */
  fontFamily?: string;
}

/** Szene „Stempeln am Empfang und auf dem Smartphone“. */
export function SceneStempeln({ className, fontFamily }: SceneStempelnProps) {
  const TAB_W = 128;
  const tab = screenInner('tablet', TAB_W);
  const tabH = Math.round(TAB_W * 1.3);
  const PHONE_W = 158;
  const phone = screenInner('phone', PHONE_W);
  const floor = 382;
  const counterTop = 298;
  const tabX = 226;
  const tabY = counterTop - tabH - 6;

  return (
    <ComicSvg
      viewBox="0 0 720 420"
      title="Eine Mitarbeiterin hat sich am Tablet mit ihrem eigenen Benutzernamen angemeldet und tippt morgens auf „Einstempeln“; auf dem Smartphone zeigt PraxisZeit „4:15 von 8:00 h heute“."
      className={className}
      fontFamily={fontFamily}
      background={PALETTE.cream}
    >
      {/* Wand + Boden (linke Szene) */}
      <rect x={14} y={14} width={466} height={392} rx={20} fill={PALETTE.sky} />
      <path d={`M14,${floor} H480 V386 Q480,406 460,406 H34 Q14,406 14,386 Z`} fill={PALETTE.mint} />
      <path d={`M14,${floor} H480`} {...line} strokeWidth={2.4} opacity={0.35} />

      <SunriseWindow x={44} y={48} w={150} h={122} />
      <WallClock x={262} y={78} />
      <Plant x={62} y={floor} scale={1.05} />

      {/* Empfangstresen */}
      <rect x={112} y={counterTop + 10} width={248} height={floor - counterTop - 10} rx={6} fill={PALETTE.white} {...line} />
      <rect x={112} y={counterTop + 40} width={248} height={10} fill={PALETTE.green} />
      <path d={`M112,${counterTop + 40} H360 M112,${counterTop + 50} H360`} {...line} strokeWidth={2} />
      <rect x={100} y={counterTop} width={272} height={14} rx={7} fill={PALETTE.lilac} {...line} />

      {/* Tablet-Ständer + Tablet */}
      <path d={`M${tabX + 34},${tabY + tabH - 30} L${tabX + 22},${counterTop} M${tabX + TAB_W - 34},${tabY + tabH - 30} L${tabX + TAB_W - 22},${counterTop}`} fill="none" {...line} strokeWidth={5} />
      <Screen kind="tablet" x={tabX} y={tabY} width={TAB_W}>
        <TabletContent w={tab.w} h={tab.h} />
      </Screen>

      {/* Kaffeebecher auf dem Tresen */}
      <g transform={`translate(150,${counterTop - 1})`}>
        <path d="M10,-16 Q19,-16 19,-9 Q19,-2 10,-2" fill="none" {...line} />
        <rect x={-11} y={-24} width={22} height={24} rx={5} fill={PALETTE.coral} {...line} />
        <path d="M-4,-30 q-3,-5 0,-10 M4,-30 q3,-5 0,-10" fill="none" {...line} strokeWidth={2} opacity={0.6} />
      </g>

      {/* MFA tippt auf „Einstempeln“ */}
      <Person
        x={410}
        y={floor}
        scale={1.4}
        {...CAST.anna}
        pose="point"
        facing="left"
      />
      {/* Tipp-Striche am Knopf */}
      <path d={`M${tabX + TAB_W + 6},${tabY + tabH - 44} l8,-8 M${tabX + TAB_W + 12},${tabY + tabH - 30} l11,-2`} fill="none" {...line} strokeWidth={2.4} />
      <Bubble x={356} y={112} text={"Guten\nMorgen!"} tail="right" fontSize={15} />

      {/* Rechte Tafel: Smartphone */}
      <rect x={494} y={14} width={212} height={392} rx={20} fill={PALETTE.mint} />
      <text x={600} y={46} textAnchor="middle" fontSize={17} fontWeight={700} fill={O}>
        Auch am Smartphone
      </text>
      <Screen kind="phone" x={521} y={64} width={PHONE_W}>
        <PhoneContent w={phone.w} h={phone.h} />
      </Screen>
      <Sparkle x={514} y={110} size={10} />
      <Sparkle x={692} y={330} size={8} color={PALETTE.blue} />
    </ComicSvg>
  );
}
