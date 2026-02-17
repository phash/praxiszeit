/**
 * PraxisZeit Handbuch-Generator
 * Erstellt drei separate Dokumente:
 *   1. Mitarbeiter-Handbuch (PDF)
 *   2. Admin-Handbuch (PDF)
 *   3. Cheat-Sheet (PDF)
 */
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost';
const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';
const EMP_USER = 'sophie.schmidt@praxis.de';
const EMP_PASS = 'Mitarbeiter2026!';

const scr = {};   // screenshot store: name → base64

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, name, desc, full = false) {
  await sleep(700);
  const buf = await page.screenshot({ fullPage: full, type: 'png' });
  scr[name] = { data: buf.toString('base64'), desc };
  console.log(`  📸 ${name}${full ? ' (full)' : ''}`);
}

async function login(page, user, pass) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await page.waitForSelector('input', { timeout: 10000 });
  await sleep(400);
  const inp = await page.$$('input');
  await inp[0].click({ clickCount: 3 }); await inp[0].type(user);
  await inp[1].click({ clickCount: 3 }); await inp[1].type(pass);
  await page.click('button[type="submit"]');
  await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(800);
}

async function logout(page) {
  try {
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
    await sleep(300);
  } catch (_) {}
}

// ─────────────────────────────────────────────────────────────────────────────
// SCREENSHOT CAPTURE
// ─────────────────────────────────────────────────────────────────────────────
async function captureAll(browser) {
  const page = await browser.newPage();

  // ── LOGIN
  console.log('\n── Login-Seite');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await sleep(400);
  await shot(page, 'login', 'Anmeldeseite von PraxisZeit');

  // ── MITARBEITER
  console.log('\n── Mitarbeiter: Sophie Schmidt');
  await login(page, EMP_USER, EMP_PASS);

  console.log('── MA: Dashboard');
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });
  await sleep(600);
  await shot(page, 'ma_dashboard', 'Dashboard – Übersicht des aktuellen Monats, Stempeluhr');

  console.log('── MA: Stempeluhr (Fokus)');
  // Scroll down to show stempeluhr widget area
  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(400);
  await shot(page, 'ma_stempeluhr', 'Stempeluhr-Widget zum Ein- und Ausstempeln');

  console.log('── MA: Zeiterfassung');
  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(600);
  await shot(page, 'ma_zeiterfassung', 'Zeiterfassung – Wochenansicht mit täglichen Einträgen');

  // Open new entry form
  try {
    const addBtn = await page.$('button[title*="inzufügen"], button[title*="Eintrag"], button:has-text("+ Eintrag")');
    if (!addBtn) {
      // Find by text
      const btns = await page.$$('button');
      for (const b of btns) {
        const txt = await page.evaluate(el => el.textContent, b);
        if (txt && (txt.includes('Eintrag') || txt.includes('+') || txt.includes('hinzufügen'))) {
          await b.click();
          break;
        }
      }
    } else {
      await addBtn.click();
    }
    await sleep(700);
    await shot(page, 'ma_zeiteintrag_form', 'Formular zum Erfassen eines neuen Zeiteintrags');
    // Close form
    const esc = await page.$('button[aria-label*="chließen"], button[title*="chließen"]');
    if (esc) await esc.click();
    else await page.keyboard.press('Escape');
    await sleep(400);
  } catch (_) {}

  console.log('── MA: Abwesenheiten');
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'ma_abwesenheiten', 'Abwesenheitskalender – Übersicht aller Abwesenheiten');

  // Click a weekday to open form
  try {
    const dayBtns = await page.$$('.cursor-pointer, [data-day], td button');
    for (const b of dayBtns) {
      const txt = await page.evaluate(el => el.textContent?.trim(), b);
      if (txt && /^\d+$/.test(txt) && parseInt(txt) >= 10 && parseInt(txt) <= 20) {
        await b.click();
        await sleep(700);
        const formVisible = await page.$('select, input[type="date"]');
        if (formVisible) {
          await shot(page, 'ma_abwesenheit_form', 'Formular zum Eintragen einer Abwesenheit (Urlaub, Krank usw.)');
          // Enable range
          try {
            const checkbox = await page.$('input[type="checkbox"]');
            if (checkbox) {
              await checkbox.click();
              await sleep(500);
              await shot(page, 'ma_abwesenheit_zeitraum', 'Zeitraum-Erfassung: Mehrere Tage auf einmal eintragen');
            }
          } catch (_) {}
          break;
        }
      }
    }
  } catch (_) {}

  console.log('── MA: Profil');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
  await sleep(600);
  await shot(page, 'ma_profil', 'Profilseite – Persönliche Daten und Passwort ändern');

  console.log('── MA: Änderungsanträge');
  await page.goto(`${BASE_URL}/change-requests`, { waitUntil: 'networkidle2' });
  await sleep(600);
  await shot(page, 'ma_aenderungsantraege', 'Änderungsanträge – Korrekturen beantragen');

  // ── ADMIN
  console.log('\n── Admin-Anmeldung');
  await logout(page);
  await login(page, ADMIN_USER, ADMIN_PASS);

  console.log('── Admin: Dashboard');
  await page.goto(`${BASE_URL}/admin`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_dashboard', 'Admin-Dashboard – Teamübersicht mit Stundensalden');
  await shot(page, 'admin_dashboard_full', 'Admin-Dashboard – vollständige Ansicht', true);

  console.log('── Admin: Benutzerverwaltung');
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_users', 'Benutzerverwaltung – Übersicht aller Mitarbeiter');

  // Open create form
  try {
    const createBtn = await page.$('button');
    const btns = await page.$$('button');
    for (const b of btns) {
      const txt = await page.evaluate(el => el.textContent?.trim(), b);
      if (txt && (txt.includes('Anlegen') || txt.includes('Neuer') || txt.includes('Hinzufügen') || txt.includes('+'))) {
        await b.click();
        await sleep(700);
        await shot(page, 'admin_user_anlegen', 'Formular: Neuen Mitarbeiter anlegen');
        await page.keyboard.press('Escape');
        await sleep(400);
        break;
      }
    }
  } catch (_) {}

  // Open edit form for first user
  try {
    await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
    await sleep(600);
    const editBtns = await page.$$('button[title*="earb"], button[title*="dit"]');
    if (editBtns.length > 0) {
      await editBtns[0].click();
      await sleep(700);
      await shot(page, 'admin_user_bearbeiten', 'Formular: Mitarbeiter-Daten bearbeiten (Arbeitszeiten, Rolle, Farbe)');

      // Enable daily schedule
      try {
        const checkboxes = await page.$$('input[type="checkbox"]');
        for (const cb of checkboxes) {
          const label = await page.evaluate(el => {
            const lbl = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
            return lbl ? lbl.textContent?.trim() : '';
          }, cb);
          if (label && (label.includes('Tagesplan') || label.includes('täglich') || label.includes('Tagesziel'))) {
            const checked = await page.evaluate(el => el.checked, cb);
            if (!checked) await cb.click();
            await sleep(600);
            await shot(page, 'admin_tagesplanung', 'Individuelle Tagesplanung: Stunden je Wochentag konfigurieren');
            break;
          }
        }
      } catch (_) {}

      await page.keyboard.press('Escape');
      await sleep(400);
    }
  } catch (_) {}

  // Stunden-Modal
  try {
    await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
    await sleep(600);
    const allBtns = await page.$$('button');
    for (const b of allBtns) {
      const txt = await page.evaluate(el => el.textContent?.trim(), b);
      if (txt && txt.includes('Std')) {
        await b.click();
        await sleep(700);
        await shot(page, 'admin_stunden_historie', 'Stundenhistorie: Änderungen der Wochenstunden nachverfolgen');
        await page.keyboard.press('Escape');
        await sleep(400);
        break;
      }
    }
  } catch (_) {}

  console.log('── Admin: Abwesenheiten');
  await page.goto(`${BASE_URL}/admin/absences`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_abwesenheiten', 'Admin: Urlaubsübersicht – Budget, Verbrauch und Resturlaub pro MA');

  // Switch tab
  try {
    const tabs = await page.$$('button[role="tab"], .tab-btn, nav button');
    for (const t of tabs) {
      const txt = await page.evaluate(el => el.textContent?.trim(), t);
      if (txt && (txt.includes('Kalender') || txt.includes('Betriebs') || txt.includes('Jahres'))) {
        await t.click();
        await sleep(600);
        await shot(page, 'admin_abwesenheiten_kalender', 'Teamkalender: Abwesenheiten aller Mitarbeiter im Überblick');
        break;
      }
    }
  } catch (_) {}

  console.log('── Admin: Berichte');
  await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_berichte', 'Berichte: Monats- und Jahresreports mit Excel-Export');
  await shot(page, 'admin_berichte_full', 'Berichte: vollständige Seite mit allen Export-Optionen', true);

  console.log('── Admin: Fehler-Monitoring');
  await page.goto(`${BASE_URL}/admin/errors`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_fehler', 'Fehler-Monitoring: Systemfehler überwachen und verwalten');

  console.log('── Admin: Änderungsanträge');
  await page.goto(`${BASE_URL}/admin/change-requests`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_aenderungen', 'Änderungsanträge: Korrekturen von Mitarbeitern prüfen und bearbeiten');

  console.log('── Admin: Audit-Log');
  await page.goto(`${BASE_URL}/admin/audit-log`, { waitUntil: 'networkidle2' });
  await sleep(700);
  await shot(page, 'admin_auditlog', 'Änderungsprotokoll: Alle Aktionen im System lückenlos dokumentiert');

  await browser.close();
  console.log(`\n✅ ${Object.keys(scr).length} Screenshots aufgenommen\n`);
}

// ─────────────────────────────────────────────────────────────────────────────
// IMG HELPER
// ─────────────────────────────────────────────────────────────────────────────
function img(name, caption = '') {
  if (!scr[name]) return '';
  return `
    <figure class="screenshot-block">
      <img src="data:image/png;base64,${scr[name].data}" alt="${scr[name].desc}" />
      ${caption ? `<figcaption>${caption}</figcaption>` : `<figcaption>${scr[name].desc}</figcaption>`}
    </figure>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED CSS
// ─────────────────────────────────────────────────────────────────────────────
function baseCss(accent = '#2563EB') {
  return `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1a1a2e; background: #fff; line-height: 1.65; }
  h1 { font-size: 26pt; color: ${accent}; margin-bottom: 8px; }
  h2 { font-size: 16pt; color: ${accent}; margin: 28px 0 10px; border-bottom: 2px solid ${accent}; padding-bottom: 5px; }
  h3 { font-size: 12pt; color: #1e40af; margin: 20px 0 8px; }
  h4 { font-size: 11pt; color: #374151; margin: 14px 0 6px; font-weight: 700; }
  p  { margin-bottom: 10px; }
  ul, ol { margin: 8px 0 12px 20px; }
  li { margin-bottom: 5px; }
  strong { color: #111; }
  .warn  { background: #fef3cd; border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 4px; margin: 14px 0; font-size: 10pt; }
  .info  { background: #e0f2fe; border-left: 4px solid #0ea5e9; padding: 10px 14px; border-radius: 4px; margin: 14px 0; font-size: 10pt; }
  .tip   { background: #d1fae5; border-left: 4px solid #10b981; padding: 10px 14px; border-radius: 4px; margin: 14px 0; font-size: 10pt; }
  .danger{ background: #fee2e2; border-left: 4px solid #ef4444; padding: 10px 14px; border-radius: 4px; margin: 14px 0; font-size: 10pt; }
  .page-break { page-break-before: always; }
  .cover { text-align: center; padding: 80px 40px; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; }
  .cover-logo { font-size: 48pt; font-weight: 900; color: ${accent}; letter-spacing: -2px; }
  .cover-sub  { font-size: 18pt; color: #6b7280; margin-top: 10px; }
  .cover-title{ font-size: 30pt; font-weight: 700; color: #111; margin: 40px 0 16px; }
  .cover-date { font-size: 11pt; color: #9ca3af; margin-top: 60px; }
  .section { max-width: 760px; margin: 0 auto; padding: 20px 40px; }
  .screenshot-block { margin: 16px 0; }
  .screenshot-block img { width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
  .screenshot-block figcaption { font-size: 9pt; color: #6b7280; text-align: center; margin-top: 5px; font-style: italic; }
  .checklist { list-style: none; margin-left: 0; }
  .checklist li { padding: 5px 0 5px 28px; position: relative; }
  .checklist li::before { content: "☐"; position: absolute; left: 0; color: ${accent}; font-size: 13pt; line-height: 1; }
  .step-list { counter-reset: steps; list-style: none; margin-left: 0; }
  .step-list li { counter-increment: steps; padding: 8px 0 8px 40px; position: relative; border-left: 2px solid #e5e7eb; margin-left: 16px; margin-bottom: 4px; }
  .step-list li::before { content: counter(steps); position: absolute; left: -16px; width: 28px; height: 28px; background: ${accent}; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10pt; font-weight: 700; top: 6px; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 10pt; }
  th { background: ${accent}; color: white; padding: 9px 12px; text-align: left; font-weight: 600; }
  td { padding: 8px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
  tr:nth-child(even) td { background: #f9fafb; }
  code { background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 3px; padding: 1px 5px; font-family: 'Courier New', monospace; font-size: 9.5pt; }
  pre  { background: #1e293b; color: #a5f3fc; padding: 14px; border-radius: 8px; font-size: 9.5pt; margin: 12px 0; overflow-x: auto; white-space: pre-wrap; }
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// MITARBEITER-HANDBUCH
// ─────────────────────────────────────────────────────────────────────────────
function buildMitarbeiterHTML() {
  const today = new Date().toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' });
  return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>PraxisZeit – Mitarbeiter-Handbuch</title>
<style>${baseCss('#2563EB')}</style></head><body>

<!-- COVER -->
<div class="cover page-break">
  <div class="cover-logo">PraxisZeit</div>
  <div class="cover-sub">Zeiterfassung & Dokumentation</div>
  <div class="cover-title">Mitarbeiter-Handbuch</div>
  <p style="color:#4b5563;font-size:13pt">Dein praktischer Begleiter für den Arbeitsalltag</p>
  <div class="cover-date">Stand: ${today} · Version 1.0</div>
</div>

<!-- WILLKOMMEN -->
<div class="section page-break">
  <h1>Willkommen bei PraxisZeit</h1>
  <p>PraxisZeit wurde entwickelt, um deinen Arbeitsalltag einfacher zu machen – nicht komplizierter.
  Die Anwendung übernimmt alle Berechnungen für dich: Überstunden, Urlaubstage, Soll-/Ist-Vergleiche.
  Du trägst deine Zeiten ein, PraxisZeit erledigt den Rest.</p>
  <p><strong>Was PraxisZeit für dich tut:</strong></p>
  <ul>
    <li>✅ Berechnet automatisch, ob du mehr oder weniger gearbeitet hast als geplant</li>
    <li>✅ Zeigt dir jederzeit deinen Resturlaub an</li>
    <li>✅ Erinnert dich an nächste geplante Abwesenheiten</li>
    <li>✅ Ermöglicht Korrekturen über Änderungsanträge – ohne Papierkram</li>
  </ul>
  <div class="tip"><strong>💡 Tipp:</strong> PraxisZeit funktioniert auch auf dem Smartphone – einfach die Adresse
  im Browser öffnen und als App speichern (PWA-Installation).</div>
  ${img('login', 'Anmelden – die erste Seite nach dem Aufruf von PraxisZeit')}
</div>

<!-- ANMELDEN -->
<div class="section page-break">
  <h2>1. Anmelden</h2>
  <p>Öffne PraxisZeit im Browser und melde dich mit deinem Benutzernamen und Passwort an.
  Deine Zugangsdaten erhältst du von der Praxisleitung.</p>
  <ol class="step-list">
    <li>Adresse im Browser aufrufen (z. B. <strong>http://praxiszeit.local</strong>)</li>
    <li>Benutzernamen eingeben (deine E-Mail-Adresse)</li>
    <li>Passwort eingeben</li>
    <li>Auf <strong>„Anmelden"</strong> klicken</li>
  </ol>
  <div class="warn"><strong>⚠️ Wichtig:</strong> Teile dein Passwort niemals mit Kollegen. Jeder hat ein eigenes Konto –
  so sind alle Einträge eindeutig dir zugeordnet. Bei Vergessen des Passworts wende dich an die Administration.</div>
</div>

<!-- DASHBOARD -->
<div class="section page-break">
  <h2>2. Das Dashboard – dein täglicher Überblick</h2>
  <p>Nach der Anmeldung siehst du sofort das Dashboard. Hier erkennst du auf einen Blick:</p>
  <ul>
    <li><strong>Stundensaldo</strong> – wie viele Stunden du diesen Monat mehr oder weniger gearbeitet hast</li>
    <li><strong>Resturlaub</strong> – verbleibende Urlaubstage in Stunden</li>
    <li><strong>Nächste Abwesenheit</strong> – dein nächster geplanter freier Tag</li>
    <li><strong>Stempeluhr</strong> – direktes Ein- und Ausstempeln per Klick</li>
  </ul>
  ${img('ma_dashboard', 'Das Dashboard – alle wichtigen Informationen auf einen Blick')}

  <h3>Die Stempeluhr</h3>
  <p>Die Stempeluhr oben auf dem Dashboard ermöglicht das schnelle Erfassen deiner Arbeitszeiten:</p>
  <ol class="step-list">
    <li>Klicke auf <strong>„Dienst beginnen"</strong> wenn du anfängst zu arbeiten</li>
    <li>PraxisZeit merkt sich die Uhrzeit automatisch</li>
    <li>Klicke am Ende auf <strong>„Dienst beenden"</strong> – die Arbeitszeit wird gespeichert</li>
  </ol>
  ${img('ma_stempeluhr', 'Stempeluhr – schnelles Ein- und Ausstempeln direkt vom Dashboard')}
  <div class="tip"><strong>💡 Tipp:</strong> Falls du die Stempeluhr vergessen hast, kannst du deinen Zeiteintrag
  jederzeit manuell in der Zeiterfassung nachtragen oder korrigieren.</div>
</div>

<!-- ZEITERFASSUNG -->
<div class="section page-break">
  <h2>3. Zeiterfassung</h2>
  <p>In der Zeiterfassung siehst du die Wochenansicht mit allen eingetragenen Arbeitszeiten.
  Hier kannst du neue Einträge erstellen, bestehende bearbeiten und Pausen erfassen.</p>
  ${img('ma_zeiterfassung', 'Zeiterfassung – Wochenübersicht aller Einträge')}

  <h3>Neuen Zeiteintrag erfassen</h3>
  <ol class="step-list">
    <li>Navigiere zur Seite <strong>„Zeiterfassung"</strong> im Menü</li>
    <li>Klicke auf den <strong>+ Button</strong> neben dem gewünschten Tag</li>
    <li>Trage <strong>Beginn</strong> und <strong>Ende</strong> ein (Format: HH:MM, z. B. 08:00 – 16:30)</li>
    <li>Trage <strong>Pause</strong> in Minuten ein (z. B. 30 für eine halbe Stunde)</li>
    <li>Optional: Notizen zum Tag hinzufügen</li>
    <li>Auf <strong>„Speichern"</strong> klicken</li>
  </ol>
  ${img('ma_zeiteintrag_form', 'Formular zum Erfassen eines neuen Zeiteintrags')}
  <div class="warn"><strong>⚠️ Daten speichern nicht vergessen!</strong> Einträge werden erst gespeichert,
  wenn du auf den „Speichern"-Button klickst. Schließen ohne Speichern verwirft alle Änderungen.</div>

  <h3>Zeiteintrag nachträglich korrigieren</h3>
  <p>Hast du dich vertippt oder vergessen, dich auszustempeln?</p>
  <ul>
    <li>Klicke auf den <strong>Bearbeiten-Button (Stift-Symbol)</strong> neben dem Eintrag</li>
    <li>Korrigiere die Werte und speichere</li>
    <li>Falls der Tag schon länger zurückliegt und du keine Berechtigung zur Bearbeitung hast,
    stelle einen <strong>Änderungsantrag</strong> (siehe Kapitel 6)</li>
  </ul>

  <h3>Mit der Stempeluhr erfasste Zeiten</h3>
  <p>Wenn du die Stempeluhr verwendet hast, erscheinen die Zeiten automatisch in der Wochenansicht.
  Du kannst sie wie jeden anderen Eintrag nachträglich bearbeiten, um z. B. die Pause zu ergänzen.</p>
</div>

<!-- ABWESENHEITEN -->
<div class="section page-break">
  <h2>4. Abwesenheiten eintragen</h2>
  <p>Unter <strong>„Abwesenheiten"</strong> kannst du Urlaub, Krankheitstage, Fortbildungen
  und sonstige Abwesenheiten eintragen und deinen Kalender einsehen.</p>
  ${img('ma_abwesenheiten', 'Abwesenheitskalender – Übersicht aller eigenen Abwesenheiten')}

  <h3>Einzelnen Tag eintragen</h3>
  <ol class="step-list">
    <li>Klicke auf den gewünschten Tag im Kalender</li>
    <li>Wähle den <strong>Typ</strong> (Urlaub, Krank, Fortbildung, Sonstiges)</li>
    <li>Trage die Stunden ein (wird automatisch aus deinen Sollstunden befüllt)</li>
    <li>Optional: Notiz hinzufügen</li>
    <li>Auf <strong>„Speichern"</strong> klicken</li>
  </ol>
  ${img('ma_abwesenheit_form', 'Formular für eine Abwesenheit an einem einzelnen Tag')}

  <h3>Mehrere Tage auf einmal (Zeitraum)</h3>
  <ol class="step-list">
    <li>Klicke auf den <strong>Starttag</strong> im Kalender</li>
    <li>Aktiviere die Checkbox <strong>„Zeitraum"</strong></li>
    <li>Wähle das <strong>Enddatum</strong></li>
    <li>PraxisZeit berechnet automatisch alle Werktage (Wochenenden und Feiertage werden übersprungen)</li>
    <li>Speichern</li>
  </ol>
  ${img('ma_abwesenheit_zeitraum', 'Zeitraum: mehrere Urlaubstage auf einmal eintragen')}
  <div class="tip"><strong>💡 Tipp:</strong> Wochenenden und gesetzliche Feiertage werden automatisch
  aus dem Zeitraum herausgerechnet. Du musst nur Start und Ende angeben.</div>
</div>

<!-- PROFIL -->
<div class="section page-break">
  <h2>5. Dein Profil</h2>
  <p>Unter <strong>„Profil"</strong> siehst du deine persönlichen Daten und kannst dein Passwort ändern.</p>
  ${img('ma_profil', 'Profilseite mit persönlichen Angaben')}

  <h3>Passwort ändern</h3>
  <ol class="step-list">
    <li>Navigiere zu <strong>„Profil"</strong></li>
    <li>Gib dein <strong>aktuelles Passwort</strong> ein</li>
    <li>Gib das <strong>neue Passwort</strong> zweimal ein</li>
    <li>Klicke auf <strong>„Passwort ändern"</strong></li>
  </ol>
  <div class="warn"><strong>⚠️ Sicheres Passwort wählen:</strong> Mindestens 8 Zeichen, Groß- und Kleinbuchstaben,
  eine Zahl und ein Sonderzeichen. Beispiel: <code>Sommer2026!</code></div>
</div>

<!-- ÄNDERUNGSANTRÄGE -->
<div class="section page-break">
  <h2>6. Änderungsanträge</h2>
  <p>Wenn du einen Fehler in deinen Zeiteinträgen feststellst, den du nicht mehr selbst korrigieren kannst
  (z. B. weil er zu weit zurückliegt oder gesperrt ist), kannst du einen <strong>Änderungsantrag</strong> stellen.</p>
  ${img('ma_aenderungsantraege', 'Änderungsanträge – Korrekturen transparent beantragen')}
  <ol class="step-list">
    <li>Gehe zu <strong>„Änderungsanträge"</strong> im Menü</li>
    <li>Klicke auf <strong>„Neuer Antrag"</strong></li>
    <li>Wähle den betroffenen <strong>Tag</strong> aus</li>
    <li>Trage die <strong>korrekten Zeiten</strong> ein</li>
    <li>Füge eine <strong>Begründung</strong> hinzu (z. B. „Habe vergessen, mich auszustempeln")</li>
    <li>Einreichen – die Administration prüft und genehmigt den Antrag</li>
  </ol>
  <div class="info"><strong>ℹ️ Transparenz:</strong> Alle Änderungsanträge werden protokolliert.
  Du siehst immer den Status deines Antrags (offen, genehmigt, abgelehnt).</div>
</div>

<!-- DATENSCHUTZ -->
<div class="section page-break">
  <h2>7. Datenschutz-Hinweise</h2>
  <div class="danger"><strong>🔒 Wichtig:</strong> PraxisZeit ist ein internes Arbeitszeiterfassungssystem.
  Es werden ausschließlich Arbeitszeitdaten gespeichert – keine Patienten- oder Klientendaten.</div>

  <h3>Was du beachten musst</h3>
  <ul>
    <li><strong>Kein freigegebener Browser:</strong> Melde dich immer ab, wenn du ein gemeinsam genutztes Gerät verwendest (Button „Abmelden" im Menü)</li>
    <li><strong>Kein Zugriff auf fremde Konten:</strong> Jeder Mitarbeiter hat sein eigenes Konto. Logge dich niemals in das Konto einer anderen Person ein</li>
    <li><strong>Passwort privat halten:</strong> Gib dein Passwort nie weiter – auch nicht an die Praxisleitung (Admins können Passwörter zurücksetzen, ohne sie zu kennen)</li>
    <li><strong>Notizen sachlich halten:</strong> Das Notizfeld in Zeiteinträgen ist für dienstliche Anmerkungen gedacht, keine persönlichen Informationen</li>
    <li><strong>Bei Verdacht auf Missbrauch:</strong> Informiere sofort die Administration, wenn du vermutest, dass jemand Zugriff auf dein Konto hatte</li>
  </ul>

  <h3>Deine gespeicherten Daten</h3>
  <p>PraxisZeit speichert folgende Daten von dir:</p>
  <table>
    <tr><th>Datenkategorie</th><th>Zweck</th></tr>
    <tr><td>Name, Benutzername</td><td>Identifikation im System</td></tr>
    <tr><td>Arbeitszeiten (Start, Ende, Pausen)</td><td>Zeiterfassung und Soll/Ist-Vergleich</td></tr>
    <tr><td>Abwesenheiten (Typ, Datum)</td><td>Urlaubs- und Fehlzeitenverwaltung</td></tr>
    <tr><td>Wochenstunden, Urlaubstage</td><td>Vertraglich vereinbarte Sollwerte</td></tr>
  </table>
  <p>Keine Standortdaten, keine biometrischen Daten, keine Aktivitätsprotokolle.</p>

  <h3>Recht auf Auskunft</h3>
  <p>Du kannst jederzeit alle über dich gespeicherten Daten einsehen – direkt in deinem Profil
  und in der Zeiterfassungsansicht. Bei weiteren Fragen wende dich an deine Praxisleitung.</p>
</div>

<!-- SCHNELLHILFE -->
<div class="section page-break">
  <h2>8. Schnellreferenz</h2>
  <table>
    <tr><th>Aufgabe</th><th>Wo?</th><th>Hinweis</th></tr>
    <tr><td>Anmelden</td><td>Login-Seite</td><td>Benutzername = E-Mail-Adresse</td></tr>
    <tr><td>Abmelden</td><td>Menü → unten → „Abmelden"</td><td>Immer abmelden auf fremden Geräten</td></tr>
    <tr><td>Einstempeln / Ausstempeln</td><td>Dashboard → Stempeluhr</td><td>Auch nachträgliche Korrektur möglich</td></tr>
    <tr><td>Zeiteintrag erstellen</td><td>Zeiterfassung → + Button</td><td>Start, Ende, Pause, Notiz</td></tr>
    <tr><td>Zeiteintrag korrigieren</td><td>Zeiterfassung → Stift-Symbol</td><td>Bei alten Einträgen: Änderungsantrag</td></tr>
    <tr><td>Urlaub eintragen</td><td>Abwesenheiten → Tag klicken</td><td>Typ „Urlaub" wählen</td></tr>
    <tr><td>Kranktag eintragen</td><td>Abwesenheiten → Tag klicken</td><td>Typ „Krank" wählen</td></tr>
    <tr><td>Mehrere Tage eintragen</td><td>Abwesenheiten → Tag klicken → Zeitraum</td><td>Wochenenden werden übersprungen</td></tr>
    <tr><td>Resturlaub prüfen</td><td>Dashboard</td><td>Wird automatisch berechnet</td></tr>
    <tr><td>Überstunden prüfen</td><td>Dashboard → Stundensaldo</td><td>Positiv = Überstunden, Negativ = Fehlstunden</td></tr>
    <tr><td>Passwort ändern</td><td>Profil → Passwort</td><td>Aktuelles Passwort erforderlich</td></tr>
    <tr><td>Fehler melden</td><td>Änderungsanträge → Neuer Antrag</td><td>Mit Begründung und korrekten Zeiten</td></tr>
  </table>

  <h3>Hilfe bei Problemen</h3>
  <div class="tip">
    <strong>1. Seite lädt nicht / Login schlägt fehl</strong><br>
    Prüfe deine Internetverbindung und versuche es erneut. Stelle sicher, dass du die richtige URL verwendest.
    Warte 30 Sekunden und lade die Seite neu.
  </div>
  <div class="tip">
    <strong>2. Daten wurden nicht gespeichert</strong><br>
    Achte darauf, immer auf den <strong>„Speichern"</strong>-Button zu klicken. Der Browser-Zurück-Button
    oder das Schließen des Tabs ohne Speichern verwirft alle Eingaben.
  </div>
  <div class="tip">
    <strong>3. Berechnungen erscheinen falsch</strong><br>
    Prüfe, ob Pausen korrekt eingetragen sind. Ein fehlendes Pauseneintrag kann die Berechnung verfälschen.
    Bei anhaltenden Unklarheiten wende dich an die Administration.
  </div>
</div>

</body></html>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// ADMIN-HANDBUCH
// ─────────────────────────────────────────────────────────────────────────────
function buildAdminHTML() {
  const today = new Date().toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' });
  return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>PraxisZeit – Admin-Handbuch</title>
<style>${baseCss('#1e40af')}</style></head><body>

<!-- COVER -->
<div class="cover page-break">
  <div class="cover-logo">PraxisZeit</div>
  <div class="cover-sub">Zeiterfassung & Dokumentation</div>
  <div class="cover-title">Administrator-Handbuch</div>
  <p style="color:#4b5563;font-size:13pt">System-Management · Konfiguration · Wartung</p>
  <div class="cover-date">Stand: ${today} · Version 1.0 · Vertraulich</div>
</div>

<!-- SETUP & DEPLOYMENT -->
<div class="section page-break">
  <h1>Setup &amp; Deployment</h1>
  <p>PraxisZeit läuft als Docker-Compose-Anwendung mit drei Services: PostgreSQL-Datenbank, FastAPI-Backend und React-Frontend (via Nginx). Die gesamte Infrastruktur ist im Repository versioniert.</p>

  <h2>1.1 Systemvoraussetzungen</h2>
  <table>
    <tr><th>Komponente</th><th>Mindestanforderung</th><th>Empfohlen</th></tr>
    <tr><td>Docker Engine</td><td>≥ 24.0</td><td>Aktuelle stabile Version</td></tr>
    <tr><td>Docker Compose</td><td>≥ 2.0 (Plugin)</td><td>Aktuelle stabile Version</td></tr>
    <tr><td>RAM</td><td>1 GB</td><td>2 GB</td></tr>
    <tr><td>Festplatte</td><td>5 GB</td><td>20 GB (für Wachstum)</td></tr>
    <tr><td>OS</td><td>Linux (Ubuntu 22.04+), Windows 10+ mit Docker Desktop, macOS 13+</td><td>Ubuntu 22.04 LTS</td></tr>
  </table>

  <h2>1.2 Erstinstallation</h2>
  <ol class="step-list">
    <li>Repository klonen: <code>git clone https://github.com/phash/praxiszeit</code></li>
    <li>Ins Verzeichnis wechseln: <code>cd praxiszeit</code></li>
    <li>Konfigurationsdatei anlegen: <code>cp .env.example .env</code></li>
    <li><code>.env</code> mit einem Texteditor öffnen und alle Werte konfigurieren (siehe 1.3)</li>
    <li>Container starten: <code>docker-compose up -d</code></li>
    <li>Logs prüfen: <code>docker-compose logs -f</code></li>
    <li>Health-Check: <code>curl http://localhost/api/health</code> → <code>{"status":"healthy","database":"connected"}</code></li>
  </ol>
  <div class="warn"><strong>⚠️ Kritisch:</strong> Die <code>.env</code>-Datei enthält alle Secrets (Datenbankpasswort, JWT-Secret, Admin-Passwort).
  Sie darf niemals in Git committet werden und ist in <code>.gitignore</code> ausgeschlossen. Sichere sie an einem separaten, gesicherten Ort.</div>

  <h2>1.3 Umgebungsvariablen</h2>
  <table>
    <tr><th>Variable</th><th>Beschreibung</th><th>Beispielwert</th></tr>
    <tr><td><code>SECRET_KEY</code></td><td>JWT-Signing-Secret (mindestens 32 Zeichen)</td><td><code>$(openssl rand -hex 32)</code></td></tr>
    <tr><td><code>POSTGRES_USER</code></td><td>Datenbankbenutzer</td><td><code>praxiszeit</code></td></tr>
    <tr><td><code>POSTGRES_PASSWORD</code></td><td>Datenbankpasswort (stark!)</td><td><code>sicheres_passwort_2026</code></td></tr>
    <tr><td><code>POSTGRES_DB</code></td><td>Datenbankname</td><td><code>praxiszeit</code></td></tr>
    <tr><td><code>DATABASE_URL</code></td><td>Vollständige DB-Verbindungszeichenfolge</td><td><code>postgresql://praxiszeit:pw@db/praxiszeit</code></td></tr>
    <tr><td><code>ADMIN_USERNAME</code></td><td>Benutzername des initialen Admins</td><td><code>admin</code></td></tr>
    <tr><td><code>ADMIN_EMAIL</code></td><td>E-Mail des initialen Admins</td><td><code>admin@praxis.de</code></td></tr>
    <tr><td><code>ADMIN_PASSWORD</code></td><td>Initiales Admin-Passwort</td><td><code>Admin2026!</code></td></tr>
    <tr><td><code>CORS_ORIGINS</code></td><td>Erlaubte Frontend-Origins (Komma-getrennt)</td><td><code>https://praxis.example.com</code></td></tr>
    <tr><td><code>ACCESS_TOKEN_EXPIRE_MINUTES</code></td><td>JWT-Token-Gültigkeit in Minuten</td><td><code>30</code></td></tr>
  </table>
  <div class="danger"><strong>🔐 Security:</strong> Generiere den <code>SECRET_KEY</code> zwingend mit <code>openssl rand -hex 32</code>.
  Setze <code>CORS_ORIGINS</code> in der Produktion auf die spezifische Domain (niemals <code>*</code> in Produktion).</div>

  <h2>1.4 Updates deployen</h2>
  <pre>git pull
docker-compose down
docker-compose up -d --build</pre>
  <div class="info"><strong>ℹ️ Hinweis:</strong> Datenbank-Migrationen werden beim Container-Start automatisch ausgeführt.
  Bestehende Daten bleiben erhalten (PostgreSQL-Volume wird nicht gelöscht).</div>

  <h2>1.5 Nginx Reverse Proxy (Produktion)</h2>
  <p>Für den Produktionseinsatz wird ein Reverse Proxy mit HTTPS empfohlen:</p>
  <pre>server {
    listen 443 ssl;
    server_name praxiszeit.praxis.de;

    ssl_certificate     /etc/ssl/certs/praxiszeit.crt;
    ssl_certificate_key /etc/ssl/private/praxiszeit.key;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}</pre>
</div>

<!-- BENUTZERVERWALTUNG -->
<div class="section page-break">
  <h1>Benutzerverwaltung</h1>
  ${img('admin_users', 'Übersicht aller Mitarbeiterkonten in der Benutzerverwaltung')}

  <h2>2.1 Neuen Mitarbeiter anlegen</h2>
  <ol class="step-list">
    <li>Admin-Dashboard aufrufen → <strong>„Benutzerverwaltung"</strong></li>
    <li>Klicke auf <strong>„Neuer Mitarbeiter"</strong></li>
    <li>Pflichtfelder ausfüllen: Vorname, Nachname, Benutzername</li>
    <li>Passwort direkt setzen (kein Temp-Passwort-Workflow)</li>
    <li>Wochenstunden und Urlaubstage eintragen</li>
    <li>Rolle wählen: <strong>Mitarbeiter</strong> oder <strong>Administrator</strong></li>
    <li>Optional: Kalenderfarbe für Abwesenheitskalender festlegen</li>
    <li>Speichern</li>
  </ol>
  ${img('admin_user_anlegen', 'Formular: Neuen Mitarbeiter anlegen')}
  <div class="info"><strong>ℹ️ Benutzername:</strong> Der Benutzername ist eindeutig im System. Empfehlung:
  E-Mail-Adresse verwenden (z. B. <code>max.mustermann@praxis.de</code>). Kann nachträglich nicht geändert werden.</div>

  <h2>2.2 Mitarbeiter-Daten bearbeiten</h2>
  <p>Klicke auf das Stift-Symbol in der Benutzerliste. Folgende Felder können geändert werden:</p>
  <table>
    <tr><th>Feld</th><th>Beschreibung</th><th>Auswirkung</th></tr>
    <tr><td>Vorname / Nachname</td><td>Anzeigename</td><td>Sofort in allen Ansichten</td></tr>
    <tr><td>E-Mail</td><td>Optional, für Benachrichtigungen</td><td>Keine direkten Systemauswirkungen</td></tr>
    <tr><td>Wochenstunden</td><td>Vertraglich vereinbarte Stunden</td><td>Beeinflusst Soll-Berechnung rückwirkend</td></tr>
    <tr><td>Urlaubstage</td><td>Jährliches Kontingent</td><td>Beeinflusst Resturlaub-Anzeige</td></tr>
    <tr><td>Stunden erfassen</td><td>Deaktiviert Arbeitszeiterfassung</td><td>Soll-Stunden werden 0</td></tr>
    <tr><td>Kalenderfarbe</td><td>Farbe im Teamkalender</td><td>Nur visuell</td></tr>
    <tr><td>Rolle</td><td>Admin oder Mitarbeiter</td><td>Zugriff auf Admin-Bereich</td></tr>
    <tr><td>Aktiv</td><td>Konto aktiv/deaktiviert</td><td>Deaktivierte Konten können sich nicht anmelden</td></tr>
  </table>
  ${img('admin_user_bearbeiten', 'Formular: Mitarbeiter-Daten bearbeiten')}

  <h2>2.3 Individuelle Tagesplanung</h2>
  <p>Bei Mitarbeitern mit ungleichmäßigen Arbeitszeiten (z. B. Mo/Di 8h, Mi 4h, Do/Fr 6h)
  kann die individuelle Tagesplanung aktiviert werden:</p>
  <ol class="step-list">
    <li>Mitarbeiter bearbeiten → Checkbox <strong>„Individuelle Tagesplanung aktivieren"</strong> anklicken</li>
    <li>Stunden pro Wochentag (Mo–Fr) einzeln eintragen</li>
    <li>Die Summe muss den Wochenstunden entsprechen</li>
    <li>Speichern</li>
  </ol>
  ${img('admin_tagesplanung', 'Individuelle Tagesplanung: Stunden je Wochentag konfigurieren')}
  <div class="info"><strong>ℹ️ Auswirkungen:</strong> Bei aktivierter Tagesplanung werden Abwesenheitsstunden
  automatisch tagespräzise berechnet. Ein Urlaubstag am Montag mit 8h-Soll zählt 8h, ein Mittwoch mit 4h-Soll zählt 4h.</div>

  <h2>2.4 Wochenstunden-Historie</h2>
  <p>Ändert sich das Arbeitspensum eines Mitarbeiters (z. B. Wechsel auf Teilzeit), muss die Änderung
  über die <strong>Stundenhistorie</strong> eingetragen werden – nicht direkt im Profil:</p>
  <ol class="step-list">
    <li>In der Benutzerliste auf <strong>„Std"-Button</strong> klicken</li>
    <li>Klicke <strong>„Neue Änderung"</strong></li>
    <li>Neue Wochenstunden und das <strong>Gültigkeitsdatum</strong> eintragen</li>
    <li>Optional: Notiz zur Änderung (z. B. „Teilzeit ab 01.03.2026 per Vereinbarung")</li>
    <li>Speichern</li>
  </ol>
  ${img('admin_stunden_historie', 'Stundenhistorie: Arbeitszeitenänderungen nachverfolgen')}
  <div class="warn"><strong>⚠️ Wichtig:</strong> Das Gültigkeitsdatum bestimmt, ab wann die neuen Stunden für
  Berechnungen gelten. Alle historischen Berechnungen bleiben mit den damaligen Stunden korrekt.</div>

  <h2>2.5 Passwort-Reset</h2>
  <p>Admins können das Passwort eines Mitarbeiters direkt setzen (kein E-Mail-Workflow):</p>
  <ol class="step-list">
    <li>Mitarbeiter in der Benutzerliste öffnen → Bearbeiten</li>
    <li>Neues Passwort eingeben</li>
    <li>Speichern</li>
    <li>Mitarbeiter informieren und auffordern, das Passwort beim nächsten Login zu ändern</li>
  </ol>
  <div class="danger"><strong>🔐 Sicherheitshinweis:</strong> Teile das gesetzte Passwort nur auf sicherem Weg mit
  dem Mitarbeiter (persönlich oder per verschlüsselter Nachricht). Verwende nie E-Mail ohne Verschlüsselung für Passwörter.</div>
</div>

<!-- KONFIGURATION -->
<div class="section page-break">
  <h1>Konfiguration</h1>

  <h2>3.1 Abwesenheitsübersicht &amp; Admin-Dashboard</h2>
  ${img('admin_dashboard', 'Admin-Dashboard: Teamübersicht mit Stundensalden aller Mitarbeiter')}
  <p>Das Admin-Dashboard zeigt eine Echtzeit-Übersicht aller Mitarbeiter mit:</p>
  <ul>
    <li>Stundensaldo des aktuellen Monats (grün = positiv, rot = negativ)</li>
    <li>Resturlaub mit Ampel-System (grün/gelb/rot)</li>
    <li>Aktueller Monat und Navigation zu Vormonaten</li>
  </ul>

  <h2>3.2 Abwesenheitsverwaltung</h2>
  ${img('admin_abwesenheiten', 'Admin: Urlaubsübersicht mit Ampel-System für alle Mitarbeiter')}
  <p>Die Abwesenheitsverwaltung bietet zwei Tabs:</p>
  <ul>
    <li><strong>Urlaubsübersicht:</strong> Jährliches Budget, verbrauchte Tage, Resturlaub pro Mitarbeiter</li>
    <li><strong>Teamkalender:</strong> Alle Abwesenheiten im Monatskalender mit Farbcodierung nach Mitarbeiter</li>
  </ul>
  ${img('admin_abwesenheiten_kalender', 'Teamkalender: Alle Abwesenheiten im Überblick')}

  <h2>3.3 Änderungsanträge bearbeiten</h2>
  ${img('admin_aenderungen', 'Änderungsanträge: Korrekturen von Mitarbeitern prüfen')}
  <p>Mitarbeiter können Korrekturen ihrer Zeiteinträge beantragen. Als Admin:</p>
  <ul>
    <li><strong>Genehmigen:</strong> Der Eintrag wird automatisch mit den beantragten Werten aktualisiert</li>
    <li><strong>Ablehnen:</strong> Der Antrag wird abgelehnt, der ursprüngliche Eintrag bleibt</li>
    <li>Alle Entscheidungen werden im Audit-Log protokolliert</li>
  </ul>

  <h2>3.4 Berichte &amp; Excel-Exports</h2>
  ${img('admin_berichte', 'Berichte: Export-Optionen für Monats- und Jahresreports')}
  <p>Drei Export-Typen stehen zur Verfügung:</p>
  <table>
    <tr><th>Report-Typ</th><th>Inhalt</th><th>Dateigröße</th><th>Ladezeit</th></tr>
    <tr><td>Monatsreport</td><td>Tägliche Einträge je Mitarbeiter (1 Tab pro MA)</td><td>~20 KB</td><td>&lt; 1s</td></tr>
    <tr><td>Jahresreport Classic</td><td>12 Monate kompakt je MA</td><td>~17 KB</td><td>~2s</td></tr>
    <tr><td>Jahresreport Detailliert</td><td>365 Tage je MA mit allen Details</td><td>~108 KB</td><td>~5s</td></tr>
  </table>
  <div class="info"><strong>ℹ️ Ruhezeitprüfung:</strong> Der Monatsreport prüft optional Mindestruhezeiten zwischen
  Einträgen (11h gemäß ArbZG). Verstöße werden farblich markiert.</div>
</div>

<!-- WARTUNG -->
<div class="section page-break">
  <h1>Wartung</h1>

  <h2>4.1 Backup-Strategie</h2>
  <div class="danger"><strong>🔐 Pflicht:</strong> Datenbankbackups sind zwingend erforderlich. Ohne Backup besteht
  Datenverlustrisiko bei Hardware-Ausfall oder fehlerhafter Migration.</div>

  <h3>Manuelles Backup</h3>
  <pre>docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup_$(date +%Y%m%d_%H%M).sql</pre>

  <h3>Automatisches Backup (Cron)</h3>
  <pre># Täglich um 02:00 Uhr – in /etc/cron.d/praxiszeit-backup
0 2 * * * root cd /opt/praxiszeit && \
  docker-compose exec -T db pg_dump -U praxiszeit praxiszeit | \
  gzip > /backups/praxiszeit_$(date +\%Y\%m\%d).sql.gz && \
  find /backups -name "praxiszeit_*.sql.gz" -mtime +30 -delete</pre>
  <div class="tip"><strong>💡 Empfehlung:</strong> Backups täglich, Aufbewahrung 30 Tage, monatliche Jahresbackups
  dauerhaft aufbewahren. Backups auf separatem Speicher (NAS, Cloud) lagern.</div>

  <h3>Backup-Wiederherstellung</h3>
  <pre>docker-compose exec -T db psql -U praxiszeit praxiszeit < backup_20260217.sql</pre>

  <h2>4.2 Updates</h2>
  <ol class="step-list">
    <li>Backup erstellen (vor jedem Update!)</li>
    <li><code>git pull</code> – aktuellen Stand herunterladen</li>
    <li><code>docker-compose down</code> – Container stoppen</li>
    <li><code>docker-compose up -d --build</code> – neu bauen und starten</li>
    <li><code>docker-compose logs -f</code> – Logs prüfen (Migrationen werden automatisch ausgeführt)</li>
    <li><code>curl http://localhost/api/health</code> – Health-Check</li>
  </ol>
  <div class="warn"><strong>⚠️ Hinweis zu Migrationen:</strong> Neue Datenbankmigrationen werden automatisch beim
  Start ausgeführt. Falls eine Migration fehlschlägt, stoppt der Backend-Container. Logs prüfen und bei Bedarf Support kontaktieren.</div>

  <h2>4.3 Fehler-Monitoring</h2>
  ${img('admin_fehler', 'Fehler-Monitoring: Systemfehler in der Admin-Oberfläche verwalten')}
  <p>PraxisZeit erfasst Backend-Fehler automatisch in der Datenbank. Im Admin-Bereich unter
  <strong>„Fehler-Monitoring"</strong> können diese eingesehen und verwaltet werden:</p>
  <ul>
    <li><strong>Offen:</strong> Neue, noch nicht bearbeitete Fehler (rot markiert)</li>
    <li><strong>Ignoriert:</strong> Bekannte, unkritische Fehler</li>
    <li><strong>Behoben:</strong> Fehler nach Lösung des Problems</li>
  </ul>
  <p>Für jeden Fehler kann ein GitHub-Issue verknüpft werden. Bei kritischen Fehlern
  (Level: critical/error) sollte umgehend reagiert werden.</p>

  <h2>4.4 Audit-Log</h2>
  ${img('admin_auditlog', 'Audit-Log: Lückenlose Protokollierung aller Systemaktionen')}
  <p>Alle relevanten Aktionen im System werden protokolliert:</p>
  <ul>
    <li>Zeiteinträge erstellen, bearbeiten, löschen</li>
    <li>Abwesenheiten erfassen und stornieren</li>
    <li>Änderungsanträge genehmigen/ablehnen</li>
    <li>Benutzerdaten ändern</li>
    <li>Admin-Aktionen</li>
  </ul>
  <div class="info"><strong>ℹ️ Compliance:</strong> Das Audit-Log ist unveränderlich und dient der Nachvollziehbarkeit
  von Arbeitszeit-Korrekturen. Bei arbeitsrechtlichen Fragen können Einträge als Nachweis dienen.</div>

  <h2>4.5 Container-Status und Logs</h2>
  <pre># Status aller Container
docker-compose ps

# Live-Logs aller Services
docker-compose logs -f

# Nur Backend-Logs
docker-compose logs -f backend

# Datenbankzugriff
docker-compose exec db psql -U praxiszeit praxiszeit

# Backend-Shell
docker-compose exec backend bash</pre>

  <h2>4.6 Notfall-Resetverfahren</h2>
  <div class="danger"><strong>⚠️ Letzter Ausweg:</strong> Folgendes löscht ALLE Daten unwiederbringlich!</div>
  <pre># Alle Container und Volumes löschen (DATENVERLUST!)
docker-compose down -v

# Neu starten mit leerer Datenbank
docker-compose up -d</pre>
  <p>Nur verwenden, wenn alle anderen Optionen ausgeschöpft sind und ein vollständiges Backup vorliegt.</p>
</div>

</body></html>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// CHEAT-SHEET
// ─────────────────────────────────────────────────────────────────────────────
function buildCheatSheetHTML() {
  const today = new Date().toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' });
  return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>PraxisZeit – Cheat-Sheet</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 9.5pt; color: #1a1a2e; background: #fff; line-height: 1.5; }
.page { max-width: 780px; margin: 0 auto; padding: 20px 28px; }
.header { background: linear-gradient(135deg, #1e3a8a, #2563EB); color: white; border-radius: 8px; padding: 14px 20px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 20pt; font-weight: 900; letter-spacing: -1px; }
.header .sub { font-size: 10pt; opacity: 0.85; }
.header .date { font-size: 8pt; opacity: 0.7; text-align: right; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.box { border: 1.5px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.box-head { background: #1e40af; color: white; font-weight: 700; font-size: 9pt; padding: 7px 12px; letter-spacing: 0.5px; text-transform: uppercase; }
.box-head.green  { background: #059669; }
.box-head.orange { background: #d97706; }
.box-head.red    { background: #dc2626; }
.box-head.purple { background: #7c3aed; }
table { width: 100%; border-collapse: collapse; }
th { background: #f1f5f9; font-size: 8pt; color: #475569; padding: 5px 10px; text-align: left; font-weight: 600; border-bottom: 1px solid #e2e8f0; }
td { padding: 5px 10px; border-bottom: 1px solid #f1f5f9; font-size: 9pt; vertical-align: top; }
td:first-child { font-weight: 600; white-space: nowrap; }
td code { background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 3px; padding: 1px 4px; font-size: 8pt; font-family: monospace; }
.warn-box { background: #fef3cd; border: 1.5px solid #f59e0b; border-radius: 8px; padding: 10px 14px; margin-top: 12px; }
.warn-box .title { font-weight: 700; color: #92400e; font-size: 9.5pt; margin-bottom: 6px; }
.warn-box ol { margin: 0 0 0 16px; }
.warn-box li { font-size: 9pt; margin-bottom: 4px; }
.tip-box { background: #d1fae5; border: 1.5px solid #10b981; border-radius: 8px; padding: 10px 14px; margin-top: 12px; }
.tip-box .title { font-weight: 700; color: #065f46; font-size: 9.5pt; margin-bottom: 6px; }
.tip-box li { font-size: 9pt; margin-bottom: 3px; list-style: none; padding-left: 0; }
.footer { text-align: center; margin-top: 14px; font-size: 8pt; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 10px; }
.full-width { grid-column: 1 / -1; }
</style></head><body>
<div class="page">

  <div class="header">
    <div>
      <h1>PraxisZeit</h1>
      <div class="sub">Cheat-Sheet – Schnellreferenz für Mitarbeiter</div>
    </div>
    <div class="date">Stand: ${today}</div>
  </div>

  <div class="cols">

    <!-- TÄGLICHER WORKFLOW -->
    <div class="box">
      <div class="box-head">📅 Täglicher Workflow</div>
      <table>
        <tr><th>Schritt</th><th>Aktion</th></tr>
        <tr><td>1. Anmelden</td><td>Browser → PraxisZeit → Benutzername + Passwort → Anmelden</td></tr>
        <tr><td>2. Einstempeln</td><td>Dashboard → <strong>„Dienst beginnen"</strong> klicken</td></tr>
        <tr><td>3. Pausenende</td><td>Automatisch – Pausen im Zeiteintrag nachtragen</td></tr>
        <tr><td>4. Ausstempeln</td><td>Dashboard → <strong>„Dienst beenden"</strong> klicken</td></tr>
        <tr><td>5. Abmelden</td><td>Menü (unten) → <strong>„Abmelden"</strong></td></tr>
      </table>
    </div>

    <!-- ZEITERFASSUNG -->
    <div class="box">
      <div class="box-head green">⏱ Zeiterfassung</div>
      <table>
        <tr><th>Aktion</th><th>Wo klicken?</th></tr>
        <tr><td>Neuer Eintrag</td><td>Zeiterfassung → <code>+ Eintrag</code> beim Tag</td></tr>
        <tr><td>Eintrag bearbeiten</td><td>Zeiterfassung → Stift-Symbol beim Eintrag</td></tr>
        <tr><td>Eintrag löschen</td><td>Zeiterfassung → Papierkorb-Symbol</td></tr>
        <tr><td>Vorwoche</td><td>Zeiterfassung → Pfeil ←</td></tr>
        <tr><td>Nachträgliche Korrektur</td><td>Änderungsanträge → <code>Neuer Antrag</code></td></tr>
      </table>
    </div>

    <!-- ABWESENHEITEN -->
    <div class="box">
      <div class="box-head orange">📆 Abwesenheiten</div>
      <table>
        <tr><th>Typ</th><th>Vorgehen</th></tr>
        <tr><td>Urlaub (1 Tag)</td><td>Abwesenheiten → Tag klicken → Typ „Urlaub" → Speichern</td></tr>
        <tr><td>Urlaub (mehrere Tage)</td><td>Tag klicken → ☑ Zeitraum → Enddatum → Speichern</td></tr>
        <tr><td>Kranktag</td><td>Abwesenheiten → Tag klicken → Typ „Krank" → Speichern</td></tr>
        <tr><td>Fortbildung</td><td>Abwesenheiten → Tag klicken → Typ „Fortbildung"</td></tr>
        <tr><td>Abwesenheit löschen</td><td>Kalender → Eintrag anklicken → Löschen</td></tr>
      </table>
    </div>

    <!-- KONTO-ÜBERSICHT -->
    <div class="box">
      <div class="box-head purple">📊 Konto &amp; Überstunden</div>
      <table>
        <tr><th>Information</th><th>Wo?</th></tr>
        <tr><td>Stundensaldo</td><td>Dashboard → Karte „Überstunden"</td></tr>
        <tr><td>Resturlaub</td><td>Dashboard → Karte „Urlaubskonto"</td></tr>
        <tr><td>Nächster Urlaub</td><td>Dashboard → Karte „Nächste Abwesenheit"</td></tr>
        <tr><td>Persönl. Daten</td><td>Menü → Profil</td></tr>
        <tr><td>Passwort ändern</td><td>Profil → Passwort-Abschnitt</td></tr>
      </table>
    </div>

    <!-- SYMBOLE -->
    <div class="box">
      <div class="box-head" style="background:#0891b2">🔣 Symbole &amp; Farben</div>
      <table>
        <tr><th>Symbol/Farbe</th><th>Bedeutung</th></tr>
        <tr><td>🟢 Grün (Saldo)</td><td>Überstunden – du hast mehr gearbeitet als geplant</td></tr>
        <tr><td>🔴 Rot (Saldo)</td><td>Fehlstunden – du hast weniger gearbeitet als geplant</td></tr>
        <tr><td>🟢 Grün (Urlaub)</td><td>Mehr als 50 % Resturlaub vorhanden</td></tr>
        <tr><td>🟡 Gelb (Urlaub)</td><td>25–50 % Resturlaub vorhanden</td></tr>
        <tr><td>🔴 Rot (Urlaub)</td><td>Weniger als 25 % Resturlaub</td></tr>
        <tr><td>✏️ Stift</td><td>Bearbeiten</td></tr>
        <tr><td>🗑️ Papierkorb</td><td>Löschen (mit Bestätigung)</td></tr>
      </table>
    </div>

    <!-- ÄNDERUNGSANTRÄGE -->
    <div class="box">
      <div class="box-head red">📝 Fehler korrigieren</div>
      <table>
        <tr><th>Problem</th><th>Lösung</th></tr>
        <tr><td>Falsche Zeit (heute)</td><td>Zeiterfassung → Stift → korrigieren → Speichern</td></tr>
        <tr><td>Falsche Zeit (alt)</td><td>Änderungsanträge → Neuer Antrag → mit Begründung</td></tr>
        <tr><td>Vergessen auszustempeln</td><td>Dashboard → Stempeluhr → Zeit nachtragen</td></tr>
        <tr><td>Falsche Abwesenheit</td><td>Abwesenheiten → Eintrag löschen → neu anlegen</td></tr>
        <tr><td>Antrag-Status prüfen</td><td>Änderungsanträge → Liste → Status-Spalte</td></tr>
      </table>
    </div>

    <!-- SOFORT-HILFE (volle Breite) -->
    <div class="full-width">
      <div class="warn-box">
        <div class="title">⚠️ Hilfe bei Problemen – 3 Sofort-Maßnahmen</div>
        <ol>
          <li><strong>Seite reagiert nicht / Fehler-Meldung:</strong> Browser neu laden (F5) · Cache leeren (Strg+Shift+R) · Browser wechseln (Chrome/Firefox) · 5 Minuten warten und erneut versuchen</li>
          <li><strong>Anmeldung schlägt fehl:</strong> Benutzernamen prüfen (E-Mail-Adresse) · Feststelltaste aus · Passwort bei Admin zurücksetzen lassen (Büro/Telefon)</li>
          <li><strong>Daten fehlen oder erscheinen falsch:</strong> Seite neu laden · Prüfen ob gespeichert wurde · Screenshot machen und an Administration schicken</li>
        </ol>
      </div>
      <div class="tip-box">
        <div class="title">💡 Wichtige Hinweise</div>
        <ul>
          <li>✅ <strong>Immer speichern!</strong> – Kein automatisches Speichern, Tabs nicht schließen ohne zu speichern</li>
          <li>✅ <strong>Auf fremden Geräten immer abmelden</strong> – Sicherheits- und Datenschutzpflicht</li>
          <li>✅ <strong>Zeitraum nutzen</strong> – Mehrere Urlaubstage auf einmal eintragen, Wochenenden werden automatisch übersprungen</li>
          <li>✅ <strong>Stempeluhr vergessen?</strong> – Manueller Eintrag in Zeiterfassung ist jederzeit möglich</li>
        </ul>
      </div>
    </div>

  </div><!-- /cols -->

  <div class="footer">PraxisZeit · ${today} · Bei Fragen: Administration</div>
</div>
</body></html>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// GENERATE PDFs
// ─────────────────────────────────────────────────────────────────────────────
async function generatePDF(browser, htmlContent, outputPath, format = 'A4') {
  const page = await browser.newPage();
  await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
  await page.pdf({
    path: outputPath,
    format,
    printBackground: true,
    margin: { top: '15mm', bottom: '15mm', left: '15mm', right: '15mm' }
  });
  await page.close();
  const size = (fs.statSync(outputPath).size / 1024 / 1024).toFixed(1);
  console.log(`✅ ${path.basename(outputPath)} (${size} MB)`);
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────────────────────
async function main() {
  console.log('PraxisZeit Handbuch-Generator');
  console.log('='.repeat(40));

  // 1. Browser starten & Screenshots aufnehmen
  console.log('\n📸 Screenshots werden aufgenommen...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=de-DE'],
    defaultViewport: { width: 1280, height: 860 }
  });

  try {
    await captureAll(browser);
  } catch (e) {
    console.error('Screenshot-Fehler:', e.message);
  }

  // 2. PDFs generieren
  console.log('\n📄 PDFs werden generiert...\n');

  const browser2 = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1280, height: 860 }
  });

  try {
    // Mitarbeiter-Handbuch
    const maHtml = buildMitarbeiterHTML();
    const maHtmlPath = path.join(__dirname, 'PraxisZeit-Mitarbeiter-Handbuch.html');
    fs.writeFileSync(maHtmlPath, maHtml, 'utf8');
    await generatePDF(browser2, maHtml, path.join(__dirname, 'PraxisZeit-Mitarbeiter-Handbuch.pdf'));

    // Admin-Handbuch
    const adminHtml = buildAdminHTML();
    const adminHtmlPath = path.join(__dirname, 'PraxisZeit-Admin-Handbuch.html');
    fs.writeFileSync(adminHtmlPath, adminHtml, 'utf8');
    await generatePDF(browser2, adminHtml, path.join(__dirname, 'PraxisZeit-Admin-Handbuch.pdf'));

    // Cheat-Sheet
    const csHtml = buildCheatSheetHTML();
    const csHtmlPath = path.join(__dirname, 'PraxisZeit-Cheat-Sheet.html');
    fs.writeFileSync(csHtmlPath, csHtml, 'utf8');
    await generatePDF(browser2, csHtml, path.join(__dirname, 'PraxisZeit-Cheat-Sheet.pdf'), 'A4');

  } finally {
    await browser2.close();
  }

  console.log('\n🎉 Fertig! Drei Dokumente wurden erstellt:');
  console.log('   📘 PraxisZeit-Mitarbeiter-Handbuch.pdf');
  console.log('   📗 PraxisZeit-Admin-Handbuch.pdf');
  console.log('   📋 PraxisZeit-Cheat-Sheet.pdf');
}

main().catch(err => { console.error('Fehler:', err); process.exit(1); });
