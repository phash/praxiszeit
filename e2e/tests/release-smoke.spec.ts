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
  // #132: Bei frischer Installation legt sich das Onboarding-Modal als Full-Screen-
  // Overlay über die Seite und fängt alle Klicks ab. Schließen ("Los geht's"),
  // sonst läuft jeder spätere Klick in einen Timeout (best-effort, idempotent).
  await page.getByRole('button', { name: /Los geht/ }).click({ timeout: 5000 }).catch(() => {});
  await page.screenshot(SHOT('02-dashboard'));

  // --- #213 Datensicherung ---------------------------------------------------
  await page.goto('/admin/backups');
  await expect(page.getByRole('heading', { name: 'Datensicherung' })).toBeVisible();
  await page.screenshot(SHOT('03-backups-page'));

  // echten Backup-Trigger ausführen (pg_dump im Container)
  await page.getByRole('button', { name: /Jetzt sichern/ }).click();
  // Der "Backup erstellt"-Toast (3s) ist als Assertion flaky — der echte Beleg ist
  // die neue Tabellen-Zeile (best-effort auf den Toast, hart auf die Zeile).
  await expect(page.getByText(/Backup erstellt/)).toBeVisible({ timeout: 30000 }).catch(() => {});
  await expect(page.locator('table').getByText(/praxiszeit_\d{8}_\d{6}\.sql\.gz/).first()).toBeVisible({ timeout: 30000 });
  await page.screenshot(SHOT('04-backup-created'));

  // --- Feedback / Rückmeldung ------------------------------------------------
  await page.getByRole('button', { name: 'Hilfe öffnen' }).click();
  await page.getByRole('button', { name: /Fehler melden \/ Feedback/ }).click();
  await expect(page.getByText(/Feedback|Fehler melden/).first()).toBeVisible();
  await page.screenshot(SHOT('05-feedback-dialog'));
});
