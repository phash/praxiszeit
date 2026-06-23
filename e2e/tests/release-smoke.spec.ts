import { test, expect } from '@playwright/test';

// 1.9.0 Release-Smoke: Login + Dashboard + #213-Datensicherung (inkl. echtem
// Backup-Trigger) + Feedback-Dialog — mit Screenshots als Beleg.
const SHOT = (n: string) => ({ path: `screenshots-release/${n}.png`, fullPage: true });

test('release-smoke: login, dashboard, backup, feedback', async ({ page }) => {
  // --- Login-Seite -----------------------------------------------------------
  await page.goto('/login');
  await expect(page.locator('#username')).toBeVisible();
  await page.screenshot(SHOT('01-login'));

  // --- Login als Admin -------------------------------------------------------
  await page.fill('#username', 'admin');
  await page.fill('#password', 'Admin2025!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
  await expect(page.locator('main')).toBeVisible();
  await page.screenshot(SHOT('02-dashboard'));

  // --- #213 Datensicherung ---------------------------------------------------
  await page.goto('/admin/backups');
  await expect(page.getByRole('heading', { name: 'Datensicherung' })).toBeVisible();
  await page.screenshot(SHOT('03-backups-page'));

  // echten Backup-Trigger ausführen (pg_dump im Container)
  await page.getByRole('button', { name: /Jetzt sichern/ }).click();
  await expect(page.getByText(/Backup erstellt/)).toBeVisible({ timeout: 30000 });
  // die neue Datei muss in der Liste auftauchen
  await expect(page.locator('table').getByText(/praxiszeit_\d{8}_\d{6}\.sql\.gz/).first()).toBeVisible();
  await page.screenshot(SHOT('04-backup-created'));

  // --- Feedback / Rückmeldung ------------------------------------------------
  await page.getByRole('button', { name: 'Hilfe öffnen' }).click();
  await page.getByRole('button', { name: /Fehler melden \/ Feedback/ }).click();
  await expect(page.getByText(/Feedback|Fehler melden/).first()).toBeVisible();
  await page.screenshot(SHOT('05-feedback-dialog'));
});
