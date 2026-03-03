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
  // Rate limiting on login (5/min) can cause setup timeouts
  test.slow();

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
