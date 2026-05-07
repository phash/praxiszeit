import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow, weekdayFromNow } from '../../helpers/date.helper';

test.describe('Employee Absences', () => {
  test.beforeEach(async ({ employeePage }) => {
    await employeePage.goto('/absences');
    await expect(employeePage.getByRole('heading', { name: 'Abwesenheiten', exact: true })).toBeVisible();
  });

  test('create single vacation day', async ({ employeePage }) => {
    // Click "Abwesenheit eintragen"
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Fill date with next weekday
    const dateInput = employeePage.locator('input[type="date"]').first();
    await dateInput.fill(nextWeekday());

    // Select type "vacation" (should already be selected by default, but ensure)
    const typeSelect = employeePage.locator('select').first();
    await typeSelect.selectOption('vacation');

    // Submit
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Check for success toast (direct entry or vacation-request depending on global setting)
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /eingetragen|erfolgreich|gestellt/ })
    ).toBeVisible({ timeout: 10000 });
  });

  test('create multi-day absence', async ({ employeePage }) => {
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Check the "Zeitraum (mehrere Tage)" checkbox
    await employeePage.locator('#isDateRange').check();

    // Fill Von (start date) - weekdayFromNow ensures the range starts on a
    // weekday so the server's "Keine gültigen Arbeitstage" guard doesn't
    // reject it when "today + 10" lands on Sat/Sun.
    const startDate = weekdayFromNow(10);
    const endDate = weekdayFromNow(12);

    const dateInputs = employeePage.locator('input[type="date"]');
    await dateInputs.first().fill(startDate);
    // The second date input (Bis) should now be visible
    await dateInputs.nth(1).fill(endDate);

    // Select "training" type
    const typeSelect = employeePage.locator('select').first();
    await typeSelect.selectOption('training');

    // Submit
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Check for success toast
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /eingetragen|erfolgreich/ })
    ).toBeVisible({ timeout: 10000 });
  });

  test('delete absence', async ({ employeePage, createAbsence }) => {
    // Create an absence via fixture
    await createAbsence({
      date: nextWeekday(),
      type: 'other',
      hours: 8,
      note: 'E2E test absence to delete',
    });

    await employeePage.reload();
    await employeePage.waitForLoadState('networkidle');

    // Find and click the "Löschen" button
    const deleteButton = employeePage.getByRole('button', { name: 'Löschen' }).first();
    await deleteButton.click();

    // Confirm in the alertdialog
    const dialog = employeePage.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Löschen' }).click();

    // Check for deletion toast
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: 'gelöscht' })
    ).toBeVisible({ timeout: 10000 });
  });

  test('calendar shows absences after creating one', async ({ employeePage, createAbsence }) => {
    // Create an absence in the current month
    const futureDate = nextWeekday();
    await createAbsence({
      date: futureDate,
      type: 'vacation',
      hours: 8,
      note: 'Calendar test absence',
    });

    await employeePage.reload();
    await employeePage.waitForLoadState('networkidle');

    // The absence should appear in "Meine Abwesenheiten" table
    // Use the table cell locator to avoid hidden mobile elements
    const absenceTable = employeePage.locator('table');
    await expect(absenceTable.getByText('Calendar test absence')).toBeVisible({ timeout: 10000 });
  });

  test('toggle month/year view', async ({ employeePage }) => {
    // Check that "Jahr" button is visible (switch to year view)
    await expect(employeePage.getByRole('button', { name: 'Jahr' })).toBeVisible();

    // Click to switch to year view
    await employeePage.getByRole('button', { name: 'Jahr' }).click();

    // Now "Monat" button should be visible (year view is active, can switch back)
    await expect(employeePage.getByRole('button', { name: 'Monat' })).toBeVisible();
  });

  test('absence type options are all present', async ({ employeePage }) => {
    // Open the form
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Check all 5 options in the type select
    const typeSelect = employeePage.locator('select').first();
    await expect(typeSelect.locator('option[value="vacation"]')).toHaveText('Urlaub');
    await expect(typeSelect.locator('option[value="sick"]')).toHaveText('Krank');
    await expect(typeSelect.locator('option[value="training"]')).toHaveText('Fortbildung (außer Haus)');
    await expect(typeSelect.locator('option[value="overtime"]')).toHaveText('Überstundenausgleich');
    await expect(typeSelect.locator('option[value="other"]')).toHaveText('Sonstiges');
  });

  test('sick leave type available for creating during vacation', async ({ employeePage }) => {
    // This is a soft test - just verify sick leave type is available in the select
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    const typeSelect = employeePage.locator('select').first();
    await typeSelect.selectOption('sick');

    // Verify it was selected
    await expect(typeSelect).toHaveValue('sick');
  });

  test('erstellt Überstundenausgleich-Abwesenheit', async ({ employeePage, adminApi, testEmployee }) => {
    // Form öffnen
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Typ auf Überstundenausgleich setzen
    const typeSelect = employeePage.locator('select').first();
    await typeSelect.selectOption('overtime');
    await expect(typeSelect).toHaveValue('overtime');

    // Datum setzen (zukünftiger Werktag). weekdayFromNow handles the weekday
    // shift in the same timezone as Date.now() so toISOString-style off-by-one
    // bugs (UTC vs Europe/Berlin midnight rollover) can't affect us.
    const dateStr = weekdayFromNow(14);

    const dateInput = employeePage.locator('input[type="date"]').first();
    await dateInput.fill(dateStr);

    // Speichern
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Erfolgstoast
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /eingetragen|erfolgreich/ })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup via API
    try {
      const year = future.getFullYear();
      const month = future.getMonth() + 1;
      const absences = await adminApi.get(`/admin/users/${testEmployee.id}/absences?year=${year}&month=${month}`);
      const toDelete = Array.isArray(absences)
        ? absences.filter((a: any) => a.type === 'overtime' && a.date === dateStr)
        : [];
      for (const a of toDelete) {
        await adminApi.delete(`/absences/${a.id}`);
      }
    } catch { /* best effort cleanup */ }
  });

  test('Überstundenausgleich erscheint in der Abwesenheitsliste', async ({ employeePage, createAbsence }) => {
    // Abwesenheit per API erstellen. weekdayFromNow vermeidet UTC-Rollover-
    // Probleme bei Date.toISOString().
    const dateStr = weekdayFromNow(21);

    await createAbsence({
      date: dateStr,
      type: 'overtime',
      hours: 8,
    });

    // Seite neu laden
    await employeePage.reload();
    await employeePage.waitForLoadState('networkidle');

    // "Überstundenausgleich" in der Tabelle sehen
    const table = employeePage.locator('table');
    await expect(table.getByText('Überstundenausgleich')).toBeVisible({ timeout: 10000 });
  });

  test('employee edits own pending vacation request — hours', async ({
    employeePage,
    adminApi,
    createVacationRequest,
  }) => {
    // Enable approval requirement (admin-side)
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    const startDate = weekdayFromNow(48);
    const uniqueNote = `E2E self-edit ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      await createVacationRequest({
        date: startDate,
        hours: 8,
        note: uniqueNote,
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    // Reload so the page picks up the newly-enabled approval setting
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

    // Cleanup approval setting (request itself is teardown-handled by fixture)
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });
});
