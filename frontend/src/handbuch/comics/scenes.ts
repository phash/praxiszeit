import type { ComponentType } from 'react';
import { SceneHero } from './SceneHero';
import { SceneStempeln } from './SceneStempeln';
import { SceneUebersicht } from './SceneUebersicht';
import { SceneUrlaub } from './SceneUrlaub';
import { SceneNachweise } from './SceneNachweise';

/** Comic-Szenen der Broschüre, adressiert über den Schlüssel `scene` in den Handbuch-Inhalten. */
export const COMIC_SCENES: Record<string, ComponentType> = {
  hero: SceneHero,
  stempeln: SceneStempeln,
  uebersicht: SceneUebersicht,
  urlaub: SceneUrlaub,
  nachweise: SceneNachweise,
};
