const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    // Login
    await page.goto('http://localhost/login', { waitUntil: 'networkidle2', timeout: 15000 });
    await page.type('input[type="text"]', 'admin');
    await page.type('input[type="password"]', 'Admin2025!');
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });

    // Go to admin users
    await page.goto('http://localhost/admin/users', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 2000));

    // Dump all button texts and their positions
    const buttonInfo = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button')).map((b, i) => ({
        index: i,
        text: b.textContent.trim(),
        visible: b.offsetParent !== null,
        rect: b.getBoundingClientRect()
      }));
    });
    console.log('Buttons on admin/users page:');
    buttonInfo.filter(b => b.visible).forEach(b => {
      console.log(`  [${b.index}] "${b.text}" at (${Math.round(b.rect.x)}, ${Math.round(b.rect.y)})`);
    });

    // Also dump all links
    const linkInfo = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('a')).map((a, i) => ({
        index: i,
        text: a.textContent.trim(),
        href: a.href,
        visible: a.offsetParent !== null
      }));
    });
    console.log('\nLinks on admin/users page:');
    linkInfo.filter(l => l.visible && l.text).forEach(l => {
      console.log(`  [${l.index}] "${l.text}" → ${l.href}`);
    });

    // Click first "Bearbeiten" button using XPath/evaluate
    const clicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const editBtn = buttons.find(b => b.textContent.trim() === 'Bearbeiten');
      if (editBtn) {
        editBtn.click();
        return true;
      }
      return false;
    });
    console.log('\nClicked Bearbeiten button:', clicked);

    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: '/tmp/03c-after-edit-click.png', fullPage: false });
    console.log('Screenshot saved');

  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
