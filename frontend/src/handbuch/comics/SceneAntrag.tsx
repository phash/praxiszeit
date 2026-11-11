/**
 * Szene „Anträge“: Eine Mitarbeiterin stellt am Praxis-PC einen Änderungsantrag
 * (orange Kopfzeile wie im Dialog „Änderungsantrag: Eintrag ändern“, Begründung,
 * Knopf „Antrag stellen“). Ein Pfeil führt zur Verwaltung, die ihn prüft; die
 * Status-Pillen „Offen“ → „Genehmigt“ entsprechen dem Tab „Anträge“.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 232;
const AMBER = '#F59E0B';

/** Bildschirminhalt: Antragsformular. */
function FormContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={24} fill={AMBER} />
      <text x={10} y={17} fontSize={12} fontWeight={700} fill={PALETTE.white}>
        Änderungsantrag
      </text>
      <rect x={10} y={32} width={w * 0.42} height={16} rx={4} fill={PALETTE.sky} stroke={PALETTE.blue} strokeWidth={1.5} />
      <rect x={w * 0.52} y={32} width={w * 0.42} height={16} rx={4} fill={PALETTE.sky} stroke={PALETTE.blue} strokeWidth={1.5} />
      <text x={10} y={63} fontSize={10} fontWeight={600} fill={O}>
        Begründung
      </text>
      <rect x={10} y={68} width={w - 20} height={26} rx={5} fill={PALETTE.white} stroke={PALETTE.blueDark} strokeWidth={1.5} />
      <rect x={16} y={75} width={(w - 32) * 0.7} height={5} rx={2.5} fill={PALETTE.blue} />
      <rect x={16} y={84} width={(w - 32) * 0.45} height={5} rx={2.5} fill={PALETTE.blue} />
      <rect x={w - 92} y={102} width={82} height={20} rx={6} fill={AMBER} />
      <text x={w - 51} y={116} textAnchor="middle" fontSize={10} fontWeight={700} fill={PALETTE.white}>
        Antrag stellen
      </text>
    </g>
  );
}

/** Status-Pille wie im Tab „Anträge“. */
function Pill({ x, y, label, fill, stroke }: { x: number; y: number; label: string; fill: string; stroke: string }) {
  const w = label.length * 9 + 26;
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={26} rx={13} fill={fill} stroke={stroke} strokeWidth={2.5} />
      <text x={w / 2} y={18} textAnchor="middle" fontSize={14} fontWeight={700} fill={O}>
        {label}
      </text>
    </g>
  );
}

export function SceneAntrag({ className }: { className?: string }) {
  const monX = 96;
  const monY = 112;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Änderungsantrag: Eine Mitarbeiterin korrigiert am Praxis-PC einen älteren Zeiteintrag per Antrag mit Begründung. Die Verwaltung prüft ihn; der Status wechselt von „Offen“ zu „Genehmigt“."
      className={className}
      background={PALETTE.cream}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      {/* Schreibtisch mit Monitor */}
      <rect x={104} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={306} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <FormContent />
      </Screen>
      <rect x={90} y={deskTop} width={240} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Person x={52} y={FLOOR} scale={1.15} {...CAST.anna} pose="point" facing="right" />
      <Bubble x={24} y={22} text={'Ich hatte vergessen\neinzustempeln.'} tail="left" fontSize={15} />

      {/* Weg des Antrags: vom Formular zur Status-Pille */}
      <path d="M338,176 Q352,140 366,134" fill="none" stroke={PALETTE.blueDark} strokeWidth={3} strokeDasharray="2 9" strokeLinecap="round" />

      {/* Status: Offen → Genehmigt (über der Verwaltung, damit nichts verdeckt wird) */}
      <Pill x={372} y={120} label="Offen" fill="#FEF3C7" stroke="#D97706" />
      <path d="M440,133 L462,133 M455,126 L462,133 L455,140" fill="none" {...ln} strokeWidth={2.5} />
      <Pill x={470} y={120} label="Genehmigt" fill={PALETTE.greenLight} stroke={PALETTE.greenDark} />
      <Sparkle x={604} y={112} size={11} />

      {/* Verwaltung prüft */}
      <Person x={548} y={FLOOR} scale={1.15} {...CAST.bea} pose="thumbsUp" facing="left" prop="clipboard" />
      <Bubble x={488} y={40} text="Geprüft!" tail="right" fontSize={16} />

      <Plant x={360} y={FLOOR} scale={0.75} />
    </ComicSvg>
  );
}
