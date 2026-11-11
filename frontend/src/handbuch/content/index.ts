import type { Handbook, HandbookId, ShotDef } from '../types';
import { mitarbeitende } from './mitarbeitende';
import { praxisleitung } from './praxisleitung';

/** Noch nicht geschriebene Handbuecher: leere Kapitel (der Markdown-Generator ueberspringt sie). */
function placeholder(id: HandbookId, title: string): Handbook {
  return { id, title, lead: '', chapters: [], shots: [] };
}

/** Die Handbuecher; Task 9b ff. fuellen die übrigen Kapitel und Platzhalter. */
export const HANDBOOKS: Record<HandbookId, Handbook> = {
  mitarbeitende,
  praxisleitung,
  'so-rechnet': placeholder('so-rechnet', 'So rechnet PraxisZeit'),
};

/** Alle Aufnahmen aller Handbuecher. */
export const ALL_SHOTS: ShotDef[] = Object.values(HANDBOOKS).flatMap((h) => h.shots);
