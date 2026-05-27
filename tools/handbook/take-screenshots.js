const puppeteer = require('puppeteer');

(async () => {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });

    // 1. Login page
    console.log('Navigating to login page...');
    await page.goto('http://localhost/login', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: '/tmp/01-login.png', fullPage: false });
    console.log('Screenshot 1: Login page saved');

    // 2. Perform login
    console.log('Logging in...');
    // Try to find username input
    const usernameInput = await page.$('input[name="username"], input[type="text"], input[id="username"]');
    const passwordInput = await page.$('input[type="password"]');

    if (usernameInput && passwordInput) {
      await usernameInput.click({ clickCount: 3 });
      await usernameInput.type('admin');
      await passwordInput.click({ clickCount: 3 });
      await passwordInput.type('Admin2025!');
      await page.click('button[type="submit"]');
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
      await new Promise(r => setTimeout(r, 1500));
    } else {
      console.log('Could not find login inputs, trying alternative selectors...');
      // Dump page HTML for debugging
      const html = await page.content();
      console.log('Page HTML (first 2000 chars):', html.substring(0, 2000));
    }

    // 3. Dashboard
    console.log('Taking dashboard screenshot...');
    await page.screenshot({ path: '/tmp/02-dashboard.png', fullPage: false });
    console.log('Current URL:', page.url());
    console.log('Screenshot 2: Dashboard saved');

    // 4. Admin Users page
    console.log('Navigating to admin users...');
    await page.goto('http://localhost/admin/users', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: '/tmp/03-admin-users.png', fullPage: true });
    console.log('Screenshot 3: Admin Users saved');

    // 5. Admin Error Monitoring page
    console.log('Navigating to admin error monitoring...');
    await page.goto('http://localhost/admin/errors', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: '/tmp/04-admin-errors.png', fullPage: true });
    console.log('Screenshot 4: Admin Errors saved');

    console.log('All screenshots taken successfully!');
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
