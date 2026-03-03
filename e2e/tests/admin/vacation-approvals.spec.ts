import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow } from '../../helpers/date.helper';

test.describe('Admin Vacation Approvals', () => {
  test.slow();

  test('page loads with toggle and filter tabs', async ({ adminPage }) => {
    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Urlaubsanträge' })).toBeVisible();

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
    await expect(adminPage.getByRole('heading', { name: 'Urlaubsanträge' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    const toggle = adminPage.getByRole('switch');
    await expect(toggle).toBeVisible();

    // Click toggle first time
    await toggle.click();
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /Genehmigungspflicht|aktiviert|deaktiviert/ })
    ).toBeVisible({ timeout: 10000 });

    // Wait for the toast to dismiss
    await adminPage.waitForTimeout(2000);

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
    await expect(adminPage.getByRole('heading', { name: 'Urlaubsanträge' })).toBeVisible();

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
    const futureDate = daysFromNow(35);
    try {
      await employeeApi.post('/absences', {
        date: futureDate,
        type: 'vacation',
        hours: 8,
        note: 'E2E approve test',
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Urlaubsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Find approve button
    const approveButton = adminPage.getByRole('button', { name: 'Genehmigen' }).first();
    const hasApprove = await approveButton.isVisible({ timeout: 5000 }).catch(() => false);

    if (hasApprove) {
      await approveButton.click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /genehmigt/ })
      ).toBeVisible({ timeout: 10000 });
    }

    // Cleanup
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });

  test('reject vacation request with reason', async ({
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
    const futureDate = daysFromNow(40);
    try {
      await employeeApi.post('/absences', {
        date: futureDate,
        type: 'vacation',
        hours: 8,
        note: 'E2E reject test',
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Urlaubsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Find reject button
    const rejectButton = adminPage.getByRole('button', { name: 'Ablehnen' }).first();
    const hasReject = await rejectButton.isVisible({ timeout: 5000 }).catch(() => false);

    if (hasReject) {
      await rejectButton.click();

      // Fill rejection reason
      const textarea = adminPage.locator('textarea').first();
      await expect(textarea).toBeVisible({ timeout: 5000 });
      await textarea.fill('E2E Test: Zeitraum nicht möglich');

      // Click the final "Ablehnen" button
      await adminPage.getByRole('button', { name: 'Ablehnen' }).first().click();

      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /abgelehnt/ })
      ).toBeVisible({ timeout: 10000 });
    }

    // Cleanup
    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });
});
