/**
 * Handbuch-Screenshot-Capture.
 *
 * Läuft Playwright durch alle Handbuch-URLs und speichert die Screenshots
 * unter docs/handbuch/screenshots/. Braucht testdata aus
 * backend/create_handbuch_testdata.py (Admin: admin/Admin2026!, Employees:
 * *@praxis.de/Mitarbeiter2026!).
 *
 * Usage:
 *   cd e2e && npx tsx capture-handbook-screenshots.ts
 */
import { chromium, Browser, Locator, Page } from '@playwright/test';
import { mkdirSync } from 'fs';
import { resolve } from 'path';

const BASE_URL = 'http://localhost';
const SHOTS_DIR = resolve(__dirname, '../docs/handbuch/screenshots');

mkdirSync(SHOTS_DIR, { recursive: true });

const DESKTOP = { width: 1280, height: 800 };
const MOBILE = { width: 390, height: 844 };

async function login(page: Page, username: string, password: string) {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.getByRole('textbox', { name: 'Benutzername' }).fill(username);
  await page.getByRole('textbox', { name: 'Passwort', exact: true }).fill(password);
  await page.getByRole('button', { name: /anmelden/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10_000 });
  await page.waitForLoadState('networkidle');
  // #132: frisch angelegte Demo-Personen sehen beim ersten Login das
  // Willkommens-Fenster (ganzseitige Überlagerung) — es verdeckte alle Bilder
  // und schluckte die Klicks auf „Neuer Eintrag" usw. „Los geht's" schließt es
  // dauerhaft (POST /auth/onboarding/complete), wie die E2E-Fixtures.
  const welcome = page.getByRole('button', { name: "Los geht's" });
  if (await welcome.waitFor({ state: 'visible', timeout: 3000 }).then(() => true).catch(() => false)) {
    // Auf die Antwort warten: das nächste page.goto() bräche den POST sonst ab,
    // und das Fenster stünde nach dem Neuladen wieder da.
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/auth/onboarding/complete'), { timeout: 5000 }),
      welcome.click(),
    ]).catch(() => console.log(`  ! Willkommens-Fenster für ${username} nicht geschlossen`));
  }
}

async function shot(page: Page, name: string, opts: { fullPage?: boolean } = {}) {
  const path = resolve(SHOTS_DIR, `${name}.png`);
  await page.screenshot({ path, fullPage: opts.fullPage ?? true, type: 'png' });
  console.log(`  ✓ ${name}.png`);
}

/**
 * Die App scrollt in ihrem Inhaltsbereich (`<main>`), nicht im Dokument —
 * `fullPage` nimmt deshalb nur das Fenster auf, und ein langes Formular wäre
 * abgeschnitten. Das Fenster wird für die Aufnahme bis zur Unterkante von
 * `until` gestreckt und danach zurückgesetzt. Die Fokus-Markierung (Autofokus,
 * zuletzt befülltes Feld) wird vorher entfernt.
 */
async function shotUntil(page: Page, name: string, until: Locator) {
  const viewport = page.viewportSize() ?? DESKTOP;
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await until.evaluate((el) => {
    for (let p = el.parentElement; p; p = p.parentElement) p.scrollTop = 0;
  });
  const box = await until.boundingBox();
  if (box) {
    await page.setViewportSize({ width: viewport.width, height: Math.ceil(box.y + box.height + 24) });
    await page.waitForTimeout(300);
  }
  await shot(page, name, { fullPage: false });
  await page.setViewportSize(viewport);
}

/** Beispielwoche aus dem Handbuch: Mo–Do 08:00–12:00 + 15:00–18:00 mit 30 Min
 *  Pause (Tagessoll 6:30 h), Fr 08:00–13:00. */
async function fillExampleBlocks(page: Page) {
  for (const day of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
    const spans = day === 'Fr' ? [['08:00', '13:00']] : [['08:00', '12:00'], ['15:00', '18:00']];
    for (const [n, [von, bis]] of spans.entries()) {
      await page.getByRole('button', { name: `${day}: Block hinzufügen` }).click();
      await page.getByLabel(`${day} Block ${n + 1} von`).fill(von);
      await page.getByLabel(`${day} Block ${n + 1} bis`).fill(bis);
    }
    if (spans.length > 1) {
      await page.getByLabel(`${day} Pause innerhalb der Blöcke (Min)`).fill('30');
    }
  }
}

async function captureEmployeeShots(browser: Browser) {
  console.log('\n── Mitarbeiter-Screenshots ──────────────────');
  const context = await browser.newContext({ viewport: DESKTOP, locale: 'de-DE' });
  const page = await context.newPage();

  // 01 Login (pre-auth)
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await shot(page, '01-ma-login');

  // Login as employee
  await login(page, 'maria.hoffmann', 'Mitarbeiter2026!');

  // 02 Dashboard
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await shot(page, '02-ma-dashboard');

  // 03 Zeiterfassung
  await page.goto(`${BASE_URL}/time-tracking`);
  await page.waitForLoadState('networkidle');
  await shot(page, '03-ma-zeiterfassung');

  // 04 Zeiteintrag-Formular (click "+ Neuer Eintrag" / "Zeit eintragen")
  try {
    const addBtn = page.getByRole('button', { name: /neuer eintrag|zeit eintragen|\+ eintragen/i }).first();
    await addBtn.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    await shot(page, '04-ma-zeiteintrag-formular');
    // Close dialog if any
    const cancel = page.getByRole('button', { name: /abbrechen|schließen/i }).first();
    if (await cancel.isVisible().catch(() => false)) await cancel.click();
  } catch {
    console.log('  ! 04-ma-zeiteintrag-formular: Formular-Button nicht gefunden');
  }

  // 05 Abwesenheiten (list)
  await page.goto(`${BASE_URL}/absences`);
  await page.waitForLoadState('networkidle');
  await shot(page, '05-ma-abwesenheiten');

  // 06 Abwesenheiten Kalender (same URL, but we capture as-is since calendar/list toggle varies)
  await shot(page, '06-ma-abwesenheiten-kalender');

  // 07 Abwesenheit-Formular
  try {
    const addAbs = page.getByRole('button', { name: /abwesenheit eintragen|neue abwesenheit|\+ eintragen/i }).first();
    await addAbs.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    await shot(page, '07-ma-abwesenheit-formular');
    const cancel = page.getByRole('button', { name: /abbrechen|schließen/i }).first();
    if (await cancel.isVisible().catch(() => false)) await cancel.click();
  } catch {
    console.log('  ! 07-ma-abwesenheit-formular: Button nicht gefunden');
  }

  // 08 Korrekturanträge-Tab in /time-tracking
  await page.goto(`${BASE_URL}/time-tracking`);
  await page.waitForLoadState('networkidle');
  try {
    const crTab = page.getByRole('button', { name: /änderungsanträge|korrekturanträge|anträge/i }).first();
    if (await crTab.isVisible().catch(() => false)) {
      await crTab.click();
      await page.waitForTimeout(500);
    }
    await shot(page, '08-ma-korrekturantraege');
  } catch {
    console.log('  ! 08-ma-korrekturantraege: Tab nicht erreichbar');
  }

  // 10 Profil
  await page.goto(`${BASE_URL}/profile`);
  await page.waitForLoadState('networkidle');
  await shot(page, '10-ma-profil');

  await context.close();

  // ── Mobile ──
  console.log('\n── Mobile Mitarbeiter-Screenshots ──────────');
  const mctx = await browser.newContext({ viewport: MOBILE, locale: 'de-DE', isMobile: true, hasTouch: true });
  const mpage = await mctx.newPage();
  await login(mpage, 'maria.hoffmann', 'Mitarbeiter2026!');

  // 11 Mobile Dashboard
  await mpage.goto(`${BASE_URL}/`);
  await mpage.waitForLoadState('networkidle');
  await shot(mpage, '11-ma-mobile-dashboard');

  // 12 Mobile Zeiterfassung
  await mpage.goto(`${BASE_URL}/time-tracking`);
  await mpage.waitForLoadState('networkidle');
  await shot(mpage, '12-ma-mobile-zeiterfassung');

  // 13 Mobile Menü
  try {
    const burger = mpage.getByRole('button', { name: /menü öffnen|menu/i }).first();
    await burger.click({ timeout: 2000 });
    await mpage.waitForTimeout(300);
    await shot(mpage, '13-ma-mobile-menu');
  } catch {
    console.log('  ! 13-ma-mobile-menu: Hamburger-Button nicht gefunden');
  }

  await mctx.close();
}

async function captureAdminShots(browser: Browser) {
  console.log('\n── Admin-Screenshots ──────────────────────────');
  const context = await browser.newContext({ viewport: DESKTOP, locale: 'de-DE' });
  const page = await context.newPage();

  await login(page, 'admin', 'Admin2026!');

  // 14 Admin-Dashboard
  await page.goto(`${BASE_URL}/admin`);
  await page.waitForLoadState('networkidle');
  await shot(page, '14-admin-dashboard');

  // 15 Benutzerliste
  await page.goto(`${BASE_URL}/admin/users`);
  await page.waitForLoadState('networkidle');
  await shot(page, '15-admin-benutzer');

  // 16 Neuer-Benutzer-Formular
  try {
    const newBtn = page.getByRole('button', { name: /neue:?r? ?mitarbeiter|neuer mitarbeiter|\+ mitarbeiter/i }).first();
    await newBtn.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    // 1.20.0: Block-Editor zeigen (Modus „Nach Arbeitsblöcken") — mit der
    // Beispielwoche, sonst stünden nur „kein Arbeitstag" und eine Fehlermeldung da.
    const blockMode = page.getByText('Nach Arbeitsblöcken', { exact: true }).first();
    if (await blockMode.isVisible().catch(() => false)) {
      await blockMode.click();
      await page.waitForTimeout(300);
      await fillExampleBlocks(page).catch(() =>
        console.log('  ! 16-admin-benutzer-formular: Block-Editor nicht befüllbar'));
    }
    await shotUntil(page, '16-admin-benutzer-formular', page.locator('form').first());
    const cancel = page.getByRole('button', { name: /abbrechen|schließen/i }).first();
    if (await cancel.isVisible().catch(() => false)) await cancel.click();
  } catch {
    console.log('  ! 16-admin-benutzer-formular: Button nicht gefunden');
  }

  // 17 Benutzer bearbeiten — Demo-Person mit Arbeitszeit-Blöcken (Sarah Klein)
  try {
    await page.waitForTimeout(500);
    const kleinRow = page.getByRole('row', { name: /Klein/ }).first();
    const editBtn = (await kleinRow.isVisible().catch(() => false))
      ? kleinRow.getByRole('button', { name: /bearbeiten/i }).first()
      : page.getByRole('button', { name: /bearbeiten/i }).first();
    await editBtn.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    // Ganzes Formular: oben „Arbeitszeit anpassen…", unten „Arbeitszeit heute".
    await shotUntil(page, '17-admin-benutzer-bearbeiten', page.locator('form').first());
    const cancel = page.getByRole('button', { name: /abbrechen|schließen/i }).first();
    if (await cancel.isVisible().catch(() => false)) await cancel.click();
  } catch {
    console.log('  ! 17-admin-benutzer-bearbeiten: Button nicht gefunden');
  }

  // 18 Abwesenheitskalender
  await page.goto(`${BASE_URL}/admin/absences`);
  await page.waitForLoadState('networkidle');
  await shot(page, '18-admin-abwesenheitskalender');

  // 19 Berichte
  await page.goto(`${BASE_URL}/admin/reports`);
  await page.waitForLoadState('networkidle');
  await shot(page, '19-admin-berichte');

  // 25 ArbZG-Berichte — scroll down on reports
  try {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    await shot(page, '25-admin-arbzg-berichte');
  } catch {
    console.log('  ! 25-admin-arbzg-berichte: scroll failed');
  }

  // 20 Korrekturanträge-Liste
  await page.goto(`${BASE_URL}/admin/change-requests`);
  await page.waitForLoadState('networkidle');
  await shot(page, '20-admin-korrekturantraege');

  // 21 Korrekturantrag-Details (click erster Antrag)
  try {
    const detailBtn = page.getByRole('button', { name: /details|prüfen|bearbeiten/i }).first();
    if (await detailBtn.isVisible().catch(() => false)) {
      await detailBtn.click({ timeout: 2000 });
      await page.waitForTimeout(500);
      await shot(page, '21-admin-korrekturantrag-details');
    } else {
      console.log('  ! 21-admin-korrekturantrag-details: Kein Antrag sichtbar');
    }
  } catch {
    console.log('  ! 21-admin-korrekturantrag-details: failed');
  }

  // 22 Audit-Log
  await page.goto(`${BASE_URL}/admin/audit-log`);
  await page.waitForLoadState('networkidle');
  await shot(page, '22-admin-auditlog');

  // 23 Fehler-Monitoring
  await page.goto(`${BASE_URL}/admin/errors`);
  await page.waitForLoadState('networkidle');
  await shot(page, '23-admin-fehlermonitoring');

  // 24 Betriebsferien (Tab auf /admin/absences)
  await page.goto(`${BASE_URL}/admin/absences`);
  await page.waitForLoadState('networkidle');
  try {
    const betrTab = page.getByRole('button', { name: /betriebsferien/i }).first();
    await betrTab.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    await shot(page, '24-admin-betriebsferien');
  } catch {
    console.log('  ! 24-admin-betriebsferien: Tab nicht gefunden');
  }

  // 26 Urlaubsanträge
  await page.goto(`${BASE_URL}/admin/vacation-approvals`);
  await page.waitForLoadState('networkidle');
  await shot(page, '26-admin-urlaubsantraege');

  await context.close();
}

(async () => {
  const browser = await chromium.launch();
  try {
    await captureEmployeeShots(browser);
    await captureAdminShots(browser);
    console.log('\n✅ Alle Screenshots in', SHOTS_DIR);
  } finally {
    await browser.close();
  }
})();
