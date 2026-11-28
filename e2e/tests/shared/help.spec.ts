import { test, expect } from '../../fixtures/base.fixture';

test.describe('Help & Info Pages', () => {
  test('help page loads', async ({ employeePage }) => {
    // Navigate directly to /help route (Hilfe in sidebar opens a panel, not a link)
    await employeePage.goto('/help');
    await employeePage.waitForLoadState('networkidle');

    // Seit dem grafischen Handbuch (1.24) leitet /help auf das Buch der Rolle um:
    // Mitarbeitende landen im Handbuch für Mitarbeitende.
    await employeePage.waitForURL('**/help/mitarbeitende');
    await expect(employeePage.getByRole('heading', { name: 'Hilfe & Dokumentation' })).toBeVisible();
    const books = employeePage.getByRole('navigation', { name: 'Handbücher' });
    await expect(books.getByRole('link', { name: 'Handbuch für Mitarbeitende' })).toHaveAttribute('aria-current', 'page');
    await expect(books.getByRole('link', { name: 'So rechnet PraxisZeit' })).toBeVisible();
    // Should show employee-specific content (not admin)
    await expect(books.getByRole('link', { name: 'Handbuch für die Praxisleitung' })).toHaveCount(0);
    await expect(employeePage.getByRole('heading', { level: 1, name: 'Handbuch für Mitarbeitende' })).toBeVisible();
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
