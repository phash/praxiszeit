import type { Handbook, HandbookId, ShotDef } from '../types';
import { PROBE_SHOTS } from './_probe';

/** Alle Aufnahmen aller Handbuecher (Task 8 ergaenzt HANDBOOKS). */
export const ALL_SHOTS: ShotDef[] = [...PROBE_SHOTS];

/** Die Handbuecher; Task 8ff. fuellen sie. Leer = der Markdown-Generator ueberspringt sie. */
export const HANDBOOKS: Partial<Record<HandbookId, Handbook>> = {};
