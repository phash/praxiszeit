import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Einstellungen', () => {
  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/admin/settings');
    await expect(adminPage.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();
  });

  test('zeigt Bundesland-Dropdown mit allen Optionen', async ({ adminPage }) => {
    const select = adminPage.locator('#holiday-state');
    await expect(select).toBeVisible();
    // 16 Bundesländer müssen geladen sein (holiday_service.SUPPORTED_STATES)
    const options = select.locator('option');
    await expect(options).toHaveCount(16);
    // Bayern muss enthalten sein
    await expect(select.locator('option[value="Bayern"]')).toBeAttached();
  });

  test('speichert Bundesland und zeigt Erfolgstoast', async ({ adminPage, adminApi }) => {
    const select = adminPage.locator('#holiday-state');
    await expect(select).toBeVisible();
    const currentValue = await select.inputValue();
    const newValue = currentValue === 'Bayern' ? 'Berlin' : 'Bayern';
    await select.selectOption(newValue);
    // Erster Speichern-Button (Bundesland)
    const saveBtn = adminPage.locator('button', { hasText: 'Speichern' }).first();
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'Bundesland aktualisiert' })
    ).toBeVisible({ timeout: 15000 });
    // Cleanup
    try {
      await adminApi.put('/admin/settings/holiday_state', { value: currentValue });
    } catch { /* best effort */ }
  });

  test('Speichern-Button ist disabled wenn Wert unveraendert', async ({ adminPage }) => {
    const saveBtn = adminPage.locator('button', { hasText: 'Speichern' }).first();
    await expect(saveBtn).toBeDisabled();
  });

  test('Urlaubsgenehmigung-Toggle speichert Einstellung', async ({ adminPage, adminApi }) => {
    // #144 added a second role="switch" (Pflicht-Pause-Ausnahme) and a second
    // "Speichern" button, so the page-wide `button[role="switch"]` and
    // `Speichern.last()` locators became ambiguous (strict-mode violation /
    // wrong button — the .last() Speichern is now the break-approval one).
    // Target the unique toggle id and scope the save button to this section.
    const section = adminPage.locator('div.bg-white').filter({
      has: adminPage.getByRole('heading', { name: 'Urlaubsgenehmigung', exact: true }),
    });
    const toggle = adminPage.locator('#approval-toggle');
    await expect(toggle).toBeVisible();
    const isChecked = await toggle.getAttribute('aria-checked');
    await toggle.click();
    const saveApprovalBtn = section.getByRole('button', { name: 'Speichern' });
    await expect(saveApprovalBtn).toBeEnabled();
    await saveApprovalBtn.click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'Urlaubsgenehmigung' })
    ).toBeVisible({ timeout: 10000 });
    // Cleanup: Originalzustand wiederherstellen
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', {
        value: isChecked === 'true' ? 'true' : 'false',
      });
    } catch { /* best effort */ }
  });
});
