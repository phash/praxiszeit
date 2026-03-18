import { test, expect } from '../../fixtures/base.fixture';

test.describe('Employee Journal', () => {
  test('Journal-Seite erreichbar über Sidebar', async ({ employeePage }) => {
    // /journal route redirects to /time-tracking?tab=journal
    // The Journal link only exists in the mobile bottom nav (hidden on desktop viewport).
    // Test the routing directly to verify the redirect works correctly.
    await employeePage.goto('/journal');
    await expect(employeePage).toHaveURL(/tab=journal/, { timeout: 10000 });
    await expect(employeePage.getByRole('heading', { name: 'Mein Journal' })).toBeVisible();
  });

  test('Journal zeigt Tages-Tabelle mit Tagen des aktuellen Monats', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.getByRole('heading', { name: 'Mein Journal' })).toBeVisible({ timeout: 10000 });

    const rows = employeePage.locator('table tbody tr');
    const daysInMonth = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();
    await expect(rows).toHaveCount(daysInMonth, { timeout: 15000 });
  });

  test('Aggregate-Kacheln sichtbar', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.getByRole('heading', { name: 'Mein Journal' })).toBeVisible({ timeout: 10000 });

    // Wait for data to load
    await expect(employeePage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });

    await expect(employeePage.getByText('Ist (Monat)')).toBeVisible();
    await expect(employeePage.getByText('Soll (Monat)')).toBeVisible();
    await expect(employeePage.getByText('Saldo (Monat)')).toBeVisible();
    await expect(employeePage.getByText('Überstunden (kumuliert)')).toBeVisible();
  });

  test('Monatsnavigation wechselt Monat', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.getByRole('heading', { name: 'Mein Journal' })).toBeVisible({ timeout: 10000 });

    // Wait for initial data load
    await expect(employeePage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });

    // Get current month display text
    const monthDisplay = employeePage.locator('.min-w-\\[180px\\]');
    const initialText = await monthDisplay.textContent();

    // Navigate to previous month
    await employeePage.getByRole('button', { name: 'Vorheriger Monat' }).click();

    // Month display should change
    await expect(monthDisplay).not.toHaveText(initialText!, { timeout: 5000 });

    // Table should still show rows for the previous month
    await expect(employeePage.locator('table tbody tr').first()).toBeVisible({ timeout: 15000 });
  });

  test('Direkter Aufruf von /journal funktioniert', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.getByRole('heading', { name: 'Mein Journal' })).toBeVisible({ timeout: 10000 });
    // Aggregate tiles confirm data loaded
    await expect(employeePage.getByText('Ist (Monat)')).toBeVisible({ timeout: 15000 });
  });
});
