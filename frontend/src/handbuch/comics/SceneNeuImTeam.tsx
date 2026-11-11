/**
 * Szene „Neu im Team“: Die Praxisleitung legt am Tablet ein Konto für eine neue
 * Kollegin an (Benutzername, Wochenstunden, Urlaub); die neue Kollegin winkt.
 */
import { CAST, Bubble, ComicSvg, PALETTE, Person, Plant, Sparkle, UiCard } from './ComicKit';

const FLOOR = 350;

export function SceneNeuImTeam({ className }: { className?: string }) {
  return (
    <ComicSvg
      viewBox="0 0 640 380"
      title="Neu im Team: Die Praxisleitung legt für eine neue Kollegin ein Konto mit Benutzername, Wochenstunden und Urlaubstagen an. Die neue Kollegin winkt zur Begrüßung."
      className={className}
      background={PALETTE.cream}
    >
      <rect x={14} y={FLOOR} width={612} height={14} rx={7} fill={PALETTE.mint} />

      {/* „Formular“ als große Karte zwischen den beiden */}
      <UiCard x={214} y={110} w={210} h={150} title="Neue:r Mitarbeiter:in" tint="blue" variant="rows" count={4} check />
      <Sparkle x={436} y={104} size={12} />

      <Person x={120} y={FLOOR} scale={1.15} {...CAST.bea} pose="point" facing="right" prop="tablet" />
      <Bubble x={20} y={24} text={'Konto, Stunden,\nUrlaub – fertig.'} tail="left" fontSize={15} />

      <Person x={530} y={FLOOR} scale={1.15} {...CAST.anna} pose="wave" facing="left" />
      <Bubble x={464} y={36} text="Hallo zusammen!" tail="right" fontSize={15} />

      <Plant x={330} y={FLOOR} scale={0.8} />
    </ComicSvg>
  );
}
