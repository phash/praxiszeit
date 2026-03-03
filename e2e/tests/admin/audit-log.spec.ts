import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Audit Log', () => {
  test.slow();

  test('page loads with heading and filters', async ({ adminPage }) => {
    await adminPage.goto('/admin/audit-log');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();

    // Check that the user filter dropdown exists
    const userFilter = adminPage.locator('select').filter({ hasText: 'Alle Mitarbeitende' });
    await expect(userFilter).toBeVisible();

    // Wait for data to load
    await adminPage.waitForLoadState('networkidle');

    // Should show either entries or "Keine Einträge"
    const table = adminPage.locator('table').first();
    const noEntries = adminPage.getByText('Keine Einträge');

    await expect(table.or(noEntries)).toBeVisible({ timeout: 10000 });
  });

  test('month navigation works', async ({ adminPage }) => {
    await adminPage.goto('/admin/audit-log');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();

    // Get the MonthSelector display text
    const monthDisplay = adminPage.locator('.min-w-\\[180px\\]');
    const initialText = await monthDisplay.textContent();

    // Click previous month
    await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Text should have changed
    await expect(monthDisplay).not.toHaveText(initialText!);

    // Click next month to go back
    await adminPage.getByRole('button', { name: 'Nächster Monat' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Should be back at original month
    await expect(monthDisplay).toHaveText(initialText!);
  });

  test('user filter dropdown works', async ({ adminPage }) => {
    await adminPage.goto('/admin/audit-log');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Find the user filter select
    const userFilter = adminPage.locator('select').filter({ hasText: 'Alle Mitarbeitende' });
    await expect(userFilter).toBeVisible();

    // Get all options
    const options = userFilter.locator('option');
    const optionCount = await options.count();

    // Should have at least "Alle Mitarbeitende" + the admin user
    expect(optionCount).toBeGreaterThanOrEqual(2);

    // Select the second option (first user)
    if (optionCount >= 2) {
      const secondOptionValue = await options.nth(1).getAttribute('value');
      if (secondOptionValue) {
        await userFilter.selectOption(secondOptionValue);
        await adminPage.waitForLoadState('networkidle');

        // Page should still be functional
        await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();
      }
    }

    // Switch back to all
    await userFilter.selectOption('');
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();
  });
});
