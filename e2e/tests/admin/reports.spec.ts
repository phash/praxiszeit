import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Reports', () => {
  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/admin/reports');
    await expect(adminPage.getByRole('heading', { name: 'Berichte & Export' })).toBeVisible();
  });

  test('Excel monthly export triggers download', async ({ adminPage }) => {
    // Set up download listener
    const downloadPromise = adminPage.waitForEvent('download', { timeout: 30000 });

    // Click the Excel (.xlsx) button in the monthly section
    const excelButton = adminPage.getByRole('button', { name: 'Excel (.xlsx)' });
    await expect(excelButton).toBeVisible();
    await excelButton.click();

    // Wait for download
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.xlsx');
    expect(download.suggestedFilename()).toContain('Monatsreport');
  });

  test('ODS monthly export triggers download', async ({ adminPage }) => {
    const downloadPromise = adminPage.waitForEvent('download', { timeout: 30000 });

    const odsButton = adminPage.getByRole('button', { name: 'ODS (.ods)' });
    await expect(odsButton).toBeVisible();
    await odsButton.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.ods');
    expect(download.suggestedFilename()).toContain('Monatsreport');
  });

  test('PDF monthly export triggers download', async ({ adminPage }) => {
    const downloadPromise = adminPage.waitForEvent('download', { timeout: 30000 });

    const pdfButton = adminPage.getByRole('button', { name: 'PDF (.pdf)' });
    await expect(pdfButton).toBeVisible();
    await pdfButton.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.pdf');
    expect(download.suggestedFilename()).toContain('Monatsreport');
  });

  test('yearly export triggers download', async ({ adminPage }) => {
    // Scroll to yearly section
    const yearlyHeading = adminPage.getByRole('heading', { name: 'Jahresreport exportieren' });
    await yearlyHeading.scrollIntoViewIfNeeded();
    await expect(yearlyHeading).toBeVisible();

    // The yearly section has two format cards with Excel/ODS buttons
    // Find the first Excel button in the yearly section (Classic format card)
    const downloadPromise = adminPage.waitForEvent('download', { timeout: 60000 });

    // Use the card that contains "Classic Format" text and find the Excel button within
    const classicCard = adminPage.locator('.border.border-gray-300.rounded-lg').filter({ hasText: 'Classic Format' });
    await expect(classicCard).toBeVisible();
    const excelButton = classicCard.getByRole('button', { name: 'Excel' });
    await expect(excelButton).toBeVisible();
    await excelButton.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.xlsx');
  });

  test('ArbZG rest-time report loads', async ({ adminPage }) => {
    // Scroll to rest time section
    const restHeading = adminPage.getByRole('heading', { name: 'Ruhezeitprüfung' });
    await restHeading.scrollIntoViewIfNeeded();

    // Find the "Prüfen" button that is associated with the rest-time section
    const restSection = restHeading.locator('..').locator('..');
    const pruefenButton = restSection.getByRole('button', { name: 'Prüfen' });
    await expect(pruefenButton).toBeVisible();
    await pruefenButton.click();

    // Wait for results - use .first() to avoid strict mode
    const resultIndicator = adminPage.getByText('Keine Ruhezeitverstöße gefunden').first()
      .or(adminPage.getByText('Verstöße bei').first());

    await expect(resultIndicator).toBeVisible({ timeout: 15000 });
  });

  test('ArbZG Sunday report loads', async ({ adminPage }) => {
    // Scroll to Sunday section
    const sundayHeading = adminPage.getByRole('heading', { name: 'Sonntagsarbeit §11 ArbZG' });
    await sundayHeading.scrollIntoViewIfNeeded();

    // Find the "Prüfen" button
    const sundaySection = sundayHeading.locator('..').locator('..');
    const pruefenButton = sundaySection.getByRole('button', { name: 'Prüfen' });
    await expect(pruefenButton).toBeVisible();
    await pruefenButton.click();

    // Wait for results - either the results table header or success toast
    // Both may appear simultaneously, so check for either one individually
    const tableHeader = adminPage.getByRole('columnheader', { name: 'Gearbeitete So.' });
    const successToast = adminPage.locator('[role="alert"]').filter({ hasText: '§11' });

    // Wait until at least one is visible
    await Promise.race([
      expect(tableHeader).toBeVisible({ timeout: 15000 }).catch(() => {}),
      expect(successToast).toBeVisible({ timeout: 15000 }).catch(() => {}),
    ]);

    // Verify at least one is actually visible
    const hasTable = await tableHeader.isVisible().catch(() => false);
    const hasToast = await successToast.first().isVisible().catch(() => false);
    expect(hasTable || hasToast).toBeTruthy();
  });
});
