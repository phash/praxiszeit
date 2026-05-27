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

    // Click first edit button (icon-only, opens form inline)
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      // "Neue:r Mitarbeiter:in" is index 3, so edit buttons start at index 4
      // Click the first icon button after the header buttons
      // Find buttons that are likely edit buttons (small icon buttons in table rows)
      const editBtn = buttons.find(b => {
        const text = b.textContent.trim();
        const title = b.title || b.getAttribute('aria-label') || '';
        return title.toLowerCase().includes('bear') || title.toLowerCase().includes('edit') ||
               (text === '' && b.closest('td, tr'));
      });
      if (editBtn) {
        editBtn.click();
        return 'found title button';
      }
      // Fallback: click 4th button (after Abmelden and Neue:r Mitarbeiter:in)
      if (buttons[4]) {
        buttons[4].click();
        return 'clicked index 4';
      }
      return 'not found';
    });
    await new Promise(r => setTimeout(r, 2000));

    // Now click the "Individuelle Tagesstunden" checkbox to expand it
    const toggleClicked = await page.evaluate(() => {
      const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
      const toggle = checkboxes.find(cb => {
        const label = cb.closest('label') || cb.parentElement;
        return label && label.textContent.includes('Individuelle Tagesstunden');
      });
      if (toggle && !toggle.checked) {
        toggle.click();
        return true;
      }
      // Also try by label text
      const labels = Array.from(document.querySelectorAll('label'));
      const lbl = labels.find(l => l.textContent.includes('Individuelle Tagesstunden'));
      if (lbl) {
        lbl.click();
        return true;
      }
      return false;
    });
    console.log('Toggle clicked:', toggleClicked);
    await new Promise(r => setTimeout(r, 1500));

    await page.screenshot({ path: '/tmp/03d-daily-schedule-expanded.png', fullPage: false });
    console.log('Daily schedule toggle screenshot saved');

    // Also scroll down to see full expanded form
    await page.evaluate(() => window.scrollTo(0, 300));
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: '/tmp/03e-daily-schedule-scrolled.png', fullPage: false });
    console.log('Scrolled screenshot saved');

  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
