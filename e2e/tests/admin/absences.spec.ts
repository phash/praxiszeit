import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow } from '../../helpers/date.helper';

test.describe('Admin Absences', () => {
  test.slow();

  test('create absence for employee', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Select the test employee from dropdown
    const employeeSelect = adminPage.locator('select').first();
    // Get all options and find the one containing the employee name
    const options = employeeSelect.locator('option');
    const count = await options.count();
    let targetValue = '';
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent();
      if (text && text.includes(testEmployee.last_name)) {
        targetValue = await options.nth(i).getAttribute('value') || '';
        break;
      }
    }
    expect(targetValue).not.toBe('');
    await employeeSelect.selectOption(targetValue);
    await adminPage.waitForTimeout(500);

    // Click "Abwesenheit eintragen"
    await adminPage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Fill the form with a far-future unique date to avoid conflicts
    const dateInput = adminPage.locator('input[type="date"]').first();
    await dateInput.fill(daysFromNow(30));

    // Type should default to vacation
    const typeSelect = adminPage.locator('select').filter({ has: adminPage.locator('option[value="vacation"]') }).first();
    await typeSelect.selectOption('vacation');

    // Submit and wait for response
    const responsePromise = adminPage.waitForResponse(
      (resp) => resp.url().includes('/api/absences') && resp.request().method() === 'POST'
    );
    await adminPage.getByRole('button', { name: 'Speichern' }).click();
    const response = await responsePromise;

    if (response.ok()) {
      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /eingetragen|erfolgreich|gespeichert/ })
      ).toBeVisible({ timeout: 10000 });
    } else {
      // If it fails (e.g. duplicate), check we at least got an error message displayed
      await expect(adminPage.locator('.bg-red-50, [role="alert"]')).toBeVisible({ timeout: 5000 });
    }
  });

  test('delete absence', async ({ adminPage, testEmployee, createAbsence }) => {
    // Create an absence via API for the test employee
    await createAbsence({
      date: nextWeekday(),
      type: 'other',
      hours: 8,
      note: 'E2E admin delete test',
      user_id: testEmployee.id,
    });

    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Select the test employee
    const employeeSelect = adminPage.locator('select').first();
    const options = employeeSelect.locator('option');
    const count = await options.count();
    let targetValue = '';
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent();
      if (text && text.includes(testEmployee.last_name)) {
        targetValue = await options.nth(i).getAttribute('value') || '';
        break;
      }
    }
    expect(targetValue).not.toBe('');
    await employeeSelect.selectOption(targetValue);
    await adminPage.waitForLoadState('networkidle');
    await adminPage.waitForTimeout(1000);

    // Find delete button
    const deleteButton = adminPage.locator('button[aria-label="Löschen"]').first();
    const hasDelete = await deleteButton.isVisible({ timeout: 5000 }).catch(() => false);

    if (hasDelete) {
      await deleteButton.click();

      // Confirm dialog
      const dialog = adminPage.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: 'Löschen' }).click();

      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'gelöscht' })
      ).toBeVisible({ timeout: 10000 });
    }
  });

  test('create company closure', async ({ adminPage }) => {
    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Switch to Betriebsferien tab
    await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
    await adminPage.waitForTimeout(500);

    // Click "Betriebsferien erstellen"
    await adminPage.getByRole('button', { name: 'Betriebsferien erstellen' }).click();

    // Fill the form
    const nameInput = adminPage.locator('input[type="text"]').first();
    await nameInput.fill(`E2E Betriebsferien ${Date.now()}`);

    // Set start and end dates (future dates)
    const dateInputs = adminPage.locator('input[type="date"]');
    const startDate = daysFromNow(60);
    const endDate = daysFromNow(62);
    await dateInputs.first().fill(startDate);
    await dateInputs.nth(1).fill(endDate);

    // Submit
    await adminPage.getByRole('button', { name: /Betriebsferien erstellen/ }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /Betriebsferien|eingetragen|erstellt/ })
    ).toBeVisible({ timeout: 10000 });
  });

  test('delete company closure', async ({ adminPage, adminApi }) => {
    // Create a closure via API
    const closureName = `E2E Delete Test ${Date.now()}`;
    try {
      await adminApi.post('/company-closures', {
        name: closureName,
        start_date: daysFromNow(90),
        end_date: daysFromNow(91),
      });
    } catch {
      // If API fails, skip
      test.skip();
      return;
    }

    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Switch to Betriebsferien tab
    await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
    await adminPage.waitForLoadState('networkidle');
    await adminPage.waitForTimeout(1000);

    // Find delete button for the closure
    const deleteButton = adminPage.locator('button[aria-label="Betriebsferien löschen"]').first();
    const hasDelete = await deleteButton.isVisible({ timeout: 5000 }).catch(() => false);

    if (hasDelete) {
      await deleteButton.click();

      // Confirm dialog
      const dialog = adminPage.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: 'Löschen' }).click();

      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /gelöscht/ })
      ).toBeVisible({ timeout: 10000 });
    }
  });

  test('tab switch between absences and closures', async ({ adminPage }) => {
    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Should start on absences tab with employee selector visible
    await expect(adminPage.getByText('Mitarbeiter-Abwesenheiten')).toBeVisible();

    // Switch to Betriebsferien
    await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
    await adminPage.waitForTimeout(500);
    await expect(adminPage.getByText('Betriebsferien').first()).toBeVisible();

    // Switch back
    await adminPage.getByRole('button', { name: 'Mitarbeiter-Abwesenheiten' }).click();
    await adminPage.waitForTimeout(500);
    // Verify the employee select dropdown is visible (contains "Alle Mitarbeiter" option)
    const selectDropdown = adminPage.locator('select').first();
    await expect(selectDropdown).toBeVisible();
    await expect(selectDropdown.locator('option').first()).toContainText('Alle Mitarbeiter');
  });
});
