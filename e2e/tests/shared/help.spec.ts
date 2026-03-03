import { test, expect } from '../../fixtures/base.fixture';

test.describe('Help & Info Pages', () => {
  test.slow();

  test('help page loads', async ({ employeePage }) => {
    // Navigate via SPA link (direct /help URL may be intercepted by nginx)
    await employeePage.goto('/');
    await employeePage.waitForLoadState('networkidle');

    // Click the "Hilfe" link in the sidebar navigation
    await employeePage.getByRole('link', { name: 'Hilfe' }).click();
    await employeePage.waitForLoadState('networkidle');

    // Help page has heading "Hilfe & Dokumentation"
    await expect(employeePage.getByRole('heading', { name: /Hilfe/ })).toBeVisible();
    // Should show the Kurzanleitung tab button (active by default)
    await expect(employeePage.getByRole('button', { name: 'Kurzanleitung' })).toBeVisible();
    // Should show employee-specific content (not admin)
    await expect(employeePage.getByRole('heading', { name: 'Kurzanleitung für Mitarbeiter' })).toBeVisible();
  });

  test('privacy page loads', async ({ employeePage }) => {
    await employeePage.goto('/privacy');
    await employeePage.waitForLoadState('networkidle');

    // Privacy page has heading "Datenschutzerklärung"
    await expect(employeePage.getByRole('heading', { name: 'Datenschutzerklärung' })).toBeVisible();
    // Should contain key section headings
    await expect(employeePage.getByRole('heading', { name: /Verantwortlicher/ })).toBeVisible();
    await expect(employeePage.getByRole('heading', { name: /Datensicherheit/ })).toBeVisible();
  });
});
