import { test, expect } from '../../fixtures/base.fixture';

/**
 * #201 — mandantenweiter Puffer `work_window_grace_minutes` in den Einstellungen.
 *
 * Extrahiert aus prod-release-features.spec.ts (Review Task 22, Muster #451):
 * dieser Test schaltet den Puffer für einige Sekunden auf 20 bzw. 25. Anlegen
 * eines Zeiteintrags (`admin_time_entries`) und die Neukappung bei einer
 * Arbeitszeit-Änderung (`wh_change_service`) lesen jeweils den AKTUELLEN
 * Mandantenwert — work-blocks.spec.ts rechnet seine erwarteten Werte („1:30 h
 * zwischen den Blöcken nicht angerechnet", „Nicht angerechnet (Lücke): 2:30 h")
 * mit dem Puffer 15. Liefe dieser Test im selben Projekt wie work-blocks.spec.ts
 * (`workers: 2`), träfe ein paralleler Worker gelegentlich den geänderten Wert
 * und stünde rot da, ohne beteiligt zu sein.
 *
 * Deshalb lebt der Test in einem eigenen Playwright-Projekt ("grace-setting",
 * siehe playwright.config.ts), das per `dependencies: ['chromium']` garantiert
 * erst startet, nachdem alle Specs des Projekts "chromium" durchgelaufen sind.
 * Das `finally` schreibt den Originalwert trotzdem sofort zurück — reiner
 * Aufräum-Reflex, kein Isolationsmechanismus.
 *
 * Ein Dateifilter auf diese Spec startet das ganze Projekt "chromium" mit;
 * gezielt allein: `npx playwright test tests/admin/grace-setting.spec.ts --no-deps`.
 */
test.describe('Soll-Fenster-Puffer (#201)', () => {
  test('#201: Soll-Fenster-Puffer lässt sich in den Einstellungen speichern', async ({ adminPage, adminApi }) => {
    // Originalwert merken, um ihn am Ende wiederherzustellen
    let original = '15';
    try {
      const settings = await adminApi.get('/admin/settings');
      const grace = settings.find((s: any) => s.key === 'work_window_grace_minutes');
      if (grace?.value) original = String(grace.value);
    } catch { /* default 15 */ }

    const newValue = original === '20' ? '25' : '20';
    try {
      await adminPage.goto('/admin/settings');
      await expect(adminPage.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();

      const input = adminPage.locator('#grace-minutes');
      await expect(input).toBeVisible();
      await input.fill(newValue);
      // Scope to the "Soll-Arbeitszeit-Fenster" section — every settings card
      // has its own "Speichern" button.
      const graceSection = adminPage.locator('div.bg-white', {
        has: adminPage.getByRole('heading', { name: 'Soll-Arbeitszeit-Fenster' }),
      });
      await graceSection.getByRole('button', { name: 'Speichern' }).click();

      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'Puffer gespeichert' })
      ).toBeVisible({ timeout: 10000 });

      const after = await adminApi.get('/admin/settings');
      const grace = after.find((s: any) => s.key === 'work_window_grace_minutes');
      expect(String(grace.value)).toBe(newValue);
    } finally {
      // Originalwert zurückschreiben
      try {
        await adminApi.put('/admin/settings/work_window_grace_minutes', { value: original });
      } catch { /* best effort */ }
    }
  });
});
