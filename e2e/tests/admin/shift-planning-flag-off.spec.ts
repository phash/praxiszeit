import { test, expect } from '../../fixtures/base.fixture';

/**
 * Schichtplanung (#305) — negativer Gegentest zum Feature-Flag.
 *
 * #451: extrahiert aus shift-planning.spec.ts. Alle anderen
 * Schichtplanungs-Specs verlassen sich darauf, dass die mandantenweite
 * Einstellung `shift_planning_enabled` für die Dauer des GESAMTEN
 * Playwright-Laufs an ist (siehe global-setup.ts) — genau DAS ist ihre
 * Isolation gegen den in #451 beschriebenen 404-Wettlauf. Dieser Test ist
 * die eine bewusste Ausnahme: sein Zweck ist zu belegen, dass die Router und
 * die Navigation korrekt reagieren, wenn das Flag AUS ist, schaltet es also
 * zwangsläufig zwischenzeitlich ab.
 *
 * Damit das die anderen vier Specs nicht wieder in denselben 404-Wettlauf
 * schickt, lebt dieser Test in einem eigenen Playwright-Projekt
 * ("shift-planning-flag-off", siehe playwright.config.ts für die ausführliche
 * Abwägung gegen die Alternative "im `finally` sofort wieder einschalten"),
 * das per `dependencies: ['shift-planning']` garantiert erst startet, nachdem
 * alle vier "echten" Schichtplanungs-Specs vollständig durchgelaufen sind —
 * kein Worker kann während dieses Tests noch eine Schichtplanungs-Anfrage im
 * selben Mandanten stellen. Das `finally` schaltet das Flag trotzdem sofort
 * wieder ein (statt bis zum globalTeardown auszuschalten) — reiner
 * Aufräum-Reflex, kein Isolationsmechanismus: sollte dieser Test je isoliert
 * (z. B. per `--project=shift-planning-flag-off` oder Dateifilter ohne die
 * anderen vier) laufen, bleibt das Flag danach nicht fälschlich aus.
 */
test.describe('Schichtplanung (#305) — Flag aus', () => {
  test('feature hidden + endpoints 404 when flag is off', async ({ adminPage, adminApi }) => {
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'false' });

    try {
      // API gate: 404 when off.
      const res = await adminApi.getRaw('/shift-planning/plans');
      expect(res.status).toBe(404);

      // Nav entry hidden after reload.
      await adminPage.goto('/');
      await adminPage.reload();
      await expect(adminPage.getByRole('link', { name: 'Schichtplanung' })).toHaveCount(0);
    } finally {
      await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'true' });
    }
  });
});
