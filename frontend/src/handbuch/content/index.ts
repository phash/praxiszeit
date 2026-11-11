import type { Handbook, HandbookId, ShotDef } from '../types';
import { mitarbeitende } from './mitarbeitende';
import { praxisleitung } from './praxisleitung';
import { soRechnet } from './so-rechnet';

/** Die Handbuecher. */
export const HANDBOOKS: Record<HandbookId, Handbook> = {
  mitarbeitende,
  praxisleitung,
  'so-rechnet': soRechnet,
};

/** Alle Aufnahmen aller Handbuecher. */
export const ALL_SHOTS: ShotDef[] = Object.values(HANDBOOKS).flatMap((h) => h.shots);
