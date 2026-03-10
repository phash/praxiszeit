import { test, expect } from '../../fixtures/base.fixture';

test.describe('Logout', () => {
  // Uses employeePage (fresh test user) so that logging out does NOT revoke
  // the shared worker-scoped admin token used by other tests.

  test('logout redirects to login page', async ({ employeePage }) => {
    await employeePage.getByRole('button', { name: 'Abmelden' }).click();
    await employeePage.waitForURL('/login');
    await expect(employeePage.getByRole('heading', { name: 'PraxisZeit' })).toBeVisible();
  });

  test('protected page inaccessible after logout', async ({ employeePage }) => {
    await employeePage.getByRole('button', { name: 'Abmelden' }).click();
    await employeePage.waitForURL('/login');
    await employeePage.goto('/time-tracking');
    await employeePage.waitForURL('/login');
    await expect(employeePage.getByLabel('Benutzername')).toBeVisible();
  });
});
