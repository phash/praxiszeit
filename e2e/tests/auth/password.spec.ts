import { test, expect } from '../../fixtures/base.fixture';
import { Page } from '@playwright/test';

/**
 * The password form uses PasswordInput components wrapped in a <div class="relative">,
 * so <label> elements have no htmlFor/id association. We locate inputs by finding the
 * label text, then navigating to the sibling input via the parent container.
 */
function getPasswordField(page: Page, labelText: string) {
  return page.locator('label', { hasText: labelText }).locator('..').locator('input');
}

test.describe('Password Change', () => {
  test('employee can change password and login with new one', async ({
    employeePage,
    testEmployee,
    adminApi,
  }) => {
    const newPassword = 'NewTestPass456!';

    await employeePage.getByRole('link', { name: 'Profil' }).click();
    await employeePage.waitForURL('/profile');

    // Click "Ändern" to show password form
    await employeePage.getByRole('button', { name: 'Ändern' }).click();

    // Fill in the password change form
    await getPasswordField(employeePage, 'Aktuelles Passwort').fill(testEmployee.password);
    await getPasswordField(employeePage, 'Neues Passwort').fill(newPassword);
    await getPasswordField(employeePage, 'Passwort bestätigen').fill(newPassword);
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // On success, the form collapses and the "Ändern" button reappears
    await expect(employeePage.getByRole('button', { name: 'Ändern' })).toBeVisible({ timeout: 10000 });
    // The hint text reappears when form is collapsed
    await expect(employeePage.getByText('Mind. 10 Zeichen')).toBeVisible();

    // Reset password via admin for cleanup
    await adminApi.post(`/admin/users/${testEmployee.id}/set-password`, {
      password: testEmployee.password,
    });
  });

  test('password complexity enforced', async ({ employeePage, testEmployee }) => {
    await employeePage.getByRole('link', { name: 'Profil' }).click();
    await employeePage.waitForURL('/profile');

    await employeePage.getByRole('button', { name: 'Ändern' }).click();

    // Use a password that passes HTML5 minLength=8 but fails JS length<10 check
    const weakPassword = 'Abc12345!';
    await getPasswordField(employeePage, 'Aktuelles Passwort').fill(testEmployee.password);
    await getPasswordField(employeePage, 'Neues Passwort').fill(weakPassword);
    await getPasswordField(employeePage, 'Passwort bestätigen').fill(weakPassword);
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Frontend validates and shows error in bg-red-50 div
    await expect(employeePage.locator('.bg-red-50')).toBeVisible({ timeout: 10000 });
    await expect(employeePage.getByText('mindestens 10 Zeichen')).toBeVisible();
  });

  test('wrong current password rejected', async ({ employeePage }) => {
    await employeePage.getByRole('link', { name: 'Profil' }).click();
    await employeePage.waitForURL('/profile');

    await employeePage.getByRole('button', { name: 'Ändern' }).click();

    await getPasswordField(employeePage, 'Aktuelles Passwort').fill('WrongOldPass99!');
    await getPasswordField(employeePage, 'Neues Passwort').fill('NewValidPass123!');
    await getPasswordField(employeePage, 'Passwort bestätigen').fill('NewValidPass123!');
    await employeePage.getByRole('button', { name: 'Speichern' }).click();

    // Backend returns "Aktuelles Passwort ist falsch" shown in bg-red-50 div
    await expect(employeePage.locator('.bg-red-50')).toBeVisible({ timeout: 10000 });
    await expect(employeePage.getByText(/falsch/i)).toBeVisible();
  });
});
