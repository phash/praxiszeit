import { test, expect } from '../../fixtures/base.fixture';
import { Page } from '@playwright/test';

/**
 * Password fields use PasswordInput component wrapped in <div class="relative">,
 * so <label> elements have no htmlFor/id association. We locate inputs by finding the
 * label text, then navigating to the sibling input via the parent container.
 */
function getPasswordField(page: Page, labelText: string) {
  return page.locator('label', { hasText: labelText }).locator('..').locator('input');
}

test.describe('Employee Profile', () => {
  test.beforeEach(async ({ employeePage }) => {
    await employeePage.goto('/profile');
    await expect(employeePage.getByRole('heading', { name: 'Profil' })).toBeVisible();
  });

  test('shows profile data', async ({ employeePage, testEmployee }) => {
    // Check heading
    await expect(employeePage.getByRole('heading', { name: 'Profil' })).toBeVisible();

    // Check the test employee's full name (first + last) in the profile heading
    const fullName = `${testEmployee.first_name} ${testEmployee.last_name}`;
    await expect(employeePage.getByRole('heading', { name: fullName })).toBeVisible();

    // Check the username is visible
    await expect(employeePage.getByText(testEmployee.username).first()).toBeVisible();
  });

  test('edit name', async ({ employeePage }) => {
    // Click "Bearbeiten" to show the profile edit form
    await employeePage.getByRole('button', { name: 'Bearbeiten' }).click();

    // The form should show with Vorname and Nachname inputs
    const vornameInput = employeePage.locator('label', { hasText: 'Vorname' }).locator('..').locator('input');
    await vornameInput.clear();
    await vornameInput.fill('UpdatedFirst');

    // Click save
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Check for success message
    await expect(employeePage.getByText('Daten erfolgreich aktualisiert')).toBeVisible({ timeout: 10000 });

    // Verify the updated name is visible (use .first() since sidebar and heading both show name)
    await expect(employeePage.getByText('UpdatedFirst').first()).toBeVisible();
  });

  test('change calendar color', async ({ employeePage }) => {
    // Check that "Kalenderfarbe" section is visible
    await expect(employeePage.getByText('Kalenderfarbe')).toBeVisible();

    // Click a color button (use the second one to change from default)
    const colorButtons = employeePage.locator('button[title]').filter({ has: employeePage.locator('.aspect-square') });
    // Click the "Rosa" color button (the second one)
    await employeePage.locator('button[title="Rosa"]').click();

    // Check for success message
    await expect(employeePage.getByText('Kalenderfarbe erfolgreich aktualisiert')).toBeVisible({ timeout: 10000 });
  });

  test('DSGVO data export', async ({ employeePage }) => {
    // Check that the download button exists
    const downloadButton = employeePage.getByRole('button', { name: 'JSON herunterladen' });
    await expect(downloadButton).toBeVisible();

    // Set up download event listener
    const downloadPromise = employeePage.waitForEvent('download', { timeout: 15000 });
    await downloadButton.click();

    // Verify download started
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('PraxisZeit_Datenauszug');
  });

  test('Profilbild: Upload gültiges JPEG zeigt Erfolgsmeldung', async ({ employeePage }) => {
    // Minimal valid JPEG bytes (1x1 pixel)
    const jpegBytes = Buffer.from([
      0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
      0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
      0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
      0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
      0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
      0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
      0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
      0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
      0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
      0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
      0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
      0x00, 0xFB, 0xFF, 0xD9,
    ]);

    // The file input is hidden (display:none) — setInputFiles works on hidden inputs
    await employeePage.locator('input[type="file"]').setInputFiles({
      name: 'test.jpg',
      mimeType: 'image/jpeg',
      buffer: jpegBytes,
    });

    // Expect success message
    await expect(employeePage.getByText('Profilbild aktualisiert')).toBeVisible({ timeout: 10000 });
  });

  test('Profilbild: Ungültiger Dateityp zeigt Fehlermeldung', async ({ employeePage }) => {
    // Bytes with no JPEG/PNG magic bytes — backend will reject with 400
    const invalidBytes = Buffer.from('This is not an image file content at all');

    await employeePage.locator('input[type="file"]').setInputFiles({
      name: 'test.txt',
      mimeType: 'application/octet-stream',
      buffer: invalidBytes,
    });

    // Backend returns "Nur JPEG oder PNG erlaubt" → getErrorMessage passes it through
    await expect(employeePage.getByText('Nur JPEG oder PNG erlaubt')).toBeVisible({ timeout: 10000 });
  });

  test('Profilbild: Datei zu groß zeigt Fehlermeldung', async ({ employeePage }) => {
    // 501 KB buffer with JPEG magic bytes — client-side check fires first (>512_000 bytes)
    const oversizeBuffer = Buffer.alloc(501 * 1024, 0);
    oversizeBuffer[0] = 0xFF;
    oversizeBuffer[1] = 0xD8;
    oversizeBuffer[2] = 0xFF;

    await employeePage.locator('input[type="file"]').setInputFiles({
      name: 'big.jpg',
      mimeType: 'image/jpeg',
      buffer: oversizeBuffer,
    });

    // Client-side check fires before API call
    await expect(employeePage.getByText('Bild zu groß (max. 500 KB)')).toBeVisible({ timeout: 5000 });
  });

  test('password change section', async ({ employeePage, testEmployee, adminApi }) => {
    // Click "Ändern" to open the password form
    await employeePage.getByRole('button', { name: 'Ändern' }).click();

    // Fill password fields
    await getPasswordField(employeePage, 'Aktuelles Passwort').fill(testEmployee.password);
    const newPassword = 'NewTestPass789!';
    await getPasswordField(employeePage, 'Neues Passwort').fill(newPassword);
    await getPasswordField(employeePage, 'Passwort bestätigen').fill(newPassword);

    // Save
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // On success, the form should collapse and "Ändern" button reappears
    await expect(employeePage.getByRole('button', { name: 'Ändern' })).toBeVisible({ timeout: 10000 });

    // Reset password via admin for cleanup
    await adminApi.post(`/admin/users/${testEmployee.id}/set-password`, {
      password: testEmployee.password,
    });
  });
});
