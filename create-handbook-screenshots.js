const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost';
const SCREENSHOTS_DIR = path.join(__dirname, 'handbook-screenshots');
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin123';

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

async function createHandbookScreenshots() {
  console.log('📸 Erstelle Handbuch-Screenshots...\n');

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: { width: 1920, height: 1080 },
    args: ['--start-maximized']
  });

  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(30000);

    // 1. Login-Seite
    console.log('🔐 1. Login-Seite...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
    await sleep(1000);
    await takeScreenshot(page, 'hb-01-login-page');

    // Login durchführen
    await page.type('input[type="email"]', ADMIN_EMAIL);
    await page.type('input[type="password"]', ADMIN_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'networkidle2' });
    await sleep(1500);

    // 2. Dashboard - Stat Cards
    console.log('📊 2. Dashboard - Stat Cards...');
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2000);

    // Crop to show only stat cards
    const statCards = await page.$('.grid.grid-cols-1.md\\:grid-cols-3');
    if (statCards) {
      const box = await statCards.boundingBox();
      await takeScreenshot(page, 'hb-02-dashboard-stat-cards', {
        clip: {
          x: box.x - 20,
          y: box.y - 20,
          width: box.width + 40,
          height: box.height + 40
        }
      });
    }

    // 3. Dashboard - Team Calendar
    console.log('📅 3. Dashboard - Team Calendar...');
    await page.evaluate(() => window.scrollTo(0, 400));
    await sleep(1000);
    await takeScreenshot(page, 'hb-03-dashboard-team-calendar', { fullPage: true });

    // 4. Zeiterfassung - Wochenansicht
    console.log('⏱️ 4. Zeiterfassung - Wochenansicht...');
    await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, 'hb-04-zeiterfassung-woche', { fullPage: true });

    // 5. Zeiterfassung - MonthSelector (close-up)
    const monthSelector = await page.$('.flex.items-center.justify-between.mb-4');
    if (monthSelector) {
      const box = await monthSelector.boundingBox();
      await takeScreenshot(page, 'hb-05-month-selector', {
        clip: {
          x: box.x - 20,
          y: box.y - 20,
          width: box.width + 40,
          height: box.height + 40
        }
      });
    }

    // 6. Abwesenheiten - Kalender
    console.log('🏖️ 6. Abwesenheiten - Kalender...');
    await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, 'hb-06-abwesenheiten-kalender', { fullPage: true });

    // 7. Abwesenheiten - Tabelle (scrolled down)
    await page.evaluate(() => window.scrollTo(0, 800));
    await sleep(1000);
    await takeScreenshot(page, 'hb-07-abwesenheiten-tabelle');

    // 8. Profil-Seite
    console.log('👤 8. Profil-Seite...');
    await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
    await sleep(1500);
    await takeScreenshot(page, 'hb-08-profil-seite', { fullPage: true });

    // 9. Admin-Dashboard - Monatsübersicht
    console.log('👔 9. Admin-Dashboard - Monatsübersicht...');
    await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, 'hb-09-admin-dashboard-monat', { fullPage: true });

    // 10. Admin-Dashboard - Sortierung (click header)
    const sortableHeader = await page.$('th.cursor-pointer');
    if (sortableHeader) {
      await sortableHeader.click();
      await sleep(1000);

      // Crop to show sorting indicator
      const headerBox = await sortableHeader.boundingBox();
      await takeScreenshot(page, 'hb-10-sortierung-indicator', {
        clip: {
          x: headerBox.x - 50,
          y: headerBox.y - 50,
          width: 400,
          height: 150
        }
      });
    }

    // 11. Admin-Dashboard - Filter Input
    const filterInput = await page.$('input[placeholder*="Suche"]');
    if (filterInput) {
      await filterInput.type('admin');
      await sleep(1000);
      await takeScreenshot(page, 'hb-11-filter-aktiv');

      // Clear filter
      await filterInput.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      await sleep(500);
    }

    // 12. Admin-Dashboard - Jahresübersicht
    await page.evaluate(() => window.scrollTo(0, 1800));
    await sleep(1500);
    await takeScreenshot(page, 'hb-12-admin-dashboard-jahr');

    // 13. Admin-Dashboard - Mitarbeiter-Detail Modal
    const firstRow = await page.evaluate(() => {
      window.scrollTo(0, 0);
      return true;
    });
    await sleep(1000);
    const clickableRow = await page.$('tbody tr.cursor-pointer');
    if (clickableRow) {
      await clickableRow.click();
      await sleep(2000);
      await takeScreenshot(page, 'hb-13-mitarbeiter-detail-modal');

      // Close modal
      await page.keyboard.press('Escape');
      await sleep(500);
    }

    // 14. Benutzerverwaltung - Liste
    console.log('👥 14. Benutzerverwaltung - Liste...');
    await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
    await sleep(2500);
    await takeScreenshot(page, 'hb-14-benutzerverwaltung-liste', { fullPage: true });

    // 15. Benutzerverwaltung - Urlaubskonto Ampel (close-up)
    const vacationCell = await page.$('td span.inline-flex.items-center.px-2.py-1');
    if (vacationCell) {
      const box = await vacationCell.boundingBox();
      await takeScreenshot(page, 'hb-15-urlaubskonto-ampel', {
        clip: {
          x: box.x - 100,
          y: box.y - 50,
          width: 400,
          height: 150
        }
      });
    }

    // 16. Berichte-Seite
    console.log('📋 16. Berichte-Seite...');
    await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
    await sleep(1500);
    await takeScreenshot(page, 'hb-16-berichte-seite', { fullPage: true });

    // 17. Mobile View - Dashboard
    console.log('📱 17. Mobile Views...');
    await page.setViewport({ width: 375, height: 812 });
    await sleep(500);

    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, 'hb-17-mobile-dashboard', { fullPage: true });

    // 18. Mobile View - Navigation Menu (if visible)
    await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await takeScreenshot(page, 'hb-18-mobile-zeiterfassung', { fullPage: true });

    // 19. ChevronRight Icons (Desktop)
    await page.setViewport({ width: 1920, height: 1080 });
    await sleep(500);

    await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
    await sleep(2500);

    const chevronRow = await page.$('tbody tr.cursor-pointer');
    if (chevronRow) {
      const box = await chevronRow.boundingBox();
      await takeScreenshot(page, 'hb-19-chevron-desktop', {
        clip: {
          x: box.x,
          y: box.y,
          width: box.width,
          height: box.height * 2
        }
      });
    }

    // 20. Farbcodierung - Abwesenheitstypen
    await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
    await sleep(2000);
    await page.evaluate(() => window.scrollTo(0, 800));
    await sleep(1000);

    const absenceTable = await page.$('.overflow-x-auto table');
    if (absenceTable) {
      const box = await absenceTable.boundingBox();
      await takeScreenshot(page, 'hb-20-farbcodierung-typen', {
        clip: {
          x: box.x,
          y: box.y,
          width: Math.min(box.width, 1200),
          height: Math.min(box.height, 400)
        }
      });
    }

    console.log('\n✅ Alle Screenshots erstellt!');
    console.log(`📂 Speicherort: ${SCREENSHOTS_DIR}`);
    console.log(`📊 Anzahl: ${fs.readdirSync(SCREENSHOTS_DIR).length} Screenshots\n`);

  } catch (error) {
    console.error('❌ Fehler:', error);
    throw error;
  } finally {
    await browser.close();
  }
}

// Run
createHandbookScreenshots().catch(console.error);
