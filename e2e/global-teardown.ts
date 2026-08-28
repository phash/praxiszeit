/**
 * Gegenstück zu global-setup.ts (#451): stellt `shift_planning_enabled` nach
 * dem letzten Test des gesamten Playwright-Laufs auf den Wert zurück, den die
 * Instanz VOR dem Lauf hatte.
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
import { PREV_FLAG_ENV, SETUP_DONE_ENV } from './global-setup';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

export default async function globalTeardown(): Promise<void> {
  if (process.env[SETUP_DONE_ENV] !== '1') return;
  const previous = process.env[PREV_FLAG_ENV] ?? 'false';
  try {
    const api = new ApiHelper();
    await api.login(ADMIN_USER, ADMIN_PASS);
    await api.put('/admin/settings/shift_planning_enabled', { value: previous });
  } catch {
    /* best effort — do not fail the whole run over teardown cleanup */
  }
}
