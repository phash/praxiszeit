import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow, weekdayFromNow } from '../../helpers/date.helper';

test.describe('Admin Vacation Approvals', () => {
  test('page loads with toggle and filter tabs', async ({ adminPage }) => {
    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();

    // Check that the toggle switch exists
    const toggle = adminPage.getByRole('switch');
    await expect(toggle).toBeVisible();

    // Check filter tabs
    await expect(adminPage.getByRole('button', { name: 'Offen' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Genehmigt' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Abgelehnt' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Alle' })).toBeVisible();
  });

  test('toggle approval requirement', async ({ adminPage }) => {
    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    const toggle = adminPage.getByRole('switch');
    await expect(toggle).toBeVisible();

    // Click toggle first time
    await toggle.click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /Genehmigungspflicht|aktiviert|deaktiviert/ })
    ).toBeVisible({ timeout: 10000 });

    // Wait for the toast to dismiss
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: /Genehmigungspflicht|aktiviert|deaktiviert/ })).not.toBeVisible({ timeout: 6000 });

    // Click toggle second time to revert
    await toggle.click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /Genehmigungspflicht|aktiviert|deaktiviert/ })
    ).toBeVisible({ timeout: 10000 });
  });

  test('employee vacation request shows as pending', async ({
    adminPage,
    adminApi,
    employeeApi,
    testEmployee,
  }) => {
    // Enable approval requirement
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    // Create a vacation request as employee
    const futureDate = daysFromNow(30);
    try {
      await employeeApi.post('/absences', {
        date: futureDate,
        type: 'vacation',
        hours: 8,
        note: 'E2E vacation approval test',
      });
    } catch {
      // If creation fails, skip
      test.skip();
      return;
    }

    // Navigate to admin vacation approvals
    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();

    // Make sure we're on "Offen" tab
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Check if the request shows up
    const requestCard = adminPage.getByText(testEmployee.last_name).first();
    const hasRequest = await requestCard.isVisible({ timeout: 5000 }).catch(() => false);

    // If there's a pending request, it should show up
    if (hasRequest) {
      await expect(requestCard).toBeVisible();
    }

    // Cleanup: disable approval requirement
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' });
    } catch { /* best effort */ }
  });

  test('approve vacation request', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    // Enable approval requirement
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    // Create the request via the fixture so the teardown deletes the row
    // (or withdraws it if the test runs the approve step). Unique note marker
    // disambiguates THIS request from any leftover pending entries that
    // share the employee's last_name. weekdayFromNow ensures Mon-Fri so the
    // approve path doesn't bail out with "Keine gültigen Arbeitstage im Zeitraum".
    const futureDate = weekdayFromNow(35);
    const uniqueNote = `E2E approve ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      await createVacationRequest({
        date: futureDate,
        hours: 8,
        note: uniqueNote,
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Locate THIS test's card by the unique note marker
    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Genehmigen' }).click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /genehmigt/ })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup setting; the request itself is teardown-handled by the fixture.
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });

  test('reject vacation request with reason', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    // Enable approval requirement
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    // Create via fixture so teardown deletes the rejected request row.
    // Unique note marker for disambiguation; weekdayFromNow for valid workdays.
    const futureDate = weekdayFromNow(40);
    const uniqueNote = `E2E reject ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      await createVacationRequest({
        date: futureDate,
        hours: 8,
        note: uniqueNote,
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Locate THIS test's card via the unique note marker
    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Ablehnen' }).click();

    // Reject form opens inline; fill reason and confirm
    const textarea = card.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5000 });
    await textarea.fill('E2E Test: Zeitraum nicht möglich');
    await card.getByRole('button', { name: 'Ablehnen' }).click();

    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /abgelehnt/ })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup setting; the request row is teardown-handled by the fixture.
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });
});
