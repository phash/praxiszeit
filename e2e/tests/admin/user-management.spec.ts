import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin User Management', () => {
  test('user list is visible', async ({ adminPage }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
    // Admin user should appear in the list
    await expect(adminPage.getByText('admin').first()).toBeVisible();
  });

  test('create new user', async ({ adminPage, adminApi }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Click "Neue:r Mitarbeiter:in"
    await adminPage.getByRole('button', { name: 'Neue:r Mitarbeiter:in' }).click();

    // Fill form
    const uniqueName = `e2e_admin_${Date.now()}`;
    await adminPage.locator('#f-username').fill(uniqueName);
    await adminPage.locator('#f-firstname').fill('TestCreate');
    await adminPage.locator('#f-lastname').fill('User');
    await adminPage.locator('#f-password').fill('TestPass123!');
    await adminPage.locator('#f-weekly-hours').fill('35');
    await adminPage.locator('#f-vacation').fill('25');

    // Submit
    await adminPage.getByRole('button', { name: 'Speichern' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup: find and deactivate the user via API
    try {
      const users = await adminApi.get('/admin/users');
      const created = users.find((u: any) => u.username === uniqueName);
      if (created) {
        await adminApi.delete(`/admin/users/${created.id}`);
      }
    } catch { /* best effort cleanup */ }
  });

  test('edit user weekly hours', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Search for the test employee
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill(testEmployee.last_name);

    // Find and click edit button
    const editButton = adminPage.locator('button[title="Bearbeiten"]').first();
    await expect(editButton).toBeVisible({ timeout: 5000 });
    await editButton.click();

    // Change weekly hours
    const weeklyHoursInput = adminPage.locator('#f-weekly-hours');
    await expect(weeklyHoursInput).toBeVisible({ timeout: 5000 });
    await weeklyHoursInput.fill('38');

    // Save
    await adminPage.getByRole('button', { name: 'Speichern' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'aktualisiert' })
    ).toBeVisible({ timeout: 10000 });
  });

  test('deactivate user', async ({ adminPage, adminApi }) => {
    // Create a user via API to deactivate
    const username = `e2e_deact_${Date.now()}`;
    const res = await adminApi.post('/admin/users', {
      username,
      password: 'TestPass123!',
      first_name: 'Deact',
      last_name: 'TestUser',
      role: 'employee',
      weekly_hours: 40,
      work_days_per_week: 5,
      vacation_days: 30,
      track_hours: true,
    });
    const userId = (res.user ?? res).id;

    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Search for the new user
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill('Deact');

    // Find deactivate button
    const deactButton = adminPage.locator('button[title="Deaktivieren"]').first();
    await expect(deactButton).toBeVisible({ timeout: 5000 });
    await deactButton.click();

    // Confirm dialog
    const dialog = adminPage.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Deaktivieren' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'deaktiviert' })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup
    try { await adminApi.delete(`/admin/users/${userId}`); } catch { /* already deactivated */ }
  });

  test('reactivate user', async ({ adminPage, adminApi }) => {
    // Create a user and deactivate via API
    const username = `e2e_react_${Date.now()}`;
    const res = await adminApi.post('/admin/users', {
      username,
      password: 'TestPass123!',
      first_name: 'React',
      last_name: 'TestUser',
      role: 'employee',
      weekly_hours: 40,
      work_days_per_week: 5,
      vacation_days: 30,
      track_hours: true,
    });
    const userId = (res.user ?? res).id;
    // Deactivate
    await adminApi.delete(`/admin/users/${userId}`);

    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Show inactive users
    await adminPage.getByText('Inaktive anzeigen').click();

    // Search for the deactivated user
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill('React');

    // Find reactivate button
    const reactivateButton = adminPage.locator('button[title="Reaktivieren"]').first();
    await expect(reactivateButton).toBeVisible({ timeout: 5000 });
    await reactivateButton.click();

    // Confirm dialog
    const dialog = adminPage.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Reaktivieren' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'reaktiviert' })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup
    try { await adminApi.delete(`/admin/users/${userId}`); } catch { /* best effort */ }
  });

  test('set password for user', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Search for test employee
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill(testEmployee.last_name);

    // Find and click "Passwort setzen" button
    const setPwdButton = adminPage.locator('button[title="Passwort setzen"]').first();
    await expect(setPwdButton).toBeVisible({ timeout: 5000 });
    await setPwdButton.click();

    // Fill the password modal
    await expect(adminPage.getByText('Passwort setzen').first()).toBeVisible({ timeout: 5000 });
    await adminPage.getByLabel('Neues Passwort').fill('NewTestPass123!');

    // Click save (scope to dialog to avoid strict mode violation with list buttons)
    await adminPage.getByRole('dialog').getByRole('button', { name: 'Passwort setzen' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'Passwort erfolgreich' })
    ).toBeVisible({ timeout: 10000 });
  });

  test('toggle hidden user', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Search for test employee
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill(testEmployee.last_name);

    // Find the hide/unhide button (eye icon)
    const hideButton = adminPage.locator('button[title="Ausblenden"], button[title="Einblenden"]').first();
    await expect(hideButton).toBeVisible({ timeout: 5000 });
    await hideButton.click();

    // Confirm if a dialog appears
    const dialog = adminPage.getByRole('alertdialog');
    const hasDialog = await dialog.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasDialog) {
      await dialog.getByRole('button').last().click();
    }

    // The page should not error out
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
  });

  test('search filter works', async ({ adminPage }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');

    // Type "admin" - should show admin user
    await searchInput.fill('admin');
    await expect(adminPage.getByText('admin').first()).toBeVisible();

    // Type nonexistent - should filter out
    await searchInput.fill('zzz_nonexistent_user_12345');

    // The admin text should no longer be visible in the user list
    // (the heading still says "Benutzerverwaltung" but the table should be empty or filtered)
    const userRows = adminPage.locator('table tbody tr, [role="button"]').filter({ hasText: 'admin' });
    await expect(userRows).toHaveCount(0, { timeout: 5000 });
  });

  test('Abwesenheit vor erstem Arbeitstag zeigt Fehler', async ({ adminApi, employeePage, testEmployee }) => {
    // Reset vacation_approval_required – if left true by another test, the absence form routes to
    // /vacation-requests (no first_work_day check there) and the error toast never appears.
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch { /* best effort */ }

    // first_work_day auf 30 Tage in der Zukunft setzen
    const future = new Date();
    future.setDate(future.getDate() + 30);
    const futureDateStr = future.toISOString().split('T')[0];
    await adminApi.put(`/admin/users/${testEmployee.id}`, {
      first_work_day: futureDateStr,
    });

    // Employee versucht eine Abwesenheit HEUTE (vor first_work_day) einzutragen
    await employeePage.goto('/absences');
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();
    const today = new Date().toISOString().split('T')[0];
    await employeePage.locator('input[type="date"]').first().fill(today);
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Fehler-Feedback prüfen – toast.error() rendert als [role="alert"]
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /ersten Arbeitstag|Datum liegt vor/i })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup: first_work_day entfernen (best effort – testEmployee fixture löscht den User ohnehin)
    try {
      await adminApi.put(`/admin/users/${testEmployee.id}`, { first_work_day: null });
    } catch { /* best effort */ }
  });

  test('Abwesenheit nach letztem Arbeitstag zeigt Fehler', async ({ adminApi, employeePage, testEmployee }) => {
    // Reset vacation_approval_required – same reason as the test above.
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch { /* best effort */ }

    // last_work_day auf gestern setzen
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = yesterday.toISOString().split('T')[0];
    await adminApi.put(`/admin/users/${testEmployee.id}`, {
      last_work_day: yesterdayStr,
    });

    // Employee versucht eine Abwesenheit HEUTE (nach last_work_day) einzutragen
    await employeePage.goto('/absences');
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();
    const today = new Date().toISOString().split('T')[0];
    await employeePage.locator('input[type="date"]').first().fill(today);
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Fehler-Feedback prüfen – toast.error() rendert als [role="alert"]
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /letzten Arbeitstag|Datum liegt nach/i })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup: last_work_day entfernen (best effort – testEmployee fixture löscht den User ohnehin)
    try {
      await adminApi.put(`/admin/users/${testEmployee.id}`, { last_work_day: null });
    } catch { /* best effort */ }
  });
});
