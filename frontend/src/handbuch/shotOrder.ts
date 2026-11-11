import type { ShotDef } from './types';

/**
 * Reihenfolge der Aufnahme (e2e/handbuch/capture.ts, Ruling R36).
 *
 * Jede Einstellungsaenderung eines Shots (`settings`) und jede Seite mit Seiteneffekt
 * schreibt Zeilen ins Aenderungsprotokoll bzw. in die Konto-Vorgaenge. Shots, die genau
 * dieses Protokoll zeigen (Route /admin/audit-log), laufen deshalb VOR allen anderen,
 * sonst haengt ihr Bild davon ab, welche Shots vorher gelaufen sind (ein `--only`-Lauf
 * sah 2 Zeilen, der volle Lauf mehr). Sonst bleibt die Reihenfolge der Inhalte.
 */
export function readsAuditLog(def: ShotDef): boolean {
  return def.route.split(/[?#]/)[0].startsWith('/admin/audit-log');
}

export function orderShots(defs: readonly ShotDef[]): ShotDef[] {
  return [...defs.filter(readsAuditLog), ...defs.filter((d) => !readsAuditLog(d))];
}
