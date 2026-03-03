import { test, expect } from '@playwright/test';

test.describe('Login', () => {
  test.slow();

  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.getByLabel('Benutzername').fill('admin');
    await page.locator('#password').fill('Admin2025!');
    await page.getByRole('button', { name: 'Anmelden' }).click();
    await page.waitForURL('/');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('wrong password shows error', async ({ page }) => {
    await page.getByLabel('Benutzername').fill('admin');
    await page.locator('#password').fill('wrongpassword');
    await page.getByRole('button', { name: 'Anmelden' }).click();
    await expect(page.locator('.bg-red-50')).toBeVisible();
  });

  test('empty fields show validation', async ({ page }) => {
    await page.getByRole('button', { name: 'Anmelden' }).click();
    const usernameInput = page.getByLabel('Benutzername');
    await expect(usernameInput).toHaveAttribute('required', '');
  });
});
