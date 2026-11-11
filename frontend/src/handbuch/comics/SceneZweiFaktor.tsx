/**
 * Szene „Profil & Sicherheit“: Am Praxis-PC fragt die Anmeldung nach dem
 * „2FA-Code (Authenticator-App)“; die Mitarbeiterin liest den 6-stelligen Code
 * von ihrem Smartphone ab. Ein Schild mit Schloss steht für das abgesicherte Konto.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Screen, Sparkle, screenInner } from './ComicKit';

const O = PALETTE.outline;
const ln = { stroke: O, strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

const FLOOR = 350;
const MON_W = 236;
const PHONE_W = 96;

function LoginContent() {
  const { w } = screenInner('monitor', MON_W);
  return (
    <g>
      <text x={w / 2} y={22} textAnchor="middle" fontSize={14} fontWeight={700} fill={PALETTE.blueDark}>
        PraxisZeit
      </text>
      <rect x={20} y={32} width={w - 40} height={14} rx={4} fill={PALETTE.sky} stroke={PALETTE.blue} strokeWidth={1.5} />
      <rect x={20} y={52} width={w - 40} height={14} rx={4} fill={PALETTE.sky} stroke={PALETTE.blue} strokeWidth={1.5} />
      <text x={20} y={82} fontSize={9.5} fontWeight={600} fill={O}>
        2FA-Code (Authenticator-App)
      </text>
      <rect x={20} y={87} width={w - 40} height={18} rx={4} fill={PALETTE.white} stroke={PALETTE.blueDark} strokeWidth={2} />
      <text x={w / 2} y={100} textAnchor="middle" fontSize={11} fontWeight={700} fill={O} letterSpacing={3}>
        ••••••
      </text>
      <rect x={20} y={112} width={w - 40} height={18} rx={6} fill={PALETTE.blueDark} />
      <text x={w / 2} y={125} textAnchor="middle" fontSize={10} fontWeight={700} fill={PALETTE.white}>
        Anmelden
      </text>
    </g>
  );
}

function CodeContent() {
  const { w, h } = screenInner('phone', PHONE_W);
  return (
    <g>
      <rect x={0} y={0} width={w} height={h} fill={PALETTE.lilac} />
      <g transform={`translate(${w / 2},44)`}>
        <path d="M0,-24 C8,-19 15,-18 20,-18 C20,-2 14,10 0,17 C-14,10 -20,-2 -20,-18 C-15,-18 -8,-19 0,-24 Z" fill={PALETTE.green} {...ln} strokeWidth={2.5} />
        <path d="M-5.5,-4 v-4 a5.5,5.5 0 0 1 11,0 v4" fill="none" {...ln} strokeWidth={2.2} />
        <rect x={-8} y={-4} width={16} height={12} rx={3} fill={PALETTE.sun} {...ln} strokeWidth={2.2} />
      </g>
      <rect x={8} y={80} width={w - 16} height={28} rx={8} fill={PALETTE.white} {...ln} strokeWidth={2} />
      <text x={w / 2} y={99} textAnchor="middle" fontSize={15} fontWeight={700} fill={O}>
        482 913
      </text>
      <rect x={w / 2 - 22} y={118} width={44} height={5} rx={2.5} fill={PALETTE.lilacDark} />
    </g>
  );
}

export function SceneZweiFaktor({ className }: { className?: string }) {
  const monX = 300;
  const monY = 96;
  const deskTop = monY + Math.round(MON_W * 0.62) + 28;
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Zwei-Faktor-Anmeldung: Der Praxis-PC fragt nach dem 2FA-Code aus der Authenticator-App. Die Mitarbeiterin liest den 6-stelligen Code von ihrem Smartphone ab; ein grünes Schild mit Schloss steht für das abgesicherte Konto."
      className={className}
      background={PALETTE.mint}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.green} opacity={0.5} />

      <Person x={150} y={FLOOR} scale={1.45} {...CAST.bea} pose="point" facing="right" />
      <Screen kind="phone" x={196} y={120} width={PHONE_W}>
        <CodeContent />
      </Screen>
      <Bubble x={40} y={28} text={'Code aus der App –\nfertig!'} tail="left" fontSize={16} />

      <rect x={monX + 8} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <rect x={monX + MON_W - 18} y={deskTop + 10} width={10} height={FLOOR - deskTop - 10} fill={PALETTE.lilacDark} {...ln} />
      <Screen kind="monitor" x={monX} y={monY} width={MON_W}>
        <LoginContent />
      </Screen>
      <rect x={monX - 8} y={deskTop} width={MON_W + 16} height={12} rx={6} fill="#FCE9C2" {...ln} />

      <Sparkle x={560} y={92} size={13} />
      <Sparkle x={296} y={300} size={9} color={PALETTE.blue} />
      <Plant x={588} y={FLOOR} scale={0.85} />
    </ComicSvg>
  );
}
