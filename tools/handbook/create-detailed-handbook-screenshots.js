const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost';
const SCREENSHOTS_DIR = path.join(__dirname, 'handbuch-screenshots-v2');

// Credentials
const EMPLOYEE = {
  email: 'anna.mueller@praxis.de',
  password: 'test123'  // Assuming standard test password
};

const ADMIN = {
  email: 'admin@praxis.de',
  password: 'test123'
};

// Ensure screenshots directory exists
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function takeScreenshot(page, name, options = {}) {
  const filename = path.join(SCREENSHOTS_DIR, `${name}.png`);
  await page.screenshot({
    path: filename,
    fullPage: options.fullPage || false,
    clip: options.clip
  });
  console.log(`✅ Screenshot: ${name}`);
  return filename;
}

async function login(page, credentials) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Clear fields first
  await page.click('input[type="email"]', { clickCount: 3 });
  await page.keyboard.press('Backspace');
  await page.click('input[type="password"]', { clickCount: 3 });
  await page.keyboard.press('Backspace');

  await page.type('input[type="email"]', credentials.email);
  await page.type('input[type="password"]', credentials.password);
  await page.click('button[type="submit"]');

  try {
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 5000 });
    await sleep(1500);
    return true;
  } catch (e) {
    console.log('⚠️ Login might have failed or already logged in');
    return false;
  }
}

async function logout(page) {
  // Try to find and click logout button
  try {
    const logoutButton = await page.$('button:has-text("Abmelden")');
    if (logoutButton) {
      await logoutButton.click();
      await sleep(1000);
    }
  } catch (e) {
    // Logout button might not exist, navigate to login directly
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  }
}

async function createDetailedHandbookScreenshots() {
  console.log('📸 Erstelle detaillierte Handbuch-Screenshots...\n');

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: { width: 1920, height: 1080 },
    args: ['--start-maximized']
  });

  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(30000);

    // ========================================
    // TEIL 1: LOGIN & AUTHENTIFIZIERUNG
    // ========================================
    console.log('\n🔐 TEIL 1: LOGIN & AUTHENTIFIZIERUNG');
    console.log('=====================================\n');

    // 01: Login-Seite (leer)
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
    await sleep(1500);
    await takeScreenshot(page, '01-login-leer');

    // 02: Login-Seite (ausgefüllt)
    await page.type('input[type="email"]', EMPLOYEE.email);
    await page.type('input[type="password"]', EMPLOYEE.password);
    await sleep(500);
    await takeScreenshot(page, '02-login-ausgefuellt');

    // Login durchführen
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'networkidle2' });
    await sleep(2000);

    // ========================================
    // TEIL 2: DASHBOARD (MITARBEITER)
    // ========================================
    console.log('\n📊 TEIL 2: DASHBOARD (MITARBEITER)');
    console.log('===================================\n');

    // 03: Dashboard Vollansicht
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '03-dashboard-vollansicht', { fullPage: true });

    // 04: Dashboard Stat-Cards (Close-up)
    const statCards = await page.$('.grid.grid-cols-1.md\\:grid-cols-3.gap-6');
    if (statCards) {
      const box = await statCards.boundingBox();
      await takeScreenshot(page, '04-dashboard-stat-cards', {
        clip: {
          x: Math.max(0, box.x - 10),
          y: Math.max(0, box.y - 10),
          width: Math.min(box.width + 20, 1900),
          height: Math.min(box.height + 20, 1060)
        }
      });
    }

    // 05: Team-Kalender
    await page.evaluate(() => window.scrollTo(0, 400));
    await sleep(1000);
    await takeScreenshot(page, '05-dashboard-team-kalender');

    // ========================================
    // TEIL 3: ZEITERFASSUNG
    // ========================================
    console.log('\n⏱️ TEIL 3: ZEITERFASSUNG');
    console.log('=========================\n');

    // 06: Zeiterfassung Übersicht
    await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '06-zeiterfassung-uebersicht', { fullPage: true });

    // 07: MonthSelector Close-up
    const monthSelector = await page.$('.flex.items-center.justify-between.mb-6');
    if (monthSelector) {
      const box = await monthSelector.boundingBox();
      await takeScreenshot(page, '07-month-selector', {
        clip: {
          x: Math.max(0, box.x - 20),
          y: Math.max(0, box.y - 20),
          width: Math.min(box.width + 40, 1900),
          height: Math.min(box.height + 40, 1060)
        }
      });
    }

    // 08: Zeiteinträge Tabelle Close-up
    const timeTable = await page.$('table');
    if (timeTable) {
      const box = await timeTable.boundingBox();
      await takeScreenshot(page, '08-zeiteintraege-tabelle', {
        clip: {
          x: Math.max(0, box.x - 10),
          y: Math.max(0, box.y - 10),
          width: Math.min(box.width + 20, 1900),
          height: Math.min(box.height + 20, 1060)
        }
      });
    }

    // ========================================
    // TEIL 4: ABWESENHEITEN
    // ========================================
    console.log('\n🏖️ TEIL 4: ABWESENHEITEN');
    console.log('=========================\n');

    // 09: Abwesenheiten Vollansicht
    await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '09-abwesenheiten-vollansicht', { fullPage: true });

    // 10: Abwesenheitskalender Close-up
    const calendar = await page.$('.grid.grid-cols-7.gap-1');
    if (calendar) {
      const parentBox = await (await calendar.evaluateHandle(el => el.parentElement.parentElement)).boundingBox();
      await takeScreenshot(page, '10-abwesenheitskalender', {
        clip: {
          x: Math.max(0, parentBox.x - 10),
          y: Math.max(0, parentBox.y - 10),
          width: Math.min(parentBox.width + 20, 1900),
          height: Math.min(parentBox.height + 20, 1060)
        }
      });
    }

    // 11: Abwesenheiten Tabelle
    await page.evaluate(() => window.scrollTo(0, 800));
    await sleep(1000);
    await takeScreenshot(page, '11-abwesenheiten-tabelle');

    // ========================================
    // TEIL 5: PROFIL
    // ========================================
    console.log('\n👤 TEIL 5: PROFIL');
    console.log('==================\n');

    // 12: Profil Vollansicht
    await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, '12-profil-vollansicht', { fullPage: true });

    // ========================================
    // TEIL 6: ADMIN-BEREICH (Logout + Admin-Login)
    // ========================================
    console.log('\n👔 TEIL 6: ADMIN-BEREICH');
    console.log('========================\n');

    // Logout und Admin-Login
    await logout(page);
    await sleep(1000);
    await login(page, ADMIN);

    // 13: Admin-Dashboard Vollansicht
    await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(3000);
    await takeScreenshot(page, '13-admin-dashboard-vollansicht', { fullPage: true });

    // 14: Monatsübersicht Tabelle
    const monthTable = await page.$('table');
    if (monthTable) {
      const box = await monthTable.boundingBox();
      await takeScreenshot(page, '14-admin-monatsuebersicht-tabelle', {
        clip: {
          x: Math.max(0, box.x - 10),
          y: Math.max(0, box.y - 60),
          width: Math.min(box.width + 20, 1900),
          height: Math.min(500, 1060)
        }
      });
    }

    // 15: Filter und Sortierung
    const filterInput = await page.$('input[placeholder*="Suche"]');
    if (filterInput) {
      await filterInput.type('Müller');
      await sleep(1500);
      await takeScreenshot(page, '15-admin-filter-aktiv');

      // Clear
      await filterInput.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // 16: Sortierung aktiv
    const sortableHeader = await page.$('th.cursor-pointer');
    if (sortableHeader) {
      await sortableHeader.click();
      await sleep(1000);
      await takeScreenshot(page, '16-admin-sortierung-aktiv');
    }

    // 17: Mitarbeiter-Detail Modal
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(500);
    const firstRow = await page.$('tbody tr.cursor-pointer');
    if (firstRow) {
      await firstRow.click();
      await sleep(2000);
      await takeScreenshot(page, '17-admin-mitarbeiter-detail-modal');

      // Close
      await page.keyboard.press('Escape');
      await sleep(500);
    }

    // 18: Jahresübersicht
    await page.evaluate(() => window.scrollTo(0, 2000));
    await sleep(2000);
    await takeScreenshot(page, '18-admin-jahresuebersicht');

    // ========================================
    // TEIL 7: BENUTZERVERWALTUNG
    // ========================================
    console.log('\n👥 TEIL 7: BENUTZERVERWALTUNG');
    console.log('==============================\n');

    // 19: Benutzerverwaltung Vollansicht
    await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
    await sleep(3000);
    await takeScreenshot(page, '19-benutzerverwaltung-vollansicht', { fullPage: true });

    // 20: Benutzertabelle Close-up
    const userTable = await page.$('table');
    if (userTable) {
      const box = await userTable.boundingBox();
      await takeScreenshot(page, '20-benutzertabelle-detail', {
        clip: {
          x: Math.max(0, box.x - 10),
          y: Math.max(0, box.y - 60),
          width: Math.min(box.width + 20, 1900),
          height: Math.min(400, 1060)
        }
      });
    }

    // 21: Urlaubskonto-Ampel Close-up
    const vacationBadge = await page.$('td span.inline-flex.items-center');
    if (vacationBadge) {
      const box = await vacationBadge.boundingBox();
      await takeScreenshot(page, '21-urlaubskonto-ampel-detail', {
        clip: {
          x: Math.max(0, box.x - 150),
          y: Math.max(0, box.y - 100),
          width: Math.min(600, 1900),
          height: Math.min(300, 1060)
        }
      });
    }

    // ========================================
    // TEIL 8: BERICHTE
    // ========================================
    console.log('\n📋 TEIL 8: BERICHTE');
    console.log('====================\n');

    // 22: Berichte Vollansicht
    await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, '22-berichte-vollansicht', { fullPage: true });

    // 23: Monatsreport Bereich
    const monthReportSection = await page.$('.bg-white.rounded-xl');
    if (monthReportSection) {
      const box = await monthReportSection.boundingBox();
      await takeScreenshot(page, '23-monatsreport-bereich', {
        clip: {
          x: Math.max(0, box.x - 10),
          y: Math.max(0, box.y - 10),
          width: Math.min(box.width + 20, 1900),
          height: Math.min(box.height + 20, 1060)
        }
      });
    }

    // 24: Jahresreport Bereich
    await page.evaluate(() => window.scrollTo(0, 600));
    await sleep(1000);
    await takeScreenshot(page, '24-jahresreport-bereich');

    // ========================================
    // TEIL 9: MOBILE ANSICHTEN
    // ========================================
    console.log('\n📱 TEIL 9: MOBILE ANSICHTEN');
    console.log('============================\n');

    // Logout und Employee-Login
    await logout(page);
    await sleep(1000);
    await login(page, EMPLOYEE);

    // Mobile Viewport
    await page.setViewport({ width: 375, height: 812 });
    await sleep(1000);

    // 25: Mobile Dashboard
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '25-mobile-dashboard', { fullPage: true });

    // 26: Mobile Zeiterfassung
    await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '26-mobile-zeiterfassung', { fullPage: true });

    // 27: Mobile Abwesenheiten
    await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, '27-mobile-abwesenheiten', { fullPage: true });

    // Reset viewport
    await page.setViewport({ width: 1920, height: 1080 });

    console.log('\n✅ Alle Screenshots erstellt!');
    console.log(`📂 Speicherort: ${SCREENSHOTS_DIR}`);
    console.log(`📊 Anzahl: ${fs.readdirSync(SCREENSHOTS_DIR).length} Screenshots\n`);

  } catch (error) {
    console.error('❌ Fehler:', error);
    await takeScreenshot(page, 'error-screenshot');
    throw error;
  } finally {
    await browser.close();
  }
}

// Run
createDetailedHandbookScreenshots().catch(console.error);
