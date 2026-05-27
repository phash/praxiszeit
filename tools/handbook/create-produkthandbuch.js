/**
 * PraxisZeit Produkthandbuch Generator
 * Erstellt ein vollständiges PDF-Handbuch mit Screenshots aus der Anwendung.
 */
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost';
const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';
const EMP_USER = 'sophie.schmidt@praxis.de';
const EMP_PASS = 'Mitarbeiter2026!';
const OUTPUT_HTML = path.join(__dirname, 'PRODUKTHANDBUCH.html');
const OUTPUT_PDF = path.join(__dirname, 'PraxisZeit-Produkthandbuch.pdf');

const screenshots = {};

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function takeScreenshot(page, name, description) {
  await sleep(600);
  const buf = await page.screenshot({ fullPage: false, type: 'png' });
  screenshots[name] = { data: buf.toString('base64'), description };
  console.log(`  📸 ${name}`);
}

async function fullPageScreenshot(page, name, description) {
  await sleep(600);
  const buf = await page.screenshot({ fullPage: true, type: 'png' });
  screenshots[name] = { data: buf.toString('base64'), description };
  console.log(`  📸 ${name} (full page)`);
}

async function login(page, username, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await page.waitForSelector('input', { timeout: 10000 });
  await sleep(400);
  const inputs = await page.$$('input');
  await inputs[0].click({ clickCount: 3 });
  await inputs[0].type(username);
  await inputs[1].click({ clickCount: 3 });
  await inputs[1].type(password);
  await page.click('button[type="submit"]');
  await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(800);
}

async function logout(page) {
  // Click logout button in nav
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
    await sleep(300);
    // Clear localStorage to log out
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
    await sleep(300);
  } catch (e) {}
}

async function run() {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=de-DE'],
    defaultViewport: { width: 1280, height: 860 }
  });
  const page = await browser.newPage();

  // ─── LOGIN PAGE ───────────────────────────────────────────────────────────
  console.log('\n── Login-Seite');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await sleep(500);
  await takeScreenshot(page, 'login_empty', 'Anmeldeseite – Eingabemaske für Benutzername und Passwort');

  // Fill in login form for screenshot
  const inputs = await page.$$('input');
  if (inputs[0]) await inputs[0].type(EMP_USER);
  if (inputs[1]) await inputs[1].type('••••••••');
  await takeScreenshot(page, 'login_filled', 'Anmeldeseite – Ausgefülltes Formular vor dem Absenden');

  // ═══════════════════════════════════════════════════════════════════════════
  // MITARBEITER-ANSICHT
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n── Mitarbeiter: Sophie Schmidt');
  await login(page, EMP_USER, EMP_PASS);

  // Dashboard
  console.log('\n── MA: Dashboard');
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'ma_dashboard', 'Mitarbeiter-Dashboard – Übersicht mit Stempeluhr, Monatsstatistik und Urlaubskonto');

  // Stempeluhr – zoom into stamp widget area
  await fullPageScreenshot(page, 'ma_dashboard_full', 'Mitarbeiter-Dashboard – Vollständige Ansicht mit allen Statuskarten');

  // Stempeluhr einstempeln
  try {
    const stampBtn = await page.$x("//*[contains(text(), 'Einstempeln')]");
    if (stampBtn.length > 0) {
      await stampBtn[0].click();
      await sleep(1000);
      await takeScreenshot(page, 'ma_stempeluhr_ein', 'Stempeluhr – Eingestempelt (Arbeitsbeginn erfasst)');
      // Ausstempeln
      const outBtn = await page.$x("//*[contains(text(), 'Ausstempeln')]");
      if (outBtn.length > 0) {
        await outBtn[0].click();
        await sleep(800);
        await takeScreenshot(page, 'ma_stempeluhr_aus', 'Stempeluhr – Ausgestempelt (Arbeitsende erfasst)');
      }
    }
  } catch (e) { console.log('  Stempeluhr skip:', e.message); }

  // Zeiterfassung
  console.log('\n── MA: Zeiterfassung');
  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(1200);
  await takeScreenshot(page, 'ma_zeiterfassung', 'Zeiterfassung – Wochenansicht mit Zeiteinträgen, Soll/Ist-Vergleich und Saldo');

  // Navigate to a week with data – go back a few weeks
  try {
    const prevBtns = await page.$$('button');
    // Find prev week button
    for (const btn of prevBtns) {
      const text = await page.evaluate(el => el.textContent, btn);
      if (text && (text.includes('←') || text.includes('<') || text.includes('Vorher'))) {
        await btn.click();
        await sleep(800);
        break;
      }
    }
    await takeScreenshot(page, 'ma_zeiterfassung_prev', 'Zeiterfassung – Wochennavigation (Vorwoche mit Zeiteinträgen)');
  } catch (e) {}

  // Open "New Entry" form
  console.log('\n── MA: Zeiterfassung – Neuer Eintrag');
  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(800);
  try {
    // Click "+" or "Neuer Eintrag" button
    const addBtns = await page.$$('button');
    for (const btn of addBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text === '+' || text.includes('Eintrag') || text.includes('Neu')) {
        await btn.click();
        await sleep(600);
        break;
      }
    }
    await takeScreenshot(page, 'ma_zeiteintrag_form', 'Zeiterfassung – Formular für neuen Zeiteintrag (Datum, Von, Bis, Pause, Notiz)');
  } catch (e) {}

  // Abwesenheiten
  console.log('\n── MA: Abwesenheiten');
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1200);
  await takeScreenshot(page, 'ma_abwesenheiten', 'Abwesenheiten – Kalenderansicht mit Team-Übersicht und Farbcodierung nach Mitarbeiter');

  // Open absence form
  try {
    const plusBtns = await page.$$('button');
    for (const btn of plusBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text.includes('Abwesenheit') || text === '+' || text.includes('Eintragen')) {
        await btn.click();
        await sleep(600);
        break;
      }
    }
    await takeScreenshot(page, 'ma_abwesenheit_form', 'Abwesenheiten – Formular für neue Abwesenheit (Typ, Datum, Stunden, Notiz)');

    // Enable date range
    try {
      const checkboxes = await page.$$('input[type="checkbox"]');
      if (checkboxes.length > 0) {
        await checkboxes[0].click();
        await sleep(400);
        await takeScreenshot(page, 'ma_abwesenheit_zeitraum', 'Abwesenheiten – Zeitraum-Erfassung (Mehrere Tage auf einmal eintragen)');
      }
    } catch (e) {}
  } catch (e) {}

  // Full page with calendar
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(800);
  await fullPageScreenshot(page, 'ma_abwesenheiten_full', 'Abwesenheiten – Vollständige Seite mit Kalender, Formular und Abwesenheitsliste');

  // Profile
  console.log('\n── MA: Profil');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
  await sleep(800);
  await takeScreenshot(page, 'ma_profil', 'Profil – Persönliche Daten und Passwort ändern');

  // ═══════════════════════════════════════════════════════════════════════════
  // ADMIN-ANSICHT
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n── Admin-Anmeldung');
  await logout(page);
  await login(page, ADMIN_USER, ADMIN_PASS);

  // Admin Dashboard
  console.log('\n── Admin: Dashboard');
  await page.goto(`${BASE_URL}/admin`, { waitUntil: 'networkidle2' });
  await sleep(1200);
  await takeScreenshot(page, 'admin_dashboard', 'Admin-Dashboard – Teamübersicht mit Stundensalden und Urlaubskonten aller Mitarbeiter');
  await fullPageScreenshot(page, 'admin_dashboard_full', 'Admin-Dashboard – Vollständige Teamübersicht mit Jahres-Abwesenheitsstatistiken');

  // Benutzerverwaltung
  console.log('\n── Admin: Benutzerverwaltung');
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(1200);
  await takeScreenshot(page, 'admin_users_list', 'Benutzerverwaltung – Übersicht aller Mitarbeiter mit Urlaubskonto-Ampel');

  // Open "New User" form
  try {
    const newBtns = await page.$$('button');
    for (const btn of newBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text.includes('Neuer') || text.includes('Anlegen') || text.includes('+ ')) {
        await btn.click();
        await sleep(600);
        break;
      }
    }
    await takeScreenshot(page, 'admin_user_create', 'Benutzerverwaltung – Formular zum Anlegen eines neuen Mitarbeiters');
  } catch (e) {}

  // Open edit form for existing user
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(800);
  try {
    const editBtns = await page.$$('button');
    for (const btn of editBtns) {
      const title = await page.evaluate(el => el.title || el.getAttribute('aria-label') || '', btn);
      const icon = await page.evaluate(el => el.querySelector('svg') ? el.innerHTML : '', btn);
      if (title.toLowerCase().includes('bear') || title.toLowerCase().includes('edit') || icon.includes('Edit')) {
        await btn.click();
        await sleep(600);
        break;
      }
    }
    await takeScreenshot(page, 'admin_user_edit', 'Benutzerverwaltung – Benutzer bearbeiten (Stammdaten, Wochenstunden, Arbeitstage)');

    // Enable daily schedule
    try {
      const checkboxes = await page.$$('input[type="checkbox"]');
      for (const cb of checkboxes) {
        const id = await page.evaluate(el => el.id || '', cb);
        if (id === 'use_daily_schedule') {
          await cb.click();
          await sleep(500);
          await takeScreenshot(page, 'admin_user_daily_schedule', 'Benutzerverwaltung – Individuelle Tagesstunden (Mo–Fr einzeln konfigurierbar)');
          await cb.click(); // reset
          break;
        }
      }
    } catch (e) {}
  } catch (e) {}

  // Arbeitszeit-Historie Modal
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(800);
  try {
    // Find "Stundenänderung" button (clock icon)
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const title = await page.evaluate(el => el.title || '', btn);
      if (title.toLowerCase().includes('stunden') || title.toLowerCase().includes('hour')) {
        await btn.click();
        await sleep(800);
        await takeScreenshot(page, 'admin_user_stunden_modal', 'Benutzerverwaltung – Arbeitszeit-Historie mit Verlauf aller Stundenänderungen');
        // Close modal
        const closeBtns = await page.$$('button');
        for (const cb of closeBtns) {
          const text = await page.evaluate(el => el.textContent.trim(), cb);
          if (text === '×' || text === 'X' || text === 'Schließen') {
            await cb.click(); break;
          }
        }
        break;
      }
    }
  } catch (e) {}

  // Admin Abwesenheiten
  console.log('\n── Admin: Abwesenheiten');
  await page.goto(`${BASE_URL}/admin/absences`, { waitUntil: 'networkidle2' });
  await sleep(1200);
  await takeScreenshot(page, 'admin_absences_tab1', 'Admin Abwesenheiten – Mitarbeiter-Abwesenheiten verwalten (Übersicht & Eintragen)');

  // Betriebsferien Tab
  try {
    const tabs = await page.$$('button');
    for (const tab of tabs) {
      const text = await page.evaluate(el => el.textContent.trim(), tab);
      if (text.includes('Betriebsferien') || text.includes('Betriebs')) {
        await tab.click();
        await sleep(800);
        await takeScreenshot(page, 'admin_absences_betriebsferien', 'Admin Abwesenheiten – Betriebsferien anlegen (automatische Urlaubs-Einträge für alle Mitarbeiter)');
        break;
      }
    }
  } catch (e) {}

  // Berichte
  console.log('\n── Admin: Berichte');
  await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'admin_reports_top', 'Berichte & Export – Monatsreport und Jahresreport exportieren');
  await fullPageScreenshot(page, 'admin_reports_full', 'Berichte & Export – Vollständige Seite mit allen Exportoptionen und Ruhezeitprüfung');

  // Scroll to rest time section
  await page.evaluate(() => window.scrollTo(0, 1200));
  await sleep(400);
  await takeScreenshot(page, 'admin_reports_ruhezeit', 'Berichte – Ruhezeitprüfung nach §5 ArbZG (Mindestens 11h Ruhezeit zwischen Arbeitstagen)');

  // Run rest time check to show results
  try {
    const checkBtns = await page.$$('button');
    for (const btn of checkBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text.includes('Prüfen')) {
        await btn.click();
        await sleep(1500);
        await page.evaluate(() => window.scrollTo(0, 1200));
        await takeScreenshot(page, 'admin_reports_ruhezeit_result', 'Berichte – Ruhezeitprüfung: Ergebnisanzeige mit Verstößen pro Mitarbeiter');
        break;
      }
    }
  } catch (e) {}

  // Fehler-Monitoring
  console.log('\n── Admin: Fehler-Monitoring');
  await page.goto(`${BASE_URL}/admin/errors`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'admin_errors', 'Fehler-Monitoring – Aggregierte Systemfehler mit Status-Filterung (Offen/Ignoriert/Behoben)');

  // Änderungsanträge
  console.log('\n── Admin: Änderungsanträge');
  await page.goto(`${BASE_URL}/admin/change-requests`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'admin_change_requests', 'Änderungsanträge – Mitarbeiter-Anträge zur Korrektur von Zeiteinträgen (Genehmigen/Ablehnen)');

  // Änderungsprotokoll
  console.log('\n── Admin: Änderungsprotokoll');
  await page.goto(`${BASE_URL}/admin/audit-log`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'admin_audit_log', 'Änderungsprotokoll – Vollständige Revisions-Historie aller Datenänderungen');

  // MA: Änderungsanträge (employee view)
  console.log('\n── MA: Änderungsanträge');
  await logout(page);
  await login(page, EMP_USER, EMP_PASS);
  await page.goto(`${BASE_URL}/change-requests`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, 'ma_change_requests', 'Änderungsanträge (Mitarbeiter) – Anträge für Korrekturen an vergangenen Zeiteinträgen stellen');

  await browser.close();
  console.log(`\n✅ ${Object.keys(screenshots).length} Screenshots aufgenommen\n`);
}

function img(key) {
  if (!screenshots[key]) return `<div class="no-screenshot">Screenshot nicht verfügbar</div>`;
  return `<figure>
    <img src="data:image/png;base64,${screenshots[key].data}" alt="${screenshots[key].description}" />
    <figcaption>${screenshots[key].description}</figcaption>
  </figure>`;
}

function generateHTML() {
  const today = new Date().toLocaleDateString('de-DE', { year: 'numeric', month: 'long', day: 'numeric' });
  return `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>PraxisZeit – Produkthandbuch</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; background: #fff; font-size: 14px; line-height: 1.6; }

  /* Cover */
  .cover { width: 100%; min-height: 100vh; background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 80px 40px; page-break-after: always; }
  .cover-logo { width: 120px; height: 120px; background: rgba(255,255,255,0.15); border-radius: 28px; display: flex; align-items: center; justify-content: center; margin: 0 auto 40px; font-size: 64px; }
  .cover h1 { color: #fff; font-size: 56px; font-weight: 800; letter-spacing: -1px; margin-bottom: 16px; }
  .cover h2 { color: rgba(255,255,255,0.85); font-size: 28px; font-weight: 300; margin-bottom: 60px; }
  .cover-divider { width: 80px; height: 3px; background: rgba(255,255,255,0.4); margin: 0 auto 60px; }
  .cover-meta { color: rgba(255,255,255,0.7); font-size: 16px; line-height: 2; }
  .cover-meta strong { color: #fff; }

  /* TOC */
  .toc { padding: 60px 80px; page-break-after: always; }
  .toc h2 { font-size: 32px; font-weight: 700; color: #2563eb; margin-bottom: 40px; padding-bottom: 16px; border-bottom: 3px solid #dbeafe; }
  .toc-section { margin-bottom: 10px; }
  .toc-chapter { font-size: 17px; font-weight: 600; color: #1e3a8a; padding: 8px 0; border-bottom: 1px solid #f3f4f6; display: flex; justify-content: space-between; }
  .toc-item { font-size: 14px; color: #4b5563; padding: 4px 0 4px 24px; display: flex; justify-content: space-between; }
  .toc-page { color: #9ca3af; }

  /* Page structure */
  .chapter { padding: 60px 80px; page-break-before: always; }
  .chapter-header { margin-bottom: 48px; padding-bottom: 20px; border-bottom: 3px solid #dbeafe; }
  .chapter-number { font-size: 13px; font-weight: 600; color: #3b82f6; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
  .chapter-title { font-size: 36px; font-weight: 800; color: #1e3a8a; }
  .chapter-subtitle { font-size: 16px; color: #6b7280; margin-top: 8px; }

  h3 { font-size: 22px; font-weight: 700; color: #1e40af; margin: 40px 0 20px; padding-left: 16px; border-left: 4px solid #2563eb; }
  h4 { font-size: 17px; font-weight: 600; color: #374151; margin: 28px 0 12px; }
  p { margin-bottom: 14px; color: #374151; }

  /* Feature box */
  .feature-box { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px; padding: 20px 24px; margin: 20px 0 28px; }
  .feature-box h4 { margin: 0 0 10px; color: #1d4ed8; font-size: 15px; }
  .feature-box ul { list-style: none; padding: 0; }
  .feature-box li { padding: 4px 0 4px 22px; position: relative; color: #1e40af; font-size: 13px; }
  .feature-box li::before { content: '✓'; position: absolute; left: 0; color: #2563eb; font-weight: 700; }

  .info-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px 20px; margin: 16px 0; }
  .info-box p { color: #166534; margin: 0; font-size: 13px; }
  .warn-box { background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px; padding: 16px 20px; margin: 16px 0; }
  .warn-box p { color: #92400e; margin: 0; font-size: 13px; }

  /* Screenshots */
  figure { margin: 24px 0 36px; }
  figure img { width: 100%; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.10); display: block; }
  figcaption { text-align: center; font-size: 12px; color: #6b7280; margin-top: 10px; font-style: italic; }
  .no-screenshot { padding: 40px; background: #f9fafb; border: 2px dashed #e5e7eb; border-radius: 12px; text-align: center; color: #9ca3af; }

  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 20px 0; }

  /* Step list */
  .steps { counter-reset: step; list-style: none; padding: 0; margin: 20px 0; }
  .steps li { counter-increment: step; display: flex; gap: 16px; margin-bottom: 16px; align-items: flex-start; }
  .steps li::before { content: counter(step); background: #2563eb; color: #fff; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; margin-top: 2px; }

  /* Role badge */
  .role-badge { display: inline-block; padding: 4px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-bottom: 20px; }
  .role-admin { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
  .role-employee { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }

  /* Table */
  table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }
  th { background: #2563eb; color: #fff; padding: 10px 14px; text-align: left; font-weight: 600; }
  td { padding: 9px 14px; border-bottom: 1px solid #f3f4f6; }
  tr:nth-child(even) td { background: #f9fafb; }

  /* Footer-like section */
  .page-footer { margin-top: 60px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; display: flex; justify-content: space-between; }

  @media print {
    .chapter { page-break-before: always; }
    h3 { page-break-after: avoid; }
    figure { page-break-inside: avoid; }
  }
</style>
</head>
<body>

<!-- ═══ COVER ═══ -->
<div class="cover">
  <div class="cover-logo">🕐</div>
  <h1>PraxisZeit</h1>
  <h2>Produkthandbuch & Benutzeranleitung</h2>
  <div class="cover-divider"></div>
  <div class="cover-meta">
    <div><strong>Version:</strong> 1.0 – Februar 2026</div>
    <div><strong>Erstellt am:</strong> ${today}</div>
    <div><strong>Zielgruppe:</strong> Mitarbeiter &amp; Administratoren</div>
    <div style="margin-top:20px;font-size:13px;opacity:0.6;">Zeiterfassungssystem für Arztpraxen und kleine Unternehmen</div>
  </div>
</div>

<!-- ═══ TOC ═══ -->
<div class="toc">
  <h2>Inhaltsverzeichnis</h2>

  <div class="toc-section">
    <div class="toc-chapter"><span>1 &nbsp; Einführung</span><span class="toc-page">3</span></div>
    <div class="toc-item"><span>1.1 Systemübersicht</span></div>
    <div class="toc-item"><span>1.2 Anmeldung</span></div>
    <div class="toc-item"><span>1.3 Navigation</span></div>
  </div>

  <div class="toc-section" style="margin-top:16px">
    <div class="toc-chapter"><span>2 &nbsp; Mitarbeiter-Handbuch</span><span class="toc-page">6</span></div>
    <div class="toc-item"><span>2.1 Dashboard &amp; Stempeluhr</span></div>
    <div class="toc-item"><span>2.2 Zeiterfassung</span></div>
    <div class="toc-item"><span>2.3 Abwesenheiten</span></div>
    <div class="toc-item"><span>2.4 Änderungsanträge</span></div>
    <div class="toc-item"><span>2.5 Profil</span></div>
  </div>

  <div class="toc-section" style="margin-top:16px">
    <div class="toc-chapter"><span>3 &nbsp; Administrator-Handbuch</span><span class="toc-page">14</span></div>
    <div class="toc-item"><span>3.1 Admin-Dashboard</span></div>
    <div class="toc-item"><span>3.2 Benutzerverwaltung</span></div>
    <div class="toc-item"><span>3.3 Abwesenheitsverwaltung</span></div>
    <div class="toc-item"><span>3.4 Berichte &amp; Excel-Export</span></div>
    <div class="toc-item"><span>3.5 Fehler-Monitoring</span></div>
    <div class="toc-item"><span>3.6 Änderungsanträge &amp; Protokoll</span></div>
  </div>

  <div class="toc-section" style="margin-top:16px">
    <div class="toc-chapter"><span>4 &nbsp; Technische Referenz</span><span class="toc-page">24</span></div>
    <div class="toc-item"><span>4.1 Rollenkonzept</span></div>
    <div class="toc-item"><span>4.2 Abwesenheitstypen</span></div>
    <div class="toc-item"><span>4.3 Berechnungsregeln</span></div>
    <div class="toc-item"><span>4.4 Gesetzliche Anforderungen</span></div>
  </div>
</div>

<!-- ═══ KAPITEL 1: EINFÜHRUNG ═══ -->
<div class="chapter">
  <div class="chapter-header">
    <div class="chapter-number">Kapitel 1</div>
    <div class="chapter-title">Einführung</div>
    <div class="chapter-subtitle">Systemübersicht, Anmeldung und Navigation</div>
  </div>

  <h3>1.1 Systemübersicht</h3>
  <p>PraxisZeit ist ein vollständiges Zeiterfassungssystem für Arztpraxen und kleine Unternehmen. Es ermöglicht Mitarbeitern, ihre Arbeitszeiten digital zu erfassen, Abwesenheiten zu verwalten und den aktuellen Stand ihres Urlaubskontos einzusehen.</p>

  <div class="feature-box">
    <h4>Funktionsumfang im Überblick</h4>
    <ul>
      <li>Tägliche Zeiterfassung (Von/Bis/Pause) mit Wochenansicht</li>
      <li>Stempeluhr: Einstempeln und Ausstempeln per Knopfdruck</li>
      <li>Automatische Berechnung von Soll/Ist-Stunden und Überstunden</li>
      <li>Abwesenheitsverwaltung (Urlaub, Krank, Fortbildung, Sonstiges)</li>
      <li>Gesetzliche Feiertage automatisch berücksichtigt (konfigurierbar je Bundesland)</li>
      <li>Excel-Exporte für Lohnbuchhaltung (Monats- und Jahresreport)</li>
      <li>PWA-fähig: Nutzbar als App auf Smartphone und Tablet</li>
    </ul>
  </div>

  <table>
    <tr><th>Benutzerrolle</th><th>Beschreibung</th><th>Zugang</th></tr>
    <tr><td><strong>Mitarbeiter</strong></td><td>Erfasst eigene Zeiten und Abwesenheiten</td><td>Eigene Daten</td></tr>
    <tr><td><strong>Administrator</strong></td><td>Verwaltet alle Mitarbeiter, Berichte und Systemeinstellungen</td><td>Alle Daten</td></tr>
  </table>

  <h3>1.2 Anmeldung</h3>
  <p>Die Anmeldung erfolgt mit Benutzername und Passwort. Benutzernamen werden vom Administrator vergeben. Die E-Mail-Adresse ist optional.</p>

  ${img('login_empty')}
  ${img('login_filled')}

  <div class="info-box"><p>💡 <strong>Tipp:</strong> Das Passwort kann nach der Anmeldung unter „Profil" geändert werden. Vergessene Passwörter müssen vom Administrator zurückgesetzt werden.</p></div>

  <h3>1.3 Navigation</h3>
  <p>Die Anwendung ist in zwei Bereiche unterteilt: Den Mitarbeiterbereich (linke Seitenleiste) und den Administratorbereich (sichtbar für Admins). Auf Mobilgeräten öffnet sich die Navigation über das Hamburger-Menü (☰) oben links.</p>

  <table>
    <tr><th>Menüpunkt</th><th>Beschreibung</th><th>Rolle</th></tr>
    <tr><td>Dashboard</td><td>Monatsübersicht, Stempeluhr, Urlaubskonto</td><td>Alle</td></tr>
    <tr><td>Zeiterfassung</td><td>Wochenansicht, Einträge erstellen/bearbeiten</td><td>Alle</td></tr>
    <tr><td>Abwesenheiten</td><td>Kalender, Urlaub/Krank eintragen</td><td>Alle</td></tr>
    <tr><td>Änderungsanträge</td><td>Korrekturen beantragen</td><td>Alle</td></tr>
    <tr><td>Admin-Dashboard</td><td>Teamübersicht</td><td>Admin</td></tr>
    <tr><td>Benutzerverwaltung</td><td>Mitarbeiter anlegen und verwalten</td><td>Admin</td></tr>
    <tr><td>Abwesenheiten (Admin)</td><td>Team-Abwesenheiten und Betriebsferien</td><td>Admin</td></tr>
    <tr><td>Berichte</td><td>Excel-Export und Ruhezeitprüfung</td><td>Admin</td></tr>
    <tr><td>Fehler-Monitoring</td><td>Systemfehler überwachen</td><td>Admin</td></tr>
  </table>
</div>

<!-- ═══ KAPITEL 2: MITARBEITER ═══ -->
<div class="chapter">
  <div class="chapter-header">
    <div class="chapter-number">Kapitel 2</div>
    <div class="chapter-title">Mitarbeiter-Handbuch</div>
    <div class="chapter-subtitle">Alle Funktionen aus Mitarbeiter-Perspektive</div>
  </div>
  <span class="role-badge role-employee">Rolle: Mitarbeiter</span>

  <h3>2.1 Dashboard &amp; Stempeluhr</h3>
  <p>Das Dashboard ist die Startseite nach der Anmeldung. Es zeigt auf einen Blick den aktuellen Monatsstatus, das Überstundenkonto und den verfügbaren Resturlaub.</p>

  ${img('ma_dashboard')}

  <h4>Statuskarten</h4>
  <table>
    <tr><th>Karte</th><th>Bedeutung</th></tr>
    <tr><td><strong>Monatssaldo</strong></td><td>Differenz zwischen Ist-Stunden (gearbeitet) und Soll-Stunden (Pflicht) im laufenden Monat</td></tr>
    <tr><td><strong>Überstundenkonto</strong></td><td>Kumulierte Überstunden seit dem ersten Zeiteintrag</td></tr>
    <tr><td><strong>Urlaubskonto</strong></td><td>Budget, verbrauchte und verbleibende Urlaubstage mit Ampel-System</td></tr>
    <tr><td><strong>Nächster Urlaub</strong></td><td>Countdown bis zum nächsten eingetragenen Urlaub</td></tr>
  </table>

  <div class="info-box"><p>💡 <strong>Urlaubsampel:</strong> Grün = mehr als 50% verbleibend · Gelb = 25–50% verbleibend · Rot = weniger als 25% verbleibend</p></div>

  <h4>Stempeluhr</h4>
  <p>Die Stempeluhr ermöglicht das einfache Erfassen des Arbeitsbeginns und -endes per Knopfdruck, ohne die Zeiterfassungsmaske manuell auszufüllen.</p>

  ${img('ma_stempeluhr_ein')}
  ${img('ma_stempeluhr_aus')}

  <ol class="steps">
    <li>Auf <strong>„Einstempeln"</strong> klicken, wenn die Arbeit beginnt – die aktuelle Uhrzeit wird automatisch als Startzeit gespeichert.</li>
    <li>Auf <strong>„Ausstempeln"</strong> klicken, wenn die Arbeit endet – die Endzeit und ein Zeiteintrag werden angelegt.</li>
    <li>Der Zeiteintrag erscheint anschließend in der Wochenansicht der Zeiterfassung.</li>
  </ol>

  ${img('ma_dashboard_full')}

  <h3>2.2 Zeiterfassung</h3>
  <p>Die Zeiterfassung zeigt eine Wochenansicht von Montag bis Sonntag. Für jeden Tag werden Startzeit, Endzeit, Pause und die resultierenden Netto-Arbeitsstunden angezeigt. Grüne Zahlen zeigen Übererfüllung, rote Zahlen Untererfüllung des Tagessolls.</p>

  ${img('ma_zeiterfassung')}

  <h4>Neuen Zeiteintrag erstellen</h4>
  <p>Klicken Sie auf den <strong>„+"</strong>-Button oder direkt auf eine Zeile, um das Formular für einen neuen Zeiteintrag zu öffnen.</p>

  ${img('ma_zeiteintrag_form')}

  <table>
    <tr><th>Feld</th><th>Beschreibung</th><th>Pflicht</th></tr>
    <tr><td>Datum</td><td>Tag der Arbeit</td><td>Ja</td></tr>
    <tr><td>Von</td><td>Arbeitsbeginn (Uhrzeit)</td><td>Ja</td></tr>
    <tr><td>Bis</td><td>Arbeitsende (Uhrzeit) – kann leer bleiben bei laufender Schicht</td><td>Nein</td></tr>
    <tr><td>Pause</td><td>Pausendauer in Minuten (wird von Arbeitszeit abgezogen)</td><td>Nein</td></tr>
    <tr><td>Notiz</td><td>Optionaler Kommentar zum Arbeitstag</td><td>Nein</td></tr>
  </table>

  <div class="warn-box"><p>⚠️ <strong>Hinweis:</strong> Bereits vergangene Zeiteinträge können bearbeitet werden. Bei sensiblen Korrekturen empfiehlt sich ein Änderungsantrag (Kapitel 2.4), der vom Administrator genehmigt wird.</p></div>

  <h4>Bearbeiten und Löschen</h4>
  <p>Klicken Sie auf einen bestehenden Zeiteintrag, um ihn zu bearbeiten. Zum Löschen verwenden Sie den Papierkorb-Button in der Eintrag-Zeile. Gelöschte Einträge können nicht wiederhergestellt werden.</p>

  <h3>2.3 Abwesenheiten</h3>
  <p>Die Abwesenheitsseite zeigt einen Monatskalender mit allen Team-Abwesenheiten farbcodiert nach Mitarbeiter, sowie darunter die eigenen Abwesenheiten als Liste.</p>

  ${img('ma_abwesenheiten')}

  <h4>Neue Abwesenheit eintragen</h4>
  <p>Klicken Sie auf einen Tag im Kalender oder auf den <strong>„Abwesenheit eintragen"</strong>-Button. Das Formular öffnet sich mit dem ausgewählten Datum vorausgefüllt.</p>

  ${img('ma_abwesenheit_form')}

  <table>
    <tr><th>Abwesenheitstyp</th><th>Farbe</th><th>Auswirkung</th></tr>
    <tr><td>Urlaub</td><td>Blau</td><td>Zieht Urlaubsbudget ab, reduziert Soll-Stunden</td></tr>
    <tr><td>Krank</td><td>Rot</td><td>Reduziert Soll-Stunden (kein Urlaubsabzug)</td></tr>
    <tr><td>Fortbildung</td><td>Orange</td><td>Reduziert Soll-Stunden</td></tr>
    <tr><td>Sonstiges</td><td>Grau</td><td>Reduziert Soll-Stunden</td></tr>
  </table>

  <h4>Zeitraum-Erfassung</h4>
  <p>Für mehrere aufeinanderfolgende Tage (z. B. Urlaubswochen) aktivieren Sie die <strong>„Zeitraum"</strong>-Checkbox. Das System erstellt automatisch separate Einträge für jeden Werktag im Zeitraum (Wochenenden und Feiertage werden übersprungen).</p>

  ${img('ma_abwesenheit_zeitraum')}

  <div class="info-box"><p>💡 <strong>Krank während Urlaub:</strong> Wenn Sie eine Krankheit im Urlaubszeitraum eintragen, bietet das System an, die betroffenen Urlaubstage automatisch zurückzubuchen.</p></div>

  ${img('ma_abwesenheiten_full')}

  <h3>2.4 Änderungsanträge</h3>
  <p>Möchten Sie einen vergangenen Zeiteintrag korrigieren, der bereits durch den Administrator bestätigt wurde, können Sie einen Änderungsantrag stellen. Der Administrator kann diesen genehmigen oder ablehnen.</p>

  ${img('ma_change_requests')}

  <ol class="steps">
    <li>Zur Seite <strong>„Änderungsanträge"</strong> navigieren.</li>
    <li>Auf <strong>„Neuer Antrag"</strong> klicken und den betreffenden Zeiteintrag auswählen.</li>
    <li>Die gewünschten korrigierten Werte (Von/Bis/Pause) eingeben und begründen.</li>
    <li>Nach Einreichung erscheint der Antrag mit Status <em>„Ausstehend"</em>.</li>
    <li>Der Administrator genehmigt oder lehnt den Antrag ab – Sie sehen das Ergebnis in der Übersicht.</li>
  </ol>

  <h3>2.5 Profil</h3>
  <p>Auf der Profilseite können Sie Ihr persönliches Passwort ändern und Ihre Stammdaten einsehen.</p>

  ${img('ma_profil')}

  <ol class="steps">
    <li>Auf <strong>„Profil"</strong> in der Navigation klicken.</li>
    <li>Im Abschnitt <strong>„Passwort ändern"</strong> das aktuelle und das neue Passwort eingeben.</li>
    <li>Das neue Passwort muss mindestens 8 Zeichen lang sein.</li>
    <li>Auf <strong>„Passwort ändern"</strong> klicken – eine Bestätigung erscheint.</li>
  </ol>
</div>

<!-- ═══ KAPITEL 3: ADMINISTRATOR ═══ -->
<div class="chapter">
  <div class="chapter-header">
    <div class="chapter-number">Kapitel 3</div>
    <div class="chapter-title">Administrator-Handbuch</div>
    <div class="chapter-subtitle">Benutzerverwaltung, Berichte und Systemüberwachung</div>
  </div>
  <span class="role-badge role-admin">Rolle: Administrator</span>

  <h3>3.1 Admin-Dashboard</h3>
  <p>Das Admin-Dashboard gibt einen vollständigen Überblick über das gesamte Team: aktuelle Stundensalden, Urlaubskonten und Jahres-Abwesenheitsstatistiken aller Mitarbeiter auf einen Blick.</p>

  ${img('admin_dashboard')}

  ${img('admin_dashboard_full')}

  <h4>Jahresend-Warnung (Q4)</h4>
  <p>Im vierten Quartal (Oktober–Dezember) zeigt das System automatisch eine Warnung, wenn Mitarbeiter noch offene Urlaubstage haben, die bis Jahresende verbraucht werden müssen.</p>

  <div class="warn-box"><p>⚠️ Die Verfallsfrist für Urlaubsübertrag ist standardmäßig der <strong>31. März des Folgejahres</strong>. Pro Mitarbeiter kann eine individuelle Frist in der Benutzerverwaltung hinterlegt werden.</p></div>

  <h3>3.2 Benutzerverwaltung</h3>
  <p>Unter <strong>„Benutzerverwaltung"</strong> werden alle Mitarbeiterkonten angelegt, bearbeitet und verwaltet. Die Liste zeigt eine Übersicht mit Urlaubskonto-Ampel für jeden Mitarbeiter.</p>

  ${img('admin_users_list')}

  <h4>Neuen Mitarbeiter anlegen</h4>
  <p>Klicken Sie auf <strong>„+ Neuer Benutzer"</strong>, um das Anmeldeformular zu öffnen.</p>

  ${img('admin_user_create')}

  <table>
    <tr><th>Feld</th><th>Beschreibung</th></tr>
    <tr><td>Benutzername</td><td>Eindeutiger Login-Name (z. B. Vorname.Nachname)</td></tr>
    <tr><td>E-Mail</td><td>Optional – wird nicht für Login benötigt</td></tr>
    <tr><td>Passwort</td><td>Initiales Passwort (min. 8 Zeichen), kann vom MA später geändert werden</td></tr>
    <tr><td>Wochenstunden</td><td>Vertraglich vereinbarte Wochenstunden (z. B. 40, 30, 20)</td></tr>
    <tr><td>Arbeitstage/Woche</td><td>Anzahl der regulären Arbeitstage (1–7)</td></tr>
    <tr><td>Urlaubstage</td><td>Jährliches Urlaubsbudget in Tagen</td></tr>
    <tr><td>Stundenzählung</td><td>Deaktivieren für Mitarbeiter ohne Arbeitszeitpflicht (Soll = 0)</td></tr>
  </table>

  <h4>Mitarbeiter bearbeiten</h4>

  ${img('admin_user_edit')}

  <h4>Individuelle Tagesstunden</h4>
  <p>Für Mitarbeiter mit unterschiedlichen Stunden pro Wochentag (z. B. Teilzeit mit variablen Tagen) kann die Funktion <strong>„Individuelle Tagesstunden"</strong> aktiviert werden.</p>

  ${img('admin_user_daily_schedule')}

  <div class="info-box"><p>💡 Bei aktiviertem Tagesplan werden Abwesenheits-Stunden automatisch aus dem Tagesplan des jeweiligen Wochentags berechnet. Die Eingabe manueller Stundenzahlen im Abwesenheitsformular entfällt.</p></div>

  <h4>Passwort setzen</h4>
  <p>Administratoren können das Passwort eines Mitarbeiters jederzeit neu setzen (z. B. bei vergessenem Passwort). Klicken Sie dazu auf das Schlüssel-Symbol (🔑) in der Benutzerliste.</p>

  <h4>Arbeitszeit-Historie</h4>
  <p>Bei Teilzeit-Änderungen oder Stundenanpassungen muss die neue Wochenstundenzahl mit einem Wirkungsdatum hinterlegt werden. Das System berücksichtigt die Historie bei allen historischen Berechnungen automatisch.</p>

  ${img('admin_user_stunden_modal')}

  <ol class="steps">
    <li>Auf das Uhr-Symbol bei einem Mitarbeiter klicken.</li>
    <li>Neues Wirkungsdatum und neue Wochenstundenzahl eingeben.</li>
    <li>Optionale Notiz hinzufügen (z. B. „Teilzeit ab 01.03.2026").</li>
    <li>Auf <strong>„Hinzufügen"</strong> klicken – die Änderung wird sofort wirksam.</li>
  </ol>

  <h3>3.3 Abwesenheitsverwaltung</h3>
  <p>Admins können Abwesenheiten für alle Mitarbeiter verwalten und Betriebsferien für das gesamte Team anlegen.</p>

  ${img('admin_absences_tab1')}

  <h4>Betriebsferien anlegen</h4>
  <p>Betriebsferien werden einmal angelegt und automatisch für alle aktiven Mitarbeiter als Urlaub eingetragen. Beim Löschen werden die zugehörigen Einträge automatisch entfernt.</p>

  ${img('admin_absences_betriebsferien')}

  <ol class="steps">
    <li>Auf den Tab <strong>„Betriebsferien"</strong> wechseln.</li>
    <li>Name der Betriebsferien eingeben (z. B. „Weihnachtsferien 2026").</li>
    <li>Start- und Enddatum auswählen.</li>
    <li>Auf <strong>„Anlegen"</strong> klicken – das System trägt für alle aktiven Mitarbeiter automatisch Urlaub ein.</li>
  </ol>

  <div class="warn-box"><p>⚠️ Beim Löschen von Betriebsferien werden alle automatisch erstellten Abwesenheits-Einträge der Mitarbeiter gelöscht. Manuell hinzugefügte Abwesenheiten an denselben Tagen bleiben erhalten.</p></div>

  <h3>3.4 Berichte &amp; Excel-Export</h3>
  <p>Unter <strong>„Berichte"</strong> stehen drei verschiedene Excel-Exportformate sowie eine gesetzliche Ruhezeitprüfung zur Verfügung.</p>

  ${img('admin_reports_top')}

  <h4>Exportformate im Überblick</h4>
  <table>
    <tr><th>Format</th><th>Inhalt</th><th>Verwendung</th></tr>
    <tr><td><strong>Monatsreport</strong></td><td>1 Tab/MA · Tägl. Einträge · Soll/Ist/Saldo · Urlaubstage</td><td>Lohnbuchhaltung, monatliche Abrechnung</td></tr>
    <tr><td><strong>Jahresreport Classic</strong></td><td>1 Tab/MA · 12 Monate als Spalten · Überstunden kumuliert</td><td>Geschäftsführung, Jahresüberblick</td></tr>
    <tr><td><strong>Jahresreport Detailliert</strong></td><td>1 Tab/MA · 365 Tage · Alle Zeiteinträge</td><td>Detaillierte Analyse, Steuerberater</td></tr>
  </table>

  <div class="info-box"><p>💡 Alle Exports berücksichtigen Feiertage, historische Stundenänderungen und Abwesenheiten korrekt. Die Datei kann direkt an die Lohnbuchhaltung weitergeleitet werden.</p></div>

  ${img('admin_reports_full')}

  <h4>Ruhezeitprüfung (§5 ArbZG)</h4>
  <p>Die Ruhezeitprüfung analysiert alle Zeiteinträge und meldet Verstöße, bei denen die gesetzlich vorgeschriebene Mindestruhezeit zwischen zwei Arbeitstagen unterschritten wurde.</p>

  ${img('admin_reports_ruhezeit')}
  ${img('admin_reports_ruhezeit_result')}

  <table>
    <tr><th>Parameter</th><th>Beschreibung</th><th>Standard</th></tr>
    <tr><td>Jahr</td><td>Zu prüfendes Kalenderjahr</td><td>Aktuelles Jahr</td></tr>
    <tr><td>Monat</td><td>Optional: nur einen Monat prüfen</td><td>Ganzes Jahr</td></tr>
    <tr><td>Mindestruhezeit</td><td>Erlaubter Mindeststunden-Abstand zwischen zwei Schichten</td><td>11 Stunden</td></tr>
  </table>

  <h3>3.5 Fehler-Monitoring</h3>
  <p>Das Fehler-Monitoring zeigt alle vom System protokollierten Fehler aggregiert an. Gleiche Fehler werden zusammengefasst und ein Zähler zeigt, wie oft sie aufgetreten sind.</p>

  ${img('admin_errors')}

  <table>
    <tr><th>Status</th><th>Bedeutung</th></tr>
    <tr><td><strong>Offen</strong></td><td>Fehler wurde noch nicht bearbeitet – Handlungsbedarf</td></tr>
    <tr><td><strong>Ignoriert</strong></td><td>Fehler ist bekannt, wird aber nicht behoben (z. B. externe Abhängigkeit)</td></tr>
    <tr><td><strong>Behoben</strong></td><td>Problem wurde gelöst – wird zur Dokumentation aufbewahrt</td></tr>
  </table>

  <h4>GitHub-Issue erstellen</h4>
  <p>Über die Erweiterungsansicht (▼) eines Fehlers kann direkt ein vorausgefülltes GitHub-Issue erstellt werden. Titel und Beschreibung mit Stack Trace werden automatisch generiert.</p>

  <div class="info-box"><p>💡 Fehler mit Status „Ignoriert" werden weiterhin gezählt (Count erhöht sich), erscheinen jedoch nicht in der Standardansicht „Offen".</p></div>

  <h3>3.6 Änderungsanträge &amp; Protokoll</h3>

  <h4>Änderungsanträge (Admin)</h4>
  <p>Mitarbeiter können Korrekturen an ihren Zeiteinträgen beantragen. Admins sehen alle offenen Anträge mit dem Vergleich Alt/Neu und können genehmigen oder ablehnen.</p>

  ${img('admin_change_requests')}

  <h4>Änderungsprotokoll</h4>
  <p>Das Änderungsprotokoll (Audit Log) dokumentiert alle Datenänderungen im System mit Timestamp und verantwortlichem Benutzer. Es dient der Nachvollziehbarkeit und Compliance.</p>

  ${img('admin_audit_log')}
</div>

<!-- ═══ KAPITEL 4: TECHNISCHE REFERENZ ═══ -->
<div class="chapter">
  <div class="chapter-header">
    <div class="chapter-number">Kapitel 4</div>
    <div class="chapter-title">Technische Referenz</div>
    <div class="chapter-subtitle">Berechnungsregeln, Rollenkonzept und gesetzliche Anforderungen</div>
  </div>

  <h3>4.1 Rollenkonzept</h3>
  <table>
    <tr><th>Funktion</th><th>Mitarbeiter</th><th>Admin</th></tr>
    <tr><td>Eigene Zeiteinträge erfassen</td><td>✓</td><td>✓</td></tr>
    <tr><td>Eigene Abwesenheiten eintragen</td><td>✓</td><td>✓</td></tr>
    <tr><td>Stempeluhr nutzen</td><td>✓</td><td>✓</td></tr>
    <tr><td>Eigenes Passwort ändern</td><td>✓</td><td>✓</td></tr>
    <tr><td>Zeiteinträge anderer Mitarbeiter sehen</td><td>–</td><td>✓</td></tr>
    <tr><td>Mitarbeiter anlegen / bearbeiten</td><td>–</td><td>✓</td></tr>
    <tr><td>Abwesenheiten für andere eintragen</td><td>–</td><td>✓</td></tr>
    <tr><td>Excel-Reports exportieren</td><td>–</td><td>✓</td></tr>
    <tr><td>Betriebsferien anlegen</td><td>–</td><td>✓</td></tr>
    <tr><td>Fehler-Monitoring</td><td>–</td><td>✓</td></tr>
    <tr><td>Passwörter anderer zurücksetzen</td><td>–</td><td>✓</td></tr>
  </table>

  <h3>4.2 Abwesenheitstypen</h3>
  <table>
    <tr><th>Typ</th><th>Code</th><th>Urlaubsabzug</th><th>Soll-Reduktion</th></tr>
    <tr><td>Urlaub</td><td>vacation</td><td>Ja</td><td>Ja</td></tr>
    <tr><td>Krank</td><td>sick</td><td>Nein</td><td>Ja</td></tr>
    <tr><td>Fortbildung</td><td>training</td><td>Nein</td><td>Ja</td></tr>
    <tr><td>Sonstiges</td><td>other</td><td>Nein</td><td>Ja</td></tr>
  </table>

  <h3>4.3 Berechnungsregeln</h3>

  <h4>Tages-Soll-Berechnung</h4>
  <p><strong>Standard:</strong> Wochenstunden ÷ Arbeitstage pro Woche = Tages-Soll</p>
  <p><strong>Mit Tagesplan:</strong> Der für den jeweiligen Wochentag (Mo–Fr) hinterlegte Stundenwert</p>
  <p><strong>Ausnahmen (Soll = 0):</strong> Wochenenden · Gesetzliche Feiertage · Abwesenheitstage</p>

  <h4>Überstunden-Konto</h4>
  <p>Das Überstundenkonto ergibt sich aus der Summe aller monatlichen Salden (Ist − Soll) seit dem ersten Zeiteintrag. Es akkumuliert sich über Monate und Jahre.</p>

  <h4>Urlaubskonto</h4>
  <p>Budget = Jahresurlaubstage × Tages-Soll-Stunden. Verbraucht = Summe aller Urlaubs-Stunden im Jahr. Verbleibend = Budget − Verbraucht.</p>

  <h4>Feiertage</h4>
  <p>Feiertage werden automatisch über die <em>workalendar</em>-Bibliothek synchronisiert. Das Bundesland ist per Umgebungsvariable <code>HOLIDAY_STATE</code> konfigurierbar (Standard: Bayern). Alle 16 Bundesländer werden unterstützt.</p>

  <h3>4.4 Gesetzliche Anforderungen</h3>
  <table>
    <tr><th>Vorschrift</th><th>Anforderung</th><th>Umsetzung in PraxisZeit</th></tr>
    <tr><td>§3 ArbZG</td><td>Max. 8h/Tag regulär, bis 10h mit Ausgleich</td><td>Zeiterfassung mit exakter Stundenauswertung</td></tr>
    <tr><td>§5 ArbZG</td><td>Min. 11h Ruhezeit zwischen Arbeitstagen</td><td>Ruhezeitprüfung in Berichte-Modul</td></tr>
    <tr><td>§6 BUrlG</td><td>Min. 24 Werktage Jahresurlaub (Vollzeit)</td><td>Konfigurierbares Urlaubsbudget pro Mitarbeiter</td></tr>
    <tr><td>DSGVO</td><td>Datenschutz und Zugriffsrechte</td><td>Rollenbasierter Zugriff, kein Cross-User-Zugriff für MA</td></tr>
  </table>

  <div class="page-footer">
    <span>PraxisZeit – Produkthandbuch v1.0</span>
    <span>Stand: ${today}</span>
    <span>Vertraulich – Nur für interne Verwendung</span>
  </div>
</div>

</body>
</html>`;
}

(async () => {
  console.log('PraxisZeit Produkthandbuch Generator');
  console.log('=====================================');

  await run();

  console.log('📝 Generiere HTML...');
  const html = generateHTML();
  fs.writeFileSync(OUTPUT_HTML, html, 'utf-8');
  console.log(`✅ HTML gespeichert: ${OUTPUT_HTML} (${(fs.statSync(OUTPUT_HTML).size / 1024 / 1024).toFixed(1)} MB)`);

  console.log('📄 Erstelle PDF...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: 'networkidle0' });
  await page.pdf({
    path: OUTPUT_PDF,
    format: 'A4',
    printBackground: true,
    margin: { top: '20mm', bottom: '20mm', left: '15mm', right: '15mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div style="font-size:9px;color:#9ca3af;width:100%;text-align:right;padding-right:15mm;">PraxisZeit – Produkthandbuch</div>',
    footerTemplate: '<div style="font-size:9px;color:#9ca3af;width:100%;text-align:center;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  });
  await browser.close();

  const pdfSize = (fs.statSync(OUTPUT_PDF).size / 1024 / 1024).toFixed(1);
  console.log(`✅ PDF gespeichert: ${OUTPUT_PDF} (${pdfSize} MB)`);
  console.log('\n🎉 Fertig!');
})();
