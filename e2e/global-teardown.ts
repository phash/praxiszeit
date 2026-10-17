/**
 * Gegenstück zu global-setup.ts (#451): stellt die dort besessenen
 * mandantenweiten Einstellungen (`OWNED_SETTINGS`: `shift_planning_enabled`,
 * seit Gesamtreview 1.20 B9 auch `vacation_approval_required`) nach dem letzten
 * Test des gesamten Playwright-Laufs auf den Wert zurück, den die Instanz VOR
 * dem Lauf hatte.
 *
 * #461 W-2: Vorher schrieb dieser Teardown hart `false` — unabhängig davon, wie
 * die Einstellung vorher stand und ob überhaupt ein Test lief. Playwright
 * stellt den Teardown zudem VOR das Setup in die Aufgabenliste; ein
 * gescheitertes Setup endete damit trotzdem in einem erzwungenen `false`. Beides
 * ist behoben: zurückgeschrieben wird der gemerkte Wert, und nur dann, wenn das
 * Setup nachweislich durchlief.
 *
 * Läuft unabhängig davon, ob einzelne Tests fehlgeschlagen sind. Best effort:
 * schlägt der Login hier fehl (z. B. Backend down), soll das den Exit-Code des
 * Testlaufs nicht verschlucken oder verschlimmern.
 */
import { ApiHelper } from './helpers/api.helper';
import { PREV_SETTINGS_ENV } from './global-setup';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

export default async function globalTeardown(): Promise<void> {
  // Nur zurückschreiben, was das Setup nachweislich geschrieben hat.
  let previous: Record<string, string> = {};
  try {
    previous = JSON.parse(process.env[PREV_SETTINGS_ENV] ?? '{}');
  } catch {
    return;
  }
  if (Object.keys(previous).length === 0) return;
  try {
    const api = new ApiHelper();
    await api.login(ADMIN_USER, ADMIN_PASS);
    for (const [key, value] of Object.entries(previous)) {
      try {
        await api.put(`/admin/settings/${key}`, { value });
      } catch {
        /* best effort — die übrigen Einstellungen trotzdem zurückschreiben */
      }
    }
  } catch {
    /* best effort — do not fail the whole run over teardown cleanup */
  }
}
