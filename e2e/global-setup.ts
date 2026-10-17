/**
 * Globaler Besitzer der mandantenweiten Einstellungen `shift_planning_enabled`
 * (#451) und `vacation_approval_required` (Gesamtreview 1.20 B9, siehe
 * OWNED_SETTINGS).
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
 * global-teardown.ts stellt danach den VORHERIGEN Wert wieder her. Die vier
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
 *
 * #461 W-2: Das Setup LIEST den bisherigen Wert und hinterlegt ihn für den
 * Teardown. Vorher schrieb der Teardown hart `false` — ein Lauf, der gar
 * keinen Test ausführte (`--grep` ohne Treffer, ein Einzeldatei-Filter, ein
 * `--project=chromium`), schaltete die Schichtplanung auf der Instanz ab, auf
 * der er lief. `local-ci.sh` fährt E2E gegen die Entwicklungsinstanz und deren
 * echte Datenbank: die Daten überlebten, waren aber unerreichbar, bis jemand
 * von Hand zurückschaltete.
 */
import { ApiHelper } from './helpers/api.helper';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

/**
 * Mandantenweite Einstellungen, die der Lauf für seine GESAMTE Dauer besitzt,
 * mit dem Wert, den alle Specs voraussetzen.
 *
 * Gesamtreview 1.20 (B9), dasselbe Muster für `vacation_approval_required`:
 * bisher schalteten vacation-approvals.spec.ts, settings.spec.ts,
 * employee/absences.spec.ts und user-management.spec.ts die
 * Genehmigungspflicht in eigenen Tests/Hooks an und aus — bei `workers: 2`
 * über Dateien hinweg gleichzeitig. Ein Urlaubsantrag (`POST /vacation-requests`
 * → 400 „Urlaubsanträge sind nicht aktiviert") bzw. eine Direktbuchung als
 * Mitarbeiter:in (→ 400 „Urlaub ist genehmigungspflichtig") scheiterte dann
 * an der Einstellung einer fremden Datei. Jetzt gilt im Projekt „chromium"
 * durchgehend `false`; die Specs, die eine mandantenweite Einstellung
 * umschalten, liegen in tests/tenant-settings/ und laufen erst danach,
 * einzeln nacheinander (playwright.config.ts). Ihr Aufräumen schreibt den hier
 * gesetzten Wert zurück.
 */
export const OWNED_SETTINGS: Readonly<Record<string, string>> = {
  shift_planning_enabled: 'true',
  vacation_approval_required: 'false',
};

/**
 * Vom Teardown gelesen (JSON `{key: vorheriger Wert}`): NUR die Einstellungen,
 * die das Setup tatsächlich geschrieben hat, mit dem Wert VOR dem Lauf.
 */
export const PREV_SETTINGS_ENV = 'E2E_PREV_TENANT_SETTINGS';

export default async function globalSetup(): Promise<void> {
  const api = new ApiHelper();
  await api.login(ADMIN_USER, ADMIN_PASS);

  // Fehlt die Zeile ganz, ist der wirksame Wert bei beiden Schaltern der
  // Default `false` — das Zurückschreiben von 'false' ist dazu gleichbedeutend
  // (es gibt keinen Endpunkt, der eine Einstellung wieder entfernt).
  delete process.env[PREV_SETTINGS_ENV];
  const settings: { key: string; value: string }[] = await api.get('/admin/settings');
  const written: Record<string, string> = {};
  for (const [key, value] of Object.entries(OWNED_SETTINGS)) {
    const prev = settings.find((s) => s.key === key)?.value ?? 'false';
    await api.put(`/admin/settings/${key}`, { value });
    // Erst NACH dem erfolgreichen Schreiben vormerken: scheitert das Setup
    // vorher (429 beim Login, Backend unten, Read-only-Lizenz), hat es die
    // Einstellung nicht angefasst und der Teardown darf sie ebenfalls nicht
    // anfassen.
    written[key] = prev;
    process.env[PREV_SETTINGS_ENV] = JSON.stringify(written);
  }
}
