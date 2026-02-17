const puppeteer = require('puppeteer');

(async () => {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    // Login first
    await page.goto('http://localhost/login', { waitUntil: 'networkidle2', timeout: 15000 });
    const usernameInput = await page.$('input[name="username"], input[type="text"], input[id="username"]');
    const passwordInput = await page.$('input[type="password"]');
    await usernameInput.type('admin');
    await passwordInput.type('Admin2025!');
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 1000));

    // Admin Users - wider viewport for table
    await page.goto('http://localhost/admin/users', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: '/tmp/03-admin-users-wide.png', fullPage: true });
    console.log('Admin Users wide screenshot saved');

    // Click on first user to see the edit form with toggle
    const editButtons = await page.$$('button');
    let editBtn = null;
    for (const btn of editButtons) {
      const text = await btn.evaluate(el => el.textContent.trim());
      if (text === 'Bearbeiten' || text.includes('Edit')) {
        editBtn = btn;
        break;
      }
    }

    if (editBtn) {
      await editBtn.click();
      await new Promise(r => setTimeout(r, 1500));
      await page.screenshot({ path: '/tmp/03b-user-edit-form.png', fullPage: false });
      console.log('User edit form screenshot saved');
    } else {
      // Try clicking on a row or the first action link
      const links = await page.$$('a[href*="/admin/users/"]');
      if (links.length > 0) {
        await links[0].click();
        await new Promise(r => setTimeout(r, 1500));
        await page.screenshot({ path: '/tmp/03b-user-edit-form.png', fullPage: false });
        console.log('User page screenshot saved');
      } else {
        console.log('No edit button or user link found');
        // Dump page info
        const buttons = await page.evaluate(() => {
          return Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).slice(0, 20);
        });
        console.log('Available buttons:', buttons);
      }
    }

    console.log('Done!');
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
