import { test } from '../../fixtures/base.fixture';

/**
 * Visuelle Belege (Screenshots) der seit 1.6.0 neuen/geänderten Bildschirme
 * für die manuelle Sichtprüfung des Prod-Release. Keine Assertions — die
 * funktionalen Checks liegen in den anderen Specs. Screenshots landen in
 * /tmp/pz-shots (im Repo-Verzeichnis nicht beschreibbar / root-owned).
 */
const SHOTS = '/tmp/pz-shots';

test.describe('Visual: Prod-Release-Bildschirme seit 1.6.0', () => {
  test('Benutzerübersicht mit Überstunden-Spalte (#194)', async ({ adminPage }) => {
    await adminPage.goto('/admin/users');
    await adminPage.getByRole('heading', { name: 'Benutzerverwaltung' }).waitFor();
    await adminPage.waitForTimeout(800);
    await adminPage.screenshot({ path: `${SHOTS}/01-users-overview.png`, fullPage: true });
  });

  test('Benutzerformular: Flags + Soll-Arbeitszeit-Fenster (#189/#191/#201)', async ({ adminPage }) => {
    await adminPage.goto('/admin/users');
    await adminPage.getByRole('button', { name: 'Neue:r Mitarbeiter:in' }).click();
    await adminPage.locator('#track_hours').waitFor();
    await adminPage.waitForTimeout(400);
    await adminPage.screenshot({ path: `${SHOTS}/02-userform-flags-workwindow.png`, fullPage: true });
  });

  test('Einstellungen: Soll-Fenster-Puffer + Sondertage (#201/#188)', async ({ adminPage }) => {
    await adminPage.goto('/admin/settings');
    await adminPage.getByRole('heading', { name: 'Einstellungen' }).waitFor();
    await adminPage.waitForTimeout(800);
    await adminPage.screenshot({ path: `${SHOTS}/03-settings-workwindow-specialdays.png`, fullPage: true });
  });

  test('Abwesenheitskalender (Sondertage 24./31.12., #188) — Dezember', async ({ adminPage }) => {
    await adminPage.goto('/admin/absences');
    await adminPage.waitForTimeout(1500);
    await adminPage.screenshot({ path: `${SHOTS}/04-absence-calendar.png`, fullPage: true });
  });

  test('Mitarbeiter-Dashboard: Stempeluhr (#199 Pause beim Ausstempeln)', async ({ employeePage }) => {
    await employeePage.goto('/dashboard');
    await employeePage.waitForTimeout(1200);
    await employeePage.screenshot({ path: `${SHOTS}/05-employee-dashboard-stamp.png`, fullPage: true });
  });
});
