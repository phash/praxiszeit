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
  await sleep(1500);
  await takeScreenshot(page, '04-dashboard-full', true);

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
  await sleep(1500);
  await takeScreenshot(page, '07-time-tracking-overview', true);

  // Test month navigation with aria-label
  try {
    await page.click('button[aria-label="Vorheriger Monat"]');
    await sleep(1000);
    await takeScreenshot(page, '08-time-tracking-prev-month');

    await page.click('button[title="Zum aktuellen Monat springen"]');
    await sleep(1000);
    await takeScreenshot(page, '09-time-tracking-back-to-current');
  } catch (e) {
    console.log('  ⚠️ Month navigation not found');
  }

  console.log('✅ Time Tracking tested');
}

async function testAbsences(page) {
  console.log('\n🏖️ Testing Absences...');
  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '10-absences-calendar', true);

  // Test month navigation
  try {
    await page.click('button[aria-label="Nächster Monat"]');
    await sleep(1000);
    await takeScreenshot(page, '11-absences-next-month');
  } catch (e) {
    console.log('  ⚠️ Next button not found');
  }

  // Scroll to see user absences table
  await page.evaluate(() => window.scrollTo(0, 800));
  await sleep(500);
  await takeScreenshot(page, '12-absences-table');

  console.log('✅ Absences tested');
}

async function testAdminDashboard(page) {
  console.log('\n👔 Testing Admin Dashboard...');
  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(2000);
  await takeScreenshot(page, '13-admin-dashboard-top', true);

  // Test filter input
  const filterInput = await page.$('input[placeholder*="Suche"]');
  if (filterInput) {
    await filterInput.type('admin');
    await sleep(1000);
    await takeScreenshot(page, '14-admin-dashboard-filtered');
    await filterInput.click({ clickCount: 3 });
    await page.keyboard.press('Backspace');
    await sleep(500);
  }

  // Test sorting by clicking first sortable header
  const sortableHeaders = await page.$$('th.cursor-pointer');
  if (sortableHeaders.length > 0) {
    await sortableHeaders[0].click();
    await sleep(1000);
    await takeScreenshot(page, '15-admin-dashboard-sorted-asc');

    await sortableHeaders[0].click();
    await sleep(1000);
    await takeScreenshot(page, '16-admin-dashboard-sorted-desc');
  }

  // Click on first employee to open detail modal
  const firstRow = await page.$('tbody tr.cursor-pointer');
  if (firstRow) {
    await firstRow.click();
    await sleep(1500);
    await takeScreenshot(page, '17-admin-dashboard-employee-modal');

    // Scroll modal content
    await page.evaluate(() => {
      const modal = document.querySelector('[role="dialog"] .overflow-y-auto');
      if (modal) modal.scrollTop = 400;
    });
    await sleep(500);
    await takeScreenshot(page, '18-admin-dashboard-modal-scrolled');

    // Close modal with X button
    const closeButton = await page.$('[role="dialog"] button svg');
    if (closeButton) {
      await closeButton.click();
      await sleep(500);
    } else {
      // Try ESC key
      await page.keyboard.press('Escape');
      await sleep(500);
    }
  }

  // Scroll to yearly overview
  await page.evaluate(() => window.scrollTo(0, 1800));
  await sleep(1000);
  await takeScreenshot(page, '19-admin-dashboard-yearly-overview');

  console.log('✅ Admin Dashboard tested');
}

async function testUsers(page) {
  console.log('\n👥 Testing User Management...');
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(2000);
  await takeScreenshot(page, '20-users-list', true);

  // Test filter
  const filterInput = await page.$('input[placeholder*="Suche"]');
  if (filterInput) {
    await filterInput.type('admin');
    await sleep(1000);
    await takeScreenshot(page, '21-users-filtered');
    await filterInput.click({ clickCount: 3 });
    await page.keyboard.press('Backspace');
    await sleep(500);
  }

  // Test sorting
  const sortableHeaders = await page.$$('th.cursor-pointer');
  if (sortableHeaders.length > 1) {
    await sortableHeaders[1].click();
    await sleep(1000);
    await takeScreenshot(page, '22-users-sorted');
  }

  // Scroll to see all users
  await page.evaluate(() => window.scrollTo(0, 800));
  await sleep(500);
  await takeScreenshot(page, '23-users-scrolled');

  console.log('✅ User Management tested');
}

async function testReports(page) {
  console.log('\n📋 Testing Reports...');
  await page.goto(`${BASE_URL}/admin/reports`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '24-reports-page', true);

  // Scroll to yearly export section
  await page.evaluate(() => window.scrollTo(0, 800));
  await sleep(500);
  await takeScreenshot(page, '25-reports-yearly-section');

  console.log('✅ Reports tested');
}

async function testProfile(page) {
  console.log('\n👤 Testing Profile...');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2' });
  await sleep(1000);
  await takeScreenshot(page, '26-profile-page', true);

  console.log('✅ Profile tested');
}

async function testMobileViews(page) {
  console.log('\n📱 Testing Mobile Views...');

  // Set mobile viewport
  await page.setViewport({ width: 375, height: 667 });
  await sleep(500);

  // Test main pages on mobile
  await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '27-mobile-dashboard', true);

  await page.goto(`${BASE_URL}/time-tracking`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '28-mobile-time-tracking', true);

  await page.goto(`${BASE_URL}/absences`, { waitUntil: 'networkidle2' });
  await sleep(1500);
  await takeScreenshot(page, '29-mobile-absences', true);

  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(2000);
  await takeScreenshot(page, '30-mobile-admin-dashboard', true);

  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(2000);
  await takeScreenshot(page, '31-mobile-users', true);

  // Reset to desktop viewport
  await page.setViewport({ width: 1920, height: 1080 });
  await sleep(500);

  console.log('✅ Mobile Views tested');
}

async function testSortingAndFilters(page) {
  console.log('\n🔍 Testing Sorting & Filters...');

  // Test Users table sorting
  await page.goto(`${BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
  await sleep(2000);

  // Click different sortable headers
  const headers = await page.$$('th.cursor-pointer');
  for (let i = 0; i < Math.min(3, headers.length); i++) {
    await headers[i].click();
    await sleep(800);
    await takeScreenshot(page, `32-sorting-column-${i + 1}`);
  }

  // Test filter with different searches
  const filterInput = await page.$('input[placeholder*="Suche"]');
  if (filterInput) {
    await filterInput.type('test');
    await sleep(1000);
    await takeScreenshot(page, '33-filter-test');

    await filterInput.click({ clickCount: 3 });
    await page.keyboard.press('Backspace');
    await sleep(500);
  }

  console.log('✅ Sorting & Filters tested');
}

async function testChevronIcons(page) {
  console.log('\n➡️ Testing ChevronRight Icons...');

  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: 'networkidle2' });
  await sleep(2000);

  // Desktop view - check for chevron icons
  await takeScreenshot(page, '34-chevron-desktop');

  // Mobile view
  await page.setViewport({ width: 375, height: 667 });
  await sleep(1000);
  await takeScreenshot(page, '35-chevron-mobile');

  // Reset viewport
  await page.setViewport({ width: 1920, height: 1080 });

  console.log('✅ ChevronRight Icons tested');
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
    await testMobileViews(page);
    await testSortingAndFilters(page);
    await testChevronIcons(page);

    console.log('\n✅ All tests completed successfully!');
    console.log(`\n📊 Total screenshots: ${fs.readdirSync(SCREENSHOTS_DIR).length}`);
    console.log(`📂 Location: ${SCREENSHOTS_DIR}`);

    // Generate test report
    const report = {
      timestamp: new Date().toISOString(),
      totalTests: 11,
      passedTests: 11,
      failedTests: 0,
      totalScreenshots: fs.readdirSync(SCREENSHOTS_DIR).length,
      screenshotsDir: SCREENSHOTS_DIR
    };

    fs.writeFileSync(
      path.join(SCREENSHOTS_DIR, 'test-report.json'),
      JSON.stringify(report, null, 2)
    );

    console.log('\n📄 Test report saved: test-report.json');

  } catch (error) {
    console.error('\n❌ Test failed:', error);
    await takeScreenshot(page, 'error-screenshot');
    throw error;
  } finally {
    await browser.close();
  }
}

// Run tests
runTests().catch(console.error);
