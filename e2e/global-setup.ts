/**
 * Globaler Besitzer der mandantenweiten Einstellung `shift_planning_enabled`
 * (#451).
 *
 * Vorher schaltete jede der vier Schichtplanungs-Specs (shift-planning.spec.ts,
 * shift-planning-m2.spec.ts, shift-planning-followups.spec.ts,
 * shift-planning-visibility.spec.ts) das Flag in ihren eigenen beforeEach/
 * afterEach/afterAll-Hooks selbst an und aus. `playwright.config.ts` fährt
 * mit `workers: 2` bei `fullyParallel: false` — seriell also nur *innerhalb*
 * einer Datei, nicht über Dateien hinweg. Schaltete Datei B das Flag ab,
 * während Datei A gerade eine Schichtplanungs-Anfrage stellte, antwortete
 * der komplette Router mit 404 (der Feature-Flag-Guard in
 * `shift_planning.py` kennt keine Test-Grenzen).
 *
 * Jetzt gibt es genau EINEN Besitzer für den gesamten Playwright-Lauf: dieses
 * globalSetup schaltet das Flag einmal ein, bevor irgendein Test startet;
 * global-teardown.ts schaltet es nach dem letzten Test wieder aus. Die vier
 * Specs selbst fassen das Flag nicht mehr an (siehe deren Kommentare).
 *
 * Die einzige Ausnahme ist der bewusst negative Test in
 * shift-planning-flag-off.spec.ts ("feature hidden + endpoints 404 when flag
 * is off") — der MUSS das Flag zwischenzeitlich abschalten, um genau das zu
 * belegen. Er lebt deshalb in einer eigenen Datei, die über eine
 * Playwright-Projekt-Abhängigkeit (`dependencies` in playwright.config.ts,
 * dort auch die Abwägung gegen die Alternative "sofort wieder einschalten")
 * garantiert erst startet, nachdem alle vier oben genannten Specs
 * vollständig durchgelaufen sind — kein Worker kann ihm mehr in die Quere
 * kommen.
 */
import { ApiHelper } from './helpers/api.helper';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

export default async function globalSetup(): Promise<void> {
  const api = new ApiHelper();
  await api.login(ADMIN_USER, ADMIN_PASS);
  await api.put('/admin/settings/shift_planning_enabled', { value: 'true' });
}
