/**
 * Gegenstück zu global-setup.ts (#451): schaltet `shift_planning_enabled`
 * nach dem letzten Test des gesamten Playwright-Laufs wieder aus.
 *
 * Läuft unabhängig davon, ob einzelne Tests fehlgeschlagen sind — Playwright
 * ruft globalTeardown immer auf, wenn globalSetup erfolgreich war. Best
 * effort: schlägt der Login hier fehl (z. B. Backend down), soll das den
 * Exit-Code des Testlaufs nicht verschlucken oder verschlimmern.
 */
import { ApiHelper } from './helpers/api.helper';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

export default async function globalTeardown(): Promise<void> {
  try {
    const api = new ApiHelper();
    await api.login(ADMIN_USER, ADMIN_PASS);
    await api.put('/admin/settings/shift_planning_enabled', { value: 'false' });
  } catch {
    /* best effort — do not fail the whole run over teardown cleanup */
  }
}
