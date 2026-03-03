import { test, expect } from '../../fixtures/base.fixture';

test.describe('Logout', () => {
  test.slow();
  test('logout redirects to login page', async ({ adminPage }) => {
    await adminPage.getByRole('button', { name: 'Abmelden' }).click();
    await adminPage.waitForURL('/login');
    await expect(adminPage.getByRole('heading', { name: 'PraxisZeit' })).toBeVisible();
  });

  test('protected page inaccessible after logout', async ({ adminPage }) => {
    await adminPage.getByRole('button', { name: 'Abmelden' }).click();
    await adminPage.waitForURL('/login');
    await adminPage.goto('/time-tracking');
    await adminPage.waitForURL('/login');
    await expect(adminPage.getByLabel('Benutzername')).toBeVisible();
  });
});
