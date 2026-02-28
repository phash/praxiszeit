/**
 * PraxisZeit – Handbuch Screenshot-Generator
 */
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://127.0.0.1';
const OUT_DIR = path.join(__dirname, 'handbuch', 'screenshots');
const ADMIN = { username: 'admin', password: 'Admin2026!' };
const MA    = { username: 'maria.hoffmann', password: 'Mitarbeiter2026!' };

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function login(page, creds) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(1000);
  const usernameInput = await page.$('input[type="text"], input:not([type="password"])');
  const passwordInput = await page.$('input[type="password"]');
  if (!usernameInput || !passwordInput) throw new Error('Login inputs not found');
  await usernameInput.click({ clickCount: 3 });
  await usernameInput.type(creds.username);
  await passwordInput.click({ clickCount: 3 });
  await passwordInput.type(creds.password);
  await Promise.all([
    page.click('button[type="submit"]'),
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 })
  ]);
  await sleep(1500);
  console.log(`  ✓ Login: ${creds.username} | ${page.url()}`);
}

async function shot(page, filename, fullPage = false) {
  const fp = path.join(OUT_DIR, filename);
  await page.screenshot({ path: fp, fullPage });
  console.log(`  ✓ ${filename}`);
}

async function goto(page, url, wait = 2000) {
  await page.goto(`${BASE_URL}${url}`, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(wait);
}

// Klick auf Button anhand von Text-Inhalt (robust)
async function clickButtonByText(page, texts) {
  const btns = await page.$$('button');
  for (const btn of btns) {
    try {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      for (const t of texts) {
        if (text.includes(t)) {
          await btn.click();
          return true;
        }
      }
    } catch(e) { /* skip unclickable */ }
  }
  return false;
}

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  try {
    // ══════════════════════════════════════════════════════════════
    // MITARBEITER-SCREENSHOTS (Maria Hoffmann)
    // ══════════════════════════════════════════════════════════════
    console.log('\n═══ MITARBEITER-SCREENSHOTS ═══');
    const p = await browser.newPage();
    await p.setViewport({ width: 1280, height: 900 });

    // 01 Login
    await p.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(800);
    await shot(p, '01-ma-login.png');

    await login(p, MA);

    // 02 Dashboard
    await goto(p, '/dashboard');
    await shot(p, '02-ma-dashboard.png', true);

    // 03 Zeiterfassung (Wochenansicht)
    await goto(p, '/time-tracking');
    await shot(p, '03-ma-zeiterfassung.png', true);

    // 04 Zeiterfassung – in Februar navigieren (Daten vorhanden)
    // Klick auf "<" (vorherige Woche) mehrfach bis Feb
    for (let i = 0; i < 3; i++) {
      const prevBtn = await p.$('button[aria-label*="vorherige"], button[title*="vorherige"], button svg[data-lucide="chevron-left"]');
      if (prevBtn) {
        const parentBtn = await p.evaluateHandle(el => el.closest ? el.closest('button') : el.parentElement, prevBtn);
        if (parentBtn) await (await parentBtn.asElement()).click();
        else await prevBtn.click();
        await sleep(800);
      }
    }
    await shot(p, '04-ma-zeiterfassung-mit-daten.png', true);

    // 05 Zeiterfassung Formular öffnen (Hinzufügen)
    await goto(p, '/time-tracking');
    const addClicked = await clickButtonByText(p, ['Hinzufügen', 'Neuer Eintrag', '+', 'Neu']);
    await sleep(800);
    await shot(p, '05-ma-zeiteintrag-formular.png', true);
    await p.keyboard.press('Escape');
    await sleep(500);

    // 06 Abwesenheiten (Kalender)
    await goto(p, '/absences');
    await shot(p, '06-ma-abwesenheiten-kalender.png', true);

    // 07 Abwesenheit eintragen – Formular
    const absClicked = await clickButtonByText(p, ['Abwesenheit', 'Eintragen', 'Neu', '+']);
    await sleep(800);
    await shot(p, '07-ma-abwesenheit-formular.png', true);
    await p.keyboard.press('Escape');
    await sleep(500);

    // 08 Korrekturanträge
    await goto(p, '/change-requests');
    await shot(p, '08-ma-korrekturantraege.png', true);

    // 09 Korrekturantrag stellen – Formular
    const crClicked = await clickButtonByText(p, ['Antrag', 'Stellen', 'Neu', '+', 'Korrektur']);
    await sleep(800);
    await shot(p, '09-ma-korrekturantrag-formular.png', true);
    await p.keyboard.press('Escape');
    await sleep(500);

    // 10 Profil
    await goto(p, '/profile');
    await shot(p, '10-ma-profil.png', true);

    // 11 Mobile Ansicht
    await p.setViewport({ width: 390, height: 844 });
    await goto(p, '/dashboard');
    await shot(p, '11-ma-mobile-dashboard.png');
    await goto(p, '/time-tracking');
    await shot(p, '12-ma-mobile-zeiterfassung.png');
    // Hamburger Menu öffnen
    const menuClicked = await clickButtonByText(p, ['☰', 'Menu', 'Menü']);
    if (!menuClicked) {
      // Versuche aria-label
      const hamburger = await p.$('button[aria-label*="Menu"], button[aria-label*="Menü"]');
      if (hamburger) await hamburger.click();
    }
    await sleep(600);
    await shot(p, '13-ma-mobile-menu.png');

    await p.setViewport({ width: 1280, height: 900 });
    await p.close();

    // ══════════════════════════════════════════════════════════════
    // ADMIN-SCREENSHOTS
    // ══════════════════════════════════════════════════════════════
    console.log('\n═══ ADMIN-SCREENSHOTS ═══');
    const ap = await browser.newPage();
    await ap.setViewport({ width: 1280, height: 900 });

    await login(ap, ADMIN);

    // 14 Admin Dashboard
    await goto(ap, '/admin/dashboard');
    await shot(ap, '14-admin-dashboard.png', true);

    // 15 Benutzerverwaltung
    await goto(ap, '/admin/users');
    await shot(ap, '15-admin-benutzer.png', true);

    // 16 Neuen Benutzer anlegen
    await clickButtonByText(ap, ['Neuer Benutzer', 'Benutzer anlegen', 'Neuen Mitarbeiter', 'Hinzufügen', '+']);
    await sleep(1000);
    await shot(ap, '16-admin-benutzer-formular.png', true);
    await ap.keyboard.press('Escape');
    await sleep(500);

    // 17 Einen Benutzer bearbeiten (erneut Formular-Screenshot)
    await goto(ap, '/admin/users');
    // Klick auf den ersten "Bearbeiten"-Button mit direktem Selektor
    try {
      const editBtns = await ap.$$('button');
      for (const btn of editBtns) {
        const text = await ap.evaluate(el => el.textContent.trim(), btn);
        if (text.includes('Bearbeiten') || text.includes('Edit')) {
          await btn.click();
          await sleep(1000);
          break;
        }
      }
    } catch(e) { console.log('  ~ Kein Bearbeiten-Button gefunden'); }
    await shot(ap, '17-admin-benutzer-bearbeiten.png', true);
    await ap.keyboard.press('Escape');
    await sleep(500);

    // 18 Abwesenheitskalender
    await goto(ap, '/absences');
    await shot(ap, '18-admin-abwesenheitskalender.png', true);

    // 19 Berichte
    await goto(ap, '/admin/reports');
    await shot(ap, '19-admin-berichte.png', true);

    // 20 Korrekturanträge Admin
    await goto(ap, '/admin/change-requests');
    await shot(ap, '20-admin-korrekturantraege.png', true);

    // 21 Korrekturantrag genehmigen (Formular)
    await clickButtonByText(ap, ['Prüfen', 'Bearbeiten', 'Details', 'Anzeigen']);
    await sleep(800);
    await shot(ap, '21-admin-korrekturantrag-details.png', true);
    await ap.keyboard.press('Escape');
    await sleep(500);

    // 22 Audit Log
    await goto(ap, '/admin/audit-log');
    await shot(ap, '22-admin-auditlog.png', true);

    // 23 Fehlermonitoring
    await goto(ap, '/admin/errors');
    await shot(ap, '23-admin-fehlermonitoring.png', true);

    // 24 Betriebsferien
    await goto(ap, '/admin/closures');
    await shot(ap, '24-admin-betriebsferien.png', true);

    // 25 ArbZG Berichte
    await goto(ap, '/admin/reports');
    // Scroll nach unten für ArbZG-Berichte
    await ap.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(500);
    await shot(ap, '25-admin-arbzg-berichte.png', true);

    await ap.close();

    const files = fs.readdirSync(OUT_DIR).filter(f => f.endsWith('.png'));
    console.log(`\n✅ ${files.length} Screenshots erstellt in: ${OUT_DIR}`);
    files.forEach(f => console.log(`   ${f}`));

  } catch (err) {
    console.error('\n❌ Fehler:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
