import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin User Journal', () => {
  test('öffnet Journal über Icon-Button in User-Liste', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();

    // Search by username (unique) to find exactly the test employee
    const searchInput = adminPage.getByPlaceholder('Suche nach Name oder Benutzername...');
    await searchInput.fill(testEmployee.username);

    // Click the journal icon button for the test employee
    // The actions column may be off-screen horizontally, so scroll into view first
    const journalBtn = adminPage.locator('button[title="Monatsjournal anzeigen"]').first();
    await expect(journalBtn).toBeAttached({ timeout: 5000 });
    await journalBtn.scrollIntoViewIfNeeded();
    await journalBtn.click();

    await expect(adminPage).toHaveURL(new RegExp(`/admin/users/.+/journal`));
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible();
  });

  test('Journal-Seite zeigt Tabelle mit Tagen des aktuellen Monats', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });

    // Wait for data to load (spinner disappears, table appears)
    const rows = adminPage.locator('table tbody tr');
    const daysInMonth = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();
    await expect(rows).toHaveCount(daysInMonth, { timeout: 15000 });
  });

  test('Monatsnavigation wechselt Monat', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });

    // Wait for initial data load
    await expect(adminPage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });

    // Get current month display text
    const monthDisplay = adminPage.locator('.min-w-\\[180px\\]');
    const initialText = await monthDisplay.textContent();

    // Navigate to previous month
    await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();

    // Month display should change
    await expect(monthDisplay).not.toHaveText(initialText!, { timeout: 5000 });

    // Table should still show rows
    await expect(adminPage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });
  });

  test('Aggregate-Kacheln sind sichtbar', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });

    // Wait for data to load
    await expect(adminPage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });

    await expect(adminPage.getByText('Ist (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Soll (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Saldo (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Überstunden (kumuliert)')).toBeVisible();
  });

  test('Zurück-Button navigiert zur Benutzerverwaltung', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });

    await adminPage.locator('button[aria-label="Zurück zur Benutzerverwaltung"]').click();
    await expect(adminPage).toHaveURL('/admin/users');
  });
});
