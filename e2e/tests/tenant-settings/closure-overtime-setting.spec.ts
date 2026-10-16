import { test, expect } from '../../fixtures/base.fixture';

/**
 * #314 Betriebsferien-Überstundenabbau-Schalter (`closure_overtime_after_vacation`).
 *
 * Gesamtreview 1.20 (B9): der Test stand in new-features-2026-06.spec.ts im
 * Projekt "chromium", schaltete die mandantenweite Einstellung um und schrieb
 * den Ausgangswert nie zurück — jeder Lauf kippte sie auf der Instanz, und
 * parallel angelegte Betriebsferien (admin/absences.spec.ts) buchten je nach
 * Zeitpunkt Urlaub oder Überstundenausgleich. Jetzt im Projekt
 * "tenant-settings" (erst nach "chromium", Dateien einzeln nacheinander,
 * playwright.config.ts) und mit Rückschreiben im `finally`.
 */
test.describe('#314 Betriebsferien-Überstundenabbau-Schalter', () => {
  test('toggle the closure-overtime setting and persist it', async ({ adminPage, adminApi }) => {
    await adminPage.goto('/admin/settings');
    await expect(adminPage.getByRole('heading', { name: 'Betriebsferien & Urlaub' })).toBeVisible();
    const toggle = adminPage.locator('#closure-overtime-toggle');
    await expect(toggle).toBeVisible();
    const before = (await toggle.getAttribute('aria-checked')) === 'true' ? 'true' : 'false';
    try {
      await toggle.click();
      const saveResp = adminPage.waitForResponse(
        (r) => r.url().includes('/api/admin/settings/closure_overtime_after_vacation') && r.request().method() === 'PUT',
      );
      // the section's own Speichern button (last "Betriebsferien & Urlaub" block)
      await adminPage.locator('div', { has: adminPage.getByRole('heading', { name: 'Betriebsferien & Urlaub' }) })
        .last().getByRole('button', { name: 'Speichern' }).click();
      const resp = await saveResp;
      expect(resp.ok()).toBeTruthy();
      await expect(toggle).toHaveAttribute('aria-checked', String(before !== 'true'));

      // Persistenz über die API, nicht nur der Zustand des Schalters.
      const settings = await adminApi.get('/admin/settings');
      const saved = settings.find((s: any) => s.key === 'closure_overtime_after_vacation');
      expect(saved?.value).toBe(before === 'true' ? 'false' : 'true');
    } finally {
      try {
        await adminApi.put('/admin/settings/closure_overtime_after_vacation', { value: before });
      } catch { /* best effort */ }
    }
  });
});
