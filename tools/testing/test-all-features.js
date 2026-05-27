const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost';
const SCREENSHOTS_DIR = 'E:/claude/zeiterfassung/screenshots/complete-test';
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin123';

// Ensure screenshots directory exists
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function takeScreenshot(page, name, fullPage = false) {
  const filename = path.join(SCREENSHOTS_DIR, `${name}.png`);
  await page.screenshot({ path: filename, fullPage });
  console.log(`✅ Screenshot: ${name}`);
}

async function testLogin(page) {
  console.log('\n🔐 Testing Login...');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2' });
  await takeScreenshot(page, '01-login-page');

  await page.type('input[type="email"]', ADMIN_EMAIL);
  await page.type('input[type="password"]', ADMIN_PASSWORD);
  await takeScreenshot(page, '02-login-filled');

  await page.click('button[type="submit"]');
  await page.waitForNavigation({ waitUntil: 'networkidle2' });
  await takeScreenshot(page, '03-after-login-dashboard');
  console.log('✅ Login successful');
}

async function testDashboard(page) {
  console.log('\n📊 Testing Dashboard...');
  await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '04-dashboard-full', true);

  // Scroll to see all sections
  await page.evaluate(() => window.scrollTo(0, 500));
  await sleep(500);
  await takeScreenshot(page, '05-dashboard-middle');

  await page.evaluate(() => window.scrollTo(0, 1000));
  await sleep(500);
  await takeScreenshot(page, '06-dashboard-bottom');

  console.log('✅ Dashboard tested');
}

async function testTimeTracking(page) {
  console.log('\n⏱️ Testing Time Tracking...');
  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '07-time-tracking-overview', true);

  // Test month navigation
  const prevButton = await page.$('button[aria-label="Vorheriger Monat"]');
  if (prevButton) {
    await prevButton.click();
    await sleep(1000);
    await takeScreenshot(page, '08-time-tracking-prev-month');
  }

  const todayButton = await page.$('button[title="Zum aktuellen Monat springen"]');
  if (todayButton) {
    await todayButton.click();
    await sleep(1000);
    await takeScreenshot(page, '09-time-tracking-back-to-current');
  }

  // Try to open add entry form (if button exists)
  try {
    const addButton = await page.$x("//button[contains(text(), 'Neuer Eintrag')]");
    if (addButton.length > 0) {
      await addButton[0].click();
      await sleep(500);
      await takeScreenshot(page, '10-time-tracking-add-form');
    }
  } catch (e) {
    console.log('  ⚠️ Add button not found (may be normal)');
  }

  console.log('✅ Time Tracking tested');
}

async function testAbsences(page) {
  console.log('\n🏖️ Testing Absences...');
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '11-absences-calendar', true);

  // Test month navigation
  const nextButton = await page.$('button[aria-label="Nächster Monat"]');
  if (nextButton) {
    await nextButton.click();
    await sleep(1000);
    await takeScreenshot(page, '12-absences-next-month');
  }

  // Scroll to see user absences table
  await page.evaluate(() => window.scrollTo(0, 800));
  await sleep(500);
  await takeScreenshot(page, '13-absences-table');

  console.log('✅ Absences tested');
}

async function testAdminDashboard(page) {
  console.log('\n👔 Testing Admin Dashboard...');
  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '14-admin-dashboard-top', true);

  // Test filter input
  const filterInput = await page.$('input[placeholder*="Suche"]');
  if (filterInput) {
    await filterInput.type('admin');
    await sleep(1000);
    await takeScreenshot(page, '15-admin-dashboard-filtered');
    await filterInput.click({ clickCount: 3 });
    await filterInput.press('Backspace');
    await sleep(500);
  }

  // Test sorting by clicking header
  const nameHeader = await page.$('th:contains("Name")');
  if (nameHeader) {
    await nameHeader.click();
    await sleep(1000);
    await takeScreenshot(page, '16-admin-dashboard-sorted-name-asc');

    await nameHeader.click();
    await sleep(1000);
    await takeScreenshot(page, '17-admin-dashboard-sorted-name-desc');
  }

  // Click on first employee to open detail modal
  const firstRow = await page.$('tbody tr.cursor-pointer');
  if (firstRow) {
    await firstRow.click();
    await sleep(1500);
    await takeScreenshot(page, '18-admin-dashboard-employee-modal');

    // Scroll modal content
    await page.evaluate(() => {
      const modal = document.querySelector('[role="dialog"] .overflow-y-auto');
      if (modal) modal.scrollTop = 300;
    });
    await sleep(500);
    await takeScreenshot(page, '19-admin-dashboard-employee-modal-scrolled');

    // Close modal
    const closeButton = await page.$('[role="dialog"] button[aria-label*="schließen"]');
    if (closeButton) {
      await closeButton.click();
      await sleep(500);
    }
  }

  // Scroll to yearly overview
  await page.evaluate(() => window.scrollTo(0, 1500));
  await sleep(1000);
  await takeScreenshot(page, '20-admin-dashboard-yearly-overview');

  console.log('✅ Admin Dashboard tested');
}

async function testUsers(page) {
  console.log('\n👥 Testing User Management...');
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '21-users-list', true);

  // Test filter
  const filterInput = await page.$('input[placeholder*="Suche"]');
  if (filterInput) {
    await filterInput.type('admin');
    await sleep(1000);
    await takeScreenshot(page, '22-users-filtered');
    await filterInput.click({ clickCount: 3 });
    await filterInput.press('Backspace');
    await sleep(500);
  }

  // Test sorting
  const emailHeader = await page.$('th:contains("E-Mail")');
  if (emailHeader) {
    await emailHeader.click();
    await sleep(1000);
    await takeScreenshot(page, '23-users-sorted-email');
  }

  // Click "Neue:r Mitarbeiter:in" button (don't actually create, just show form)
  const addButton = await page.$('button:contains("Neue:r")');
  if (addButton) {
    await addButton.click();
    await sleep(500);
    await takeScreenshot(page, '24-users-add-form');

    // Close form
    const cancelButton = await page.$('button:contains("Abbrechen")');
    if (cancelButton) {
      await cancelButton.click();
      await sleep(500);
    }
  }

  console.log('✅ User Management tested');
}

async function testReports(page) {
  console.log('\n📋 Testing Reports...');
  await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '25-reports-page', true);

  // Scroll to yearly export section
  await page.evaluate(() => window.scrollTo(0, 800));
  await sleep(500);
  await takeScreenshot(page, '26-reports-yearly-section');

  console.log('✅ Reports tested');
}

async function testProfile(page) {
  console.log('\n👤 Testing Profile...');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '27-profile-page', true);

  // Try to open password change form
  const changePasswordButton = await page.$('button:contains("Passwort ändern")');
  if (changePasswordButton) {
    await changePasswordButton.click();
    await sleep(500);
    await takeScreenshot(page, '28-profile-password-form');

    // Close form
    const cancelButton = await page.$('button:contains("Abbrechen")');
    if (cancelButton) {
      await cancelButton.click();
      await sleep(500);
    }
  }

  console.log('✅ Profile tested');
}

async function testMobileViews(page) {
  console.log('\n📱 Testing Mobile Views...');

  // Set mobile viewport
  await page.setViewport({ width: 375, height: 667 });
  await sleep(500);

  // Test main pages on mobile
  await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '29-mobile-dashboard', true);

  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '30-mobile-time-tracking', true);

  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '31-mobile-absences', true);

  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '32-mobile-admin-dashboard', true);

  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '33-mobile-users', true);

  // Reset to desktop viewport
  await page.setViewport({ width: 1920, height: 1080 });
  await sleep(500);

  console.log('✅ Mobile Views tested');
}

async function testPasswordResetModal(page) {
  console.log('\n🔑 Testing Password Reset Modal...');
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(1500);

  // Find and click password reset button for first user
  const resetButton = await page.$('button[title="Passwort zurücksetzen"]');
  if (resetButton) {
    await resetButton.click();
    await sleep(500);

    // Confirm dialog
    page.on('dialog', async dialog => {
      await dialog.accept();
    });

    await sleep(2000);
    await takeScreenshot(page, '34-password-reset-modal');

    // Close modal
    const closeButton = await page.$('[role="dialog"] button:contains("Schließen")');
    if (closeButton) {
      await closeButton.click();
      await sleep(500);
    }
  }

  console.log('✅ Password Reset Modal tested');
}

async function testHolidaysInCalendar(page) {
  console.log('\n🎄 Testing Holidays in Calendar...');
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Look for a month with holidays (try navigating)
  for (let i = 0; i < 3; i++) {
    await takeScreenshot(page, `35-calendar-holidays-month-${i + 1}`);
    const nextButton = await page.$('button[aria-label="Nächster Monat"]');
    if (nextButton) {
      await nextButton.click();
      await sleep(1000);
    }
  }

  console.log('✅ Holidays in Calendar tested');
}

async function runTests() {
  console.log('🚀 Starting Complete UI Tests...\n');
  console.log(`📂 Screenshots will be saved to: ${SCREENSHOTS_DIR}\n`);

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: { width: 1920, height: 1080 },
    args: ['--start-maximized']
  });

  try {
    const page = await browser.newPage();

    // Set longer timeouts
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(30000);

    // Test all features
    await testLogin(page);
    await testDashboard(page);
    await testTimeTracking(page);
    await testAbsences(page);
    await testAdminDashboard(page);
    await testUsers(page);
    await testReports(page);
    await testProfile(page);
    await testPasswordResetModal(page);
    await testHolidaysInCalendar(page);
    await testMobileViews(page);

    console.log('\n✅ All tests completed successfully!');
    console.log(`\n📊 Total screenshots: ${fs.readdirSync(SCREENSHOTS_DIR).length}`);
    console.log(`📂 Location: ${SCREENSHOTS_DIR}`);

  } catch (error) {
    console.error('\n❌ Test failed:', error);
    throw error;
  } finally {
    await browser.close();
  }
}

// Run tests
runTests().catch(console.error);
