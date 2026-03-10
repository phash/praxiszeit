import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow } from '../../helpers/date.helper';

test.describe('Employee Absences', () => {
  // Rate limiting on login (5/min) can cause setup timeouts
  test.slow();

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

    // Fill Von (start date) - use daysFromNow to get future dates
    const startDate = daysFromNow(10);
    const endDate = daysFromNow(12);

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
    // Check that "Jahresansicht" button is visible
    await expect(employeePage.getByRole('button', { name: 'Jahresansicht' })).toBeVisible();

    // Click to switch to year view
    await employeePage.getByRole('button', { name: 'Jahresansicht' }).click();

    // Now "Monatsansicht" button should be visible (year view is active)
    await expect(employeePage.getByRole('button', { name: 'Monatsansicht' })).toBeVisible();
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

    // Datum setzen (zukünftiger Werktag)
    const future = new Date();
    future.setDate(future.getDate() + 14);
    if (future.getDay() === 6) future.setDate(future.getDate() + 2);
    if (future.getDay() === 0) future.setDate(future.getDate() + 1);
    const dateStr = future.toISOString().split('T')[0];

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
    // Abwesenheit per API erstellen
    const future = new Date();
    future.setDate(future.getDate() + 21);
    if (future.getDay() === 6) future.setDate(future.getDate() + 2);
    if (future.getDay() === 0) future.setDate(future.getDate() + 1);
    const dateStr = future.toISOString().split('T')[0];

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
});
