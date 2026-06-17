/**
 * Screenshots der neuen Features (2026-06-17): Schnellstart-Drawer + Onboarding-Toggle.
 * Usage: cd e2e && npx tsx capture-new-features.ts
 */
import { chromium, Page } from '@playwright/test';
import { mkdirSync } from 'fs';
import { resolve } from 'path';

const BASE_URL = 'http://localhost';
const DIR = resolve(__dirname, '../docs/screenshots-2026-06-17');
mkdirSync(DIR, { recursive: true });
const DESKTOP = { width: 1366, height: 900 };

async function shot(page: Page, name: string, fullPage = false) {
  await page.screenshot({ path: resolve(DIR, `${name}.png`), fullPage, type: 'png' });
  console.log('  ✓', name);
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: DESKTOP, locale: 'de-DE' });
  const page = await ctx.newPage();

  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await shot(page, '01-login');

  await page.getByRole('textbox', { name: 'Benutzername' }).fill('admin');
  await page.getByRole('textbox', { name: 'Passwort', exact: true }).fill('Admin2025!');
  await page.getByRole('button', { name: /anmelden/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(800);
  await shot(page, '02-admin-dashboard');

  // Schnellstart-Drawer (Button unten links in der Sidebar, admin-only)
  try {
    await page.getByRole('button', { name: 'Schnellstart' }).click({ timeout: 5000 });
    await page.waitForTimeout(800);
    await shot(page, '03-schnellstart-drawer');
    await page.getByRole('button', { name: /schließen/i }).first().click().catch(() => {});
    await page.waitForTimeout(400);
  } catch (e) {
    console.log('  ! Schnellstart-Button nicht gefunden:', (e as Error).message);
  }

  // Einstellungen -> Onboarding-Toggle
  await page.goto(`${BASE_URL}/admin/settings`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(700);
  await page.getByText('Onboarding / Willkommens-Tour').scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(400);
  await shot(page, '04-settings-onboarding-toggle');

  await browser.close();
  console.log('done -> docs/screenshots-2026-06-17/');
})();
