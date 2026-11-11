import type { Handbook, HandbookId, ShotDef } from '../types';
import { mitarbeitende } from './mitarbeitende';

/** Noch nicht geschriebene Handbuecher: leere Kapitel (der Markdown-Generator ueberspringt sie). */
function placeholder(id: HandbookId, title: string): Handbook {
  return { id, title, lead: '', chapters: [], shots: [] };
}

/** Die Handbuecher; Task 8b ff. fuellen die Platzhalter. */
export const HANDBOOKS: Record<HandbookId, Handbook> = {
  mitarbeitende,
  praxisleitung: placeholder('praxisleitung', 'Handbuch für die Praxisleitung'),
  'so-rechnet': placeholder('so-rechnet', 'So rechnet PraxisZeit'),
};

/** Alle Aufnahmen aller Handbuecher. */
export const ALL_SHOTS: ShotDef[] = Object.values(HANDBOOKS).flatMap((h) => h.shots);
