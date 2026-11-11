/**
 * ComicKit – gemeinsame SVG-Bausteine für die Broschüre.
 *
 * Stil: flache, freundliche Comic-Figuren (runde Köpfe, Punktaugen, kleines Lächeln),
 * dicke weiche Konturen in Dunkel-Schiefer, Kleidung nur in Pastellblau oder Pastellgrün.
 *
 * Koordinaten: <Person> steht mit den Füßen auf (x, y); bei scale = 1 ist eine
 * stehende Figur ca. 130 Einheiten hoch und ca. 60 breit. Alle Bausteine liefern
 * ein SVG-<g> und werden in ein <svg viewBox="…"> (z. B. <ComicSvg>) eingesetzt.
 */
import { useId, type ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

export const PALETTE = {
  outline: '#2F3E4E',
  white: '#FFFFFF',
  // Kleidung
  blue: '#A8CBE8',
  blueDark: '#7FA9CF',
  blueLight: '#D3E5F4',
  green: '#B7E2C8',
  greenDark: '#88C4A1',
  greenLight: '#DAF1E3',
  // Hintergründe
  sky: '#EAF4FB',
  mint: '#EAF7EF',
  cream: '#FFF8EC',
  lilac: '#E9E4F5',
  lilacDark: '#C9BEE6',
  // Akzente
  sun: '#FFD98A',
  coral: '#F6B3A6',
  cheek: '#F4A6A0',
  shoe: '#4A5A6B',
  // Haarfarben
  hair: {
    warmBrown: '#8B5E3C',
    sand: '#D8B27A',
    softBlack: '#3B3A40',
    auburn: '#A4523A',
    lightGrey: '#C9CDD2',
    chestnut: '#6B4A35',
  },
  // Hauttöne
  skin: {
    light: '#FBE3D2',
    peach: '#F4CDAE',
    tan: '#DDAA82',
    olive: '#C99B72',
    brown: '#A87552',
    deep: '#7E5238',
  },
} as const;

export type Shirt = 'blue' | 'green';
export type HairStyle = 'short' | 'sidePart' | 'bob' | 'bun' | 'ponytail' | 'curls' | 'long';
export type Pose = 'stand' | 'wave' | 'point' | 'sit' | 'thumbsUp';
export type Facing = 'left' | 'right';
export type HeldProp = 'tablet' | 'phone' | 'mug' | 'clipboard';
export type Tint = 'blue' | 'green' | 'cream' | 'lilac' | 'sky' | 'mint';

export const HAIR_STYLES: readonly HairStyle[] = [
  'short',
  'sidePart',
  'bob',
  'bun',
  'ponytail',
  'curls',
  'long',
];
export const POSES: readonly Pose[] = ['stand', 'wave', 'point', 'thumbsUp', 'sit'];

/**
 * Feste Besetzung: dieselbe Person sieht in jeder Szene gleich aus
 * (Haarschnitt, Haarfarbe, Hautton, Shirtfarbe). In Szenen per `{...CAST.anna}` einsetzen.
 */
export const CAST = {
  anna: { shirt: 'blue', hair: 'bun', hairColor: PALETTE.hair.auburn, skin: PALETTE.skin.peach },
  bea: { shirt: 'green', hair: 'curls', hairColor: PALETTE.hair.softBlack, skin: PALETTE.skin.brown },
  chris: { shirt: 'blue', hair: 'sidePart', hairColor: PALETTE.hair.sand, skin: PALETTE.skin.light },
  dana: { shirt: 'green', hair: 'ponytail', hairColor: PALETTE.hair.warmBrown, skin: PALETTE.skin.tan },
} as const satisfies Record<string, { shirt: Shirt; hair: HairStyle; hairColor: string; skin: string }>;

const O = PALETTE.outline;
const SW = 3;

const TINTS: Record<Tint, { bg: string; bar: string; barSoft: string }> = {
  blue: { bg: PALETTE.blueLight, bar: PALETTE.blueDark, barSoft: PALETTE.blue },
  green: { bg: PALETTE.greenLight, bar: PALETTE.greenDark, barSoft: PALETTE.green },
  cream: { bg: PALETTE.cream, bar: PALETTE.sun, barSoft: '#FCE9C2' },
  lilac: { bg: PALETTE.lilac, bar: PALETTE.lilacDark, barSoft: '#DDD5EF' },
  sky: { bg: PALETTE.sky, bar: PALETTE.blue, barSoft: PALETTE.blueLight },
  mint: { bg: PALETTE.mint, bar: PALETTE.green, barSoft: PALETTE.greenLight },
};

const line = {
  stroke: O,
  strokeWidth: SW,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

/** Sanitised id for url(#…) references (React's useId contains colons). */
function useSvgId(prefix: string): string {
  return `${prefix}-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
}

// ---------------------------------------------------------------------------
// Root wrapper
// ---------------------------------------------------------------------------

export interface ComicSvgProps {
  /** e.g. "0 0 640 360" */
  viewBox: string;
  /** German description – used as aria-label (no <title>: avoids a hover tooltip and double reading). */
  title: string;
  className?: string;
  /** Optional background colour for the whole scene. */
  background?: string;
  /** Font for bubbles/cards; defaults to the page font. */
  fontFamily?: string;
  children?: ReactNode;
}

/** Responsive, accessible <svg> root for a scene. */
export function ComicSvg({ viewBox, title, className, background, fontFamily = 'inherit', children }: ComicSvgProps) {
  const [, , w, h] = viewBox.split(/[\s,]+/).map(Number);
  return (
    <svg
      viewBox={viewBox}
      role="img"
      aria-label={title}
      className={`block h-auto max-w-full${className ? ` ${className}` : ''}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      xmlns="http://www.w3.org/2000/svg"
      // Presentation attribute, not a style prop: the site CSP (style-src 'self')
      // blocks inline style attributes.
      fontFamily={fontFamily}
    >
      {background ? <rect x={0} y={0} width={w} height={h} rx={24} fill={background} /> : null}
      {children}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Person
// ---------------------------------------------------------------------------

export interface PersonProps {
  x: number;
  y: number;
  scale?: number;
  shirt: Shirt;
  hair: HairStyle;
  hairColor: string;
  skin: string;
  pose?: Pose;
  facing?: Facing;
  prop?: HeldProp;
  /** Sitting figures get a simple stool unless this is false. */
  seat?: boolean;
}

type Pt = readonly [number, number];

/** Outlined "tube" limb: dark wide stroke + coloured narrower stroke. */
function Limb({ d, color, width = 11 }: { d: string; color: string; width?: number }) {
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} stroke={O} strokeWidth={width + SW * 2} />
      <path d={d} stroke={color} strokeWidth={width} />
    </g>
  );
}

function Hand({ p, skin }: { p: Pt; skin: string }) {
  return <circle cx={p[0]} cy={p[1]} r={5.5} fill={skin} {...line} />;
}

const HEAD: Pt = [0, -100];
const HEAD_R = 20;

/** Hair drawn behind the head. */
function HairBack({ style, color }: { style: HairStyle; color: string }) {
  switch (style) {
    case 'bob':
      return (
        <path
          d="M-24,-104 Q-26,-126 0,-126 Q26,-126 24,-104 L25,-84 Q25,-78 19,-78 L-19,-78 Q-25,-78 -25,-84 Z"
          fill={color}
          {...line}
        />
      );
    case 'long':
      return (
        <path
          d="M-23,-104 Q-25,-126 0,-126 Q25,-126 23,-104 L25,-70 Q26,-62 18,-62 L-18,-62 Q-26,-62 -25,-70 Z"
          fill={color}
          {...line}
        />
      );
    case 'ponytail':
      return (
        <path
          d="M-14,-114 Q-34,-116 -36,-96 Q-37,-80 -28,-70 Q-24,-80 -26,-92 Q-24,-104 -12,-106 Z"
          fill={color}
          {...line}
        />
      );
    case 'bun':
      return <circle cx={0} cy={-124} r={10} fill={color} {...line} />;
    case 'curls':
      return (
        <g fill={color} {...line}>
          <circle cx={-21} cy={-92} r={7} />
          <circle cx={21} cy={-92} r={7} />
        </g>
      );
    default:
      return null;
  }
}

/** Hair drawn over the top of the head (fringe / cap). */
function HairFront({ style, color }: { style: HairStyle; color: string }) {
  switch (style) {
    case 'short':
      return (
        <path
          d="M-20,-98 Q-23,-123 0,-123 Q23,-123 20,-98 Q17,-108 8,-109 Q-2,-104 -10,-108 Q-17,-107 -20,-98 Z"
          fill={color}
          {...line}
        />
      );
    case 'sidePart':
      return (
        <path
          d="M-20,-96 Q-23,-123 2,-123 Q24,-122 20,-98 Q19,-108 12,-111 Q0,-108 -6,-114 Q-12,-106 -20,-96 Z"
          fill={color}
          {...line}
        />
      );
    case 'bob':
    case 'long':
      return (
        <path
          d="M-21,-96 Q-23,-122 0,-122 Q23,-122 21,-96 Q18,-104 10,-106 Q2,-106 -4,-110 Q-10,-104 -21,-96 Z"
          fill={color}
          {...line}
        />
      );
    case 'bun':
    case 'ponytail':
      return (
        <path
          d="M-20,-97 Q-22,-122 0,-122 Q22,-122 20,-97 Q16,-108 0,-109 Q-16,-108 -20,-97 Z"
          fill={color}
          {...line}
        />
      );
    case 'curls': {
      const pts: Pt[] = [
        [-18, -104],
        [-13, -115],
        [-3, -121],
        [8, -120],
        [17, -112],
        [20, -102],
      ];
      return (
        <g fill={color} {...line}>
          <path d="M-20,-99 Q-22,-122 0,-122 Q22,-122 20,-99 Q10,-108 0,-108 Q-10,-108 -20,-99 Z" />
          {pts.map(([cx, cy]) => (
            <circle key={`${cx}`} cx={cx} cy={cy} r={7.5} />
          ))}
          {/* cover inner outlines so the curls read as one shape */}
          <path
            d="M-15,-106 Q-12,-116 0,-116 Q12,-116 15,-106 Q8,-110 0,-110 Q-8,-110 -15,-106 Z"
            stroke="none"
          />
        </g>
      );
    }
    default:
      return null;
  }
}

function Face({ skin }: { skin: string }) {
  const [hx, hy] = HEAD;
  return (
    <g>
      <circle cx={hx} cy={hy} r={HEAD_R} fill={skin} {...line} />
      {/* ears */}
      <circle cx={hx - HEAD_R + 1} cy={hy + 2} r={4} fill={skin} {...line} />
      <circle cx={hx + HEAD_R - 1} cy={hy + 2} r={4} fill={skin} {...line} />
      <circle cx={hx} cy={hy} r={HEAD_R - 1.6} fill={skin} />
      {/* eyes (looking slightly towards facing direction) */}
      <circle cx={hx - 5} cy={hy - 1} r={2.4} fill={O} />
      <circle cx={hx + 8} cy={hy - 1} r={2.4} fill={O} />
      {/* cheeks */}
      <ellipse cx={hx - 9} cy={hy + 6} rx={3.6} ry={2.4} fill={PALETTE.cheek} opacity={0.55} />
      <ellipse cx={hx + 13} cy={hy + 6} rx={3.2} ry={2.4} fill={PALETTE.cheek} opacity={0.55} />
      {/* smile */}
      <path d={`M${hx - 3},${hy + 6} Q${hx + 2},${hy + 11} ${hx + 7},${hy + 6}`} fill="none" {...line} strokeWidth={2.4} />
    </g>
  );
}

function PropShape({ prop, at }: { prop: HeldProp; at: Pt }) {
  const [x, y] = at;
  switch (prop) {
    case 'tablet':
      return (
        <g transform={`translate(${x},${y}) rotate(-6)`}>
          <rect x={-15} y={-20} width={30} height={38} rx={5} fill={PALETTE.white} {...line} />
          <rect x={-10} y={-14} width={20} height={6} rx={2} fill={PALETTE.blue} />
          <rect x={-10} y={-4} width={14} height={4} rx={2} fill={PALETTE.green} />
          <rect x={-10} y={4} width={17} height={4} rx={2} fill={PALETTE.blueLight} />
        </g>
      );
    case 'phone':
      return (
        <g transform={`translate(${x},${y}) rotate(-8)`}>
          <rect x={-7} y={-13} width={14} height={24} rx={3.5} fill={PALETTE.white} {...line} />
          <rect x={-3.5} y={-8} width={7} height={3} rx={1.5} fill={PALETTE.green} />
          <rect x={-3.5} y={-2} width={7} height={3} rx={1.5} fill={PALETTE.blue} />
        </g>
      );
    case 'mug':
      return (
        <g transform={`translate(${x},${y})`}>
          <path d="M8,-6 Q15,-6 15,0 Q15,6 8,6" fill="none" {...line} />
          <rect x={-9} y={-10} width={18} height={18} rx={4} fill={PALETTE.cream} {...line} />
          <path d="M-3,-15 q-3,-4 0,-8 M3,-15 q3,-4 0,-8" fill="none" {...line} strokeWidth={2} opacity={0.6} />
        </g>
      );
    case 'clipboard':
      return (
        <g transform={`translate(${x},${y}) rotate(-5)`}>
          <rect x={-14} y={-18} width={28} height={36} rx={4} fill={PALETTE.cream} {...line} />
          <rect x={-6} y={-22} width={12} height={7} rx={2.5} fill={PALETTE.lilacDark} {...line} />
          <path d="M-8,-6 h16 M-8,1 h16 M-8,8 h10" fill="none" {...line} strokeWidth={2.2} />
        </g>
      );
    default:
      return null;
  }
}

/** Flat, friendly comic person. Feet stand on (x, y). */
export function Person({
  x,
  y,
  scale = 1,
  shirt,
  hair,
  hairColor,
  skin,
  pose = 'stand',
  facing = 'right',
  prop,
  seat = true,
}: PersonProps) {
  const shirtFill = shirt === 'blue' ? PALETTE.blue : PALETTE.green;
  const pants = shirt === 'blue' ? PALETTE.blueDark : PALETTE.greenDark;
  const flip = facing === 'left' ? -1 : 1;
  const sitting = pose === 'sit';
  // sitting lowers the upper body by this much
  const dy = sitting ? 22 : 0;

  // shoulders
  const sL: Pt = [-17, -70 + dy];
  const sR: Pt = [17, -70 + dy];

  // arm paths: [path, hand]
  type Arm = { d: string; hand: Pt };
  const arm = (pts: Pt[]): Arm => {
    const [a, b, c] = pts;
    return { d: `M${a[0]},${a[1]} Q${b[0]},${b[1]} ${c[0]},${c[1]}`, hand: c };
  };
  // arm bent in front of the chest; the hand grips the edge of a held prop
  const holdFront = (side: 'L' | 'R'): Arm =>
    side === 'L'
      ? arm([sL, [-24, -46 + dy], [-14, -48 + dy]])
      : arm([sR, [24, -46 + dy], [14, -48 + dy]]);

  let armL: Arm = arm([sL, [-25, -52 + dy], [-24, -38 + dy]]);
  let armR: Arm = arm([sR, [25, -52 + dy], [24, -38 + dy]]);
  let extra: ReactNode = null;

  switch (pose) {
    case 'wave':
      armR = arm([sR, [34, -78 + dy], [34, -100 + dy]]);
      extra = (
        <path
          d={`M44,${-112 + dy} q5,4 5,10 M47,${-96 + dy} q4,2 5,6`}
          fill="none"
          {...line}
          strokeWidth={2.2}
        />
      );
      break;
    case 'point':
      armR = arm([sR, [32, -64 + dy], [46, -72 + dy]]);
      extra = (
        <rect x={48} y={-77 + dy} width={11} height={6} rx={3} fill={skin} {...line} strokeWidth={2.5} transform={`rotate(-14 48 ${-74 + dy})`} />
      );
      break;
    case 'thumbsUp':
      armR = arm([sR, [34, -48 + dy], [32, -70 + dy]]);
      extra = (
        <rect x={29} y={-86 + dy} width={6.5} height={12} rx={3.2} fill={skin} {...line} strokeWidth={2.5} />
      );
      break;
    case 'sit':
      // forearms reach forward to lap / desk height
      armL = arm([sL, [-8, -34], [22, -38]]);
      armR = arm([sR, [22, -32], [34, -42]]);
      break;
    default:
      break;
  }

  // prop: held at chest by a free arm
  let propAt: Pt | null = null;
  if (prop) {
    if (pose === 'stand') {
      armR = holdFront('R');
      propAt = [2, -54];
    } else if (pose === 'sit') {
      propAt = [38, -52];
    } else {
      armL = holdFront('L');
      propAt = [-2, -54];
    }
  }

  const legs = sitting ? (
    <g>
      <Limb d="M-6,-30 L26,-30 L27,-7" color={pants} width={12} />
      <Limb d="M4,-31 L38,-31 L40,-7" color={pants} width={12} />
      <ellipse cx={32} cy={-3} rx={9} ry={5} fill={PALETTE.shoe} {...line} />
      <ellipse cx={45} cy={-3} rx={9} ry={5} fill={PALETTE.shoe} {...line} />
    </g>
  ) : (
    <g>
      <Limb d="M-9,-34 L-10,-6" color={pants} width={13} />
      <Limb d="M9,-34 L10,-6" color={pants} width={13} />
      <ellipse cx={-12} cy={-3} rx={10} ry={5} fill={PALETTE.shoe} {...line} />
      <ellipse cx={12} cy={-3} rx={10} ry={5} fill={PALETTE.shoe} {...line} />
    </g>
  );

  const torsoTop = -76 + dy;
  const torsoBot = sitting ? -26 : -30;
  const torso = `M-21,${torsoBot - 4} L-19,${torsoTop + 10} Q-18,${torsoTop} -7,${torsoTop} L7,${torsoTop} Q18,${torsoTop} 19,${torsoTop + 10} L21,${torsoBot - 4} Q21,${torsoBot} 17,${torsoBot} L-17,${torsoBot} Q-21,${torsoBot} -21,${torsoBot - 4} Z`;

  return (
    <g transform={`translate(${x},${y}) scale(${scale * flip},${scale})`}>
      {sitting && seat ? (
        <g>
          <rect x={-32} y={-74} width={11} height={50} rx={5.5} fill={PALETTE.lilacDark} {...line} />
          <rect x={-28} y={-30} width={46} height={9} rx={4.5} fill={PALETTE.lilac} {...line} />
          <path d="M-5,-21 L-5,-6 M-17,-2 L7,-2" fill="none" {...line} strokeWidth={4} />
        </g>
      ) : null}
      {/* hair behind head – translated with upper body */}
      <g transform={`translate(0,${dy})`}>
        <HairBack style={hair} color={hairColor} />
      </g>
      {legs}
      <path d={torso} fill={shirtFill} {...line} />
      {/* scrub v-neck + pocket */}
      <path d={`M-7,${torsoTop + 1} L0,${torsoTop + 11} L7,${torsoTop + 1}`} fill={skin} {...line} strokeWidth={2.4} />
      <path d={`M7,${torsoTop + 22} h8 v6 q0,3 -3,3 h-2 q-3,0 -3,-3 Z`} fill="none" {...line} strokeWidth={2} opacity={0.55} />
      <g transform={`translate(0,${dy})`}>
        <Face skin={skin} />
        <HairFront style={hair} color={hairColor} />
      </g>
      <Limb d={armL.d} color={shirtFill} width={10} />
      <Limb d={armR.d} color={shirtFill} width={10} />
      {propAt && prop ? <PropShape prop={prop} at={propAt} /> : null}
      <Hand p={armL.hand} skin={skin} />
      <Hand p={armR.hand} skin={skin} />
      {extra}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Bubble
// ---------------------------------------------------------------------------

export interface BubbleProps {
  /** Top-left corner of the bubble body. */
  x: number;
  y: number;
  /** Short German text; use "\n" for a line break (max. ~3 short lines). */
  text: string;
  /** Tail direction: points down-left or down-right from the bubble. */
  tail?: 'left' | 'right' | 'none';
  fontSize?: number;
  /** Override the estimated width. */
  width?: number;
  fill?: string;
}

/** Speech bubble with short German text. */
export function Bubble({ x, y, text, tail = 'left', fontSize = 14, width, fill = PALETTE.white }: BubbleProps) {
  const lines = text.split('\n');
  const longest = Math.max(...lines.map((l) => l.length));
  // Estimated, not measured: 0.6 leaves room for wider fallback fonts.
  const w = width ?? Math.round(longest * fontSize * 0.6 + 28);
  const lh = fontSize * 1.3;
  const h = Math.round(lines.length * lh + 18);
  const tailPath =
    tail === 'left'
      ? `M${18},${h - 2} L${10},${h + 14} L${34},${h - 2}`
      : tail === 'right'
        ? `M${w - 34},${h - 2} L${w - 10},${h + 14} L${w - 18},${h - 2}`
        : null;
  return (
    <g transform={`translate(${x},${y})`}>
      {tailPath ? <path d={tailPath} fill={fill} {...line} /> : null}
      <rect x={0} y={0} width={w} height={h} rx={Math.min(16, h / 2)} fill={fill} {...line} />
      {tailPath ? (
        <path
          d={tail === 'left' ? `M20,${h - 3.5} L32,${h - 3.5}` : `M${w - 32},${h - 3.5} L${w - 20},${h - 3.5}`}
          stroke={fill}
          strokeWidth={4}
        />
      ) : null}
      <text
        x={w / 2}
        y={9 + fontSize}
        textAnchor="middle"
        fontSize={fontSize}
        fontWeight={600}
        fill={O}
      >
        {lines.map((l, i) => (
          <tspan key={i} x={w / 2} dy={i === 0 ? 0 : lh}>
            {l}
          </tspan>
        ))}
      </text>
    </g>
  );
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export type ScreenKind = 'monitor' | 'tablet' | 'phone';

const SCREEN_DEFAULT_W: Record<ScreenKind, number> = { monitor: 200, tablet: 130, phone: 64 };
const SCREEN_RATIO: Record<ScreenKind, number> = { monitor: 0.62, tablet: 1.3, phone: 1.9 };
const SCREEN_BEZEL: Record<ScreenKind, number> = { monitor: 7, tablet: 8, phone: 5 };

/** Inner (content) area of a screen in local coordinates – children are drawn there. */
export function screenInner(kind: ScreenKind, width?: number): { w: number; h: number } {
  const w = width ?? SCREEN_DEFAULT_W[kind];
  const h = Math.round(w * SCREEN_RATIO[kind]);
  const b = SCREEN_BEZEL[kind];
  return { w: w - 2 * b, h: h - 2 * b - (kind === 'phone' ? 8 : 0) };
}

export interface ScreenProps {
  kind: ScreenKind;
  /** Top-left corner of the device. */
  x: number;
  y: number;
  /** Outer width; height follows the device ratio. */
  width?: number;
  /** Screen background. */
  screen?: string;
  /** Content, in coordinates of the inner area (0,0 = top-left; size via screenInner()). */
  children?: ReactNode;
}

/** Simple device frame (monitor with stand, tablet, phone); children are clipped to the screen. */
export function Screen({ kind, x, y, width, screen = PALETTE.white, children }: ScreenProps) {
  const clipId = useSvgId('scr');
  const w = width ?? SCREEN_DEFAULT_W[kind];
  const h = Math.round(w * SCREEN_RATIO[kind]);
  const b = SCREEN_BEZEL[kind];
  const inner = screenInner(kind, w);
  const top = kind === 'phone' ? b + 4 : b;
  return (
    <g transform={`translate(${x},${y})`}>
      {kind === 'monitor' ? (
        <g>
          <path d={`M${w / 2 - 12},${h} L${w / 2 - 16},${h + 22} L${w / 2 + 16},${h + 22} L${w / 2 + 12},${h} Z`} fill={PALETTE.lilac} {...line} />
          <rect x={w / 2 - 34} y={h + 20} width={68} height={8} rx={4} fill={PALETTE.lilac} {...line} />
        </g>
      ) : null}
      <rect x={0} y={0} width={w} height={h} rx={kind === 'monitor' ? 10 : kind === 'tablet' ? 14 : 12} fill={PALETTE.outline} {...line} />
      <defs>
        <clipPath id={clipId}>
          <rect x={0} y={0} width={inner.w} height={inner.h} rx={kind === 'monitor' ? 4 : 6} />
        </clipPath>
      </defs>
      <g transform={`translate(${b},${top})`}>
        <rect x={0} y={0} width={inner.w} height={inner.h} rx={kind === 'monitor' ? 4 : 6} fill={screen} />
        <g clipPath={`url(#${clipId})`}>{children}</g>
      </g>
      {kind === 'phone' ? <rect x={w / 2 - 8} y={4} width={16} height={3} rx={1.5} fill={PALETTE.shoe} /> : null}
      {kind === 'tablet' ? <circle cx={w / 2} cy={h - b / 2} r={2} fill={PALETTE.shoe} /> : null}
    </g>
  );
}

// ---------------------------------------------------------------------------
// UiCard
// ---------------------------------------------------------------------------

export interface UiCardProps {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Short German title line, e.g. "Heute". Optional – without it a title bar is drawn. */
  title?: string;
  tint?: Tint;
  /** 'rows' = list lines with dots, 'bars' = horizontal progress bars, 'chart' = small columns. */
  variant?: 'rows' | 'bars' | 'chart';
  /** Number of rows/bars/columns (default 3). */
  count?: number;
  /** Optional check mark badge in the top-right corner. */
  check?: boolean;
  outline?: boolean;
}

/** Rounded pastel card suggesting app UI. */
export function UiCard({
  x,
  y,
  w,
  h,
  title,
  tint = 'blue',
  variant = 'rows',
  count = 3,
  check = false,
  outline = true,
}: UiCardProps) {
  const t = TINTS[tint];
  const pad = Math.max(8, Math.round(w * 0.08));
  const titleH = Math.max(12, Math.min(18, h * 0.22));
  const bodyY = pad + titleH + 6;
  const bodyH = h - bodyY - pad;
  const rows = Array.from({ length: count }, (_, i) => i);
  const widths = [0.85, 0.6, 0.72, 0.5, 0.78, 0.66];
  const stroke = outline ? line : { stroke: 'none' };
  return (
    <g transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={w} height={h} rx={Math.min(14, h / 4)} fill={t.bg} {...stroke} />
      {title ? (
        <text x={pad} y={pad + titleH * 0.8} fontSize={titleH * 0.85} fontWeight={700} fill={O}>
          {title}
        </text>
      ) : (
        <rect x={pad} y={pad + 2} width={w * 0.45} height={titleH * 0.6} rx={titleH * 0.3} fill={t.bar} />
      )}
      {check ? (
        <g transform={`translate(${w - pad - 8},${pad + titleH / 2})`}>
          <circle r={8} fill={PALETTE.green} {...line} strokeWidth={2.2} />
          <path d="M-3.5,0 L-1,2.8 L4,-3" fill="none" {...line} strokeWidth={2.2} />
        </g>
      ) : null}
      {variant === 'chart'
        ? rows.map((i) => {
            const cw = (w - 2 * pad) / count;
            const bh = bodyH * (0.35 + 0.65 * (((i * 37) % 10) / 10));
            return (
              <rect
                key={i}
                x={pad + i * cw + cw * 0.18}
                y={bodyY + bodyH - bh}
                width={cw * 0.64}
                height={bh}
                rx={Math.min(4, cw * 0.2)}
                fill={i % 2 ? t.barSoft : t.bar}
              />
            );
          })
        : rows.map((i) => {
            const rh = bodyH / count;
            const cy = bodyY + rh * i + rh / 2;
            const barH = Math.max(4, Math.min(9, rh * 0.45));
            if (variant === 'bars') {
              const full = w - 2 * pad;
              return (
                <g key={i}>
                  <rect x={pad} y={cy - barH / 2} width={full} height={barH} rx={barH / 2} fill={PALETTE.white} />
                  <rect x={pad} y={cy - barH / 2} width={full * widths[i % widths.length]} height={barH} rx={barH / 2} fill={t.bar} />
                </g>
              );
            }
            return (
              <g key={i}>
                <circle cx={pad + barH / 2} cy={cy} r={barH / 2 + 0.5} fill={t.bar} />
                <rect
                  x={pad + barH + 6}
                  y={cy - barH / 2}
                  width={(w - 2 * pad - barH - 6) * widths[i % widths.length]}
                  height={barH}
                  rx={barH / 2}
                  fill={PALETTE.white}
                />
              </g>
            );
          })}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Sparkle & Plant
// ---------------------------------------------------------------------------

export interface SparkleProps {
  x: number;
  y: number;
  size?: number;
  color?: string;
}

/** Four-pointed sparkle star. */
export function Sparkle({ x, y, size = 12, color = PALETTE.sun }: SparkleProps) {
  const s = size;
  const k = s * 0.28;
  return (
    <path
      d={`M${x},${y - s} Q${x + k},${y - k} ${x + s},${y} Q${x + k},${y + k} ${x},${y + s} Q${x - k},${y + k} ${x - s},${y} Q${x - k},${y - k} ${x},${y - s} Z`}
      fill={color}
      {...line}
      strokeWidth={2.2}
    />
  );
}

export interface PlantProps {
  /** Bottom centre of the pot. */
  x: number;
  y: number;
  scale?: number;
  pot?: string;
}

/** Potted plant with rounded leaves. */
export function Plant({ x, y, scale = 1, pot = PALETTE.coral }: PlantProps) {
  return (
    <g transform={`translate(${x},${y}) scale(${scale})`}>
      <path d="M0,-30 Q-2,-50 0,-62" fill="none" {...line} />
      <path d="M0,-38 Q-22,-40 -24,-60 Q-4,-60 0,-38 Z" fill={PALETTE.green} {...line} />
      <path d="M0,-44 Q20,-46 24,-68 Q4,-68 0,-44 Z" fill={PALETTE.greenDark} {...line} />
      <path d="M0,-58 Q-10,-70 0,-82 Q10,-70 0,-58 Z" fill={PALETTE.green} {...line} />
      <path d="M-16,-30 L16,-30 L12,-2 Q11,0 8,0 L-8,0 Q-11,0 -12,-2 Z" fill={pot} {...line} />
      <rect x={-19} y={-34} width={38} height={9} rx={4} fill={pot} {...line} />
    </g>
  );
}
