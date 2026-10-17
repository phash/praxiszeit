import { test, expect } from '../../fixtures/base.fixture';
import { weekdayFromNow } from '../../helpers/date.helper';

/**
 * Mitarbeitende bearbeiten ihre offenen Urlaubsanträge („Meine Anträge").
 *
 * Gesamtreview 1.20 (B9): die beiden Tests standen in employee/absences.spec.ts
 * und schalteten dort die mandantenweite Genehmigungspflicht
 * (`vacation_approval_required`) ein und wieder aus — bei `workers: 2` neben
 * Specs, die als Mitarbeiter:in Urlaub direkt buchen (→ 400 bei aktiver
 * Pflicht) oder die Pflicht selbst abschalten (→ 400 beim Antrag). Ein
 * `catch { test.skip() }` um das Anlegen des Antrags verschluckte genau diesen
 * Wettlauf: der Test wurde still übersprungen statt rot.
 *
 * Jetzt im Projekt "tenant-settings" (erst nach "chromium", Dateien einzeln
 * nacheinander, playwright.config.ts) — der Wettlauf entfällt, ein Fehlschlag
 * beim Einschalten oder Anlegen ist ein Fehler. Ausgangswert ist `false`
 * (global-setup.ts); das afterEach schreibt ihn zurück.
 */
test.describe('Eigene Urlaubsanträge bearbeiten (Genehmigungspflicht an)', () => {
  test.beforeEach(async ({ adminApi }) => {
    await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
  });

  test.afterEach(async ({ adminApi }) => {
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' });
    } catch { /* best effort */ }
  });

  test('employee edits own pending vacation request — hours', async ({
    employeePage,
    createVacationRequest,
  }) => {
    const startDate = weekdayFromNow(48);
    const uniqueNote = `E2E self-edit ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createVacationRequest({
      date: startDate,
      hours: 8,
      note: uniqueNote,
    });

    // Reload so the page picks up the enabled approval setting
    // (the "Meine Anträge" tab is only rendered when vacation_approval_required=true).
    await employeePage.goto('/absences');
    await employeePage.waitForLoadState('networkidle');

    // Switch to "Meine Anträge".
    await employeePage.getByRole('button', { name: /Meine Anträge/ }).click();
    await employeePage.waitForLoadState('networkidle');

    const card = employeePage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });

    // Pencil button is icon-only with title="Antrag bearbeiten"
    await card.getByRole('button', { name: 'Antrag bearbeiten' }).click();

    const dialog = employeePage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Change hours to 6
    const hoursInput = dialog.locator('input[type="number"]').first();
    await hoursInput.fill('6');
    await dialog.getByRole('button', { name: 'Speichern' }).click();

    // Toast confirms
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /aktualisiert/ })
    ).toBeVisible({ timeout: 10000 });

    // Re-open the modal and verify the hours value persisted as 6.
    await employeePage.waitForLoadState('networkidle');
    const cardAfter = employeePage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(cardAfter).toBeVisible({ timeout: 5000 });
    await cardAfter.getByRole('button', { name: 'Antrag bearbeiten' }).click();

    const dialogAfter = employeePage.getByRole('dialog');
    await expect(dialogAfter).toBeVisible({ timeout: 5000 });
    const hoursAfter = dialogAfter.locator('input[type="number"]').first();
    await expect(hoursAfter).toHaveValue('6');
    await dialogAfter.getByRole('button', { name: 'Abbrechen' }).click();
    // Den Antrag selbst räumt die Fixture ab.
  });

  test('edit modal shows initial values from the existing request', async ({
    employeePage,
    createVacationRequest,
  }) => {
    // Spec section 5: "Modal zeigt Initialwerte"
    const startDate = weekdayFromNow(54);
    const uniqueNote = `E2E prefill ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createVacationRequest({
      date: startDate,
      hours: 7,
      absence_type: 'training',
      note: uniqueNote,
    });

    await employeePage.goto('/absences');
    await employeePage.waitForLoadState('networkidle');
    await employeePage.getByRole('button', { name: /Meine Anträge/ }).click();
    await employeePage.waitForLoadState('networkidle');

    const card = employeePage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Antrag bearbeiten' }).click();

    const dialog = employeePage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // All four user-facing fields must reflect the existing request.
    await expect(dialog.locator('input[type="date"]').first()).toHaveValue(startDate);
    await expect(dialog.locator('input[type="number"]').first()).toHaveValue('7');
    await expect(dialog.locator('select').first()).toHaveValue('training');
    await expect(dialog.locator('input[type="text"]').first()).toHaveValue(uniqueNote);

    await dialog.getByRole('button', { name: 'Abbrechen' }).click();
  });
});
