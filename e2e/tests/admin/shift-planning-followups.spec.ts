import { test, expect } from '../../fixtures/base.fixture';

/**
 * Schichtplanung follow-ups:
 *   #321 Tagesansicht (Woche/Tag toggle)
 *   #322 Schicht auf andere Wochentage kopieren (SlotDialog)
 *
 * #451: die mandantenweite Einstellung `shift_planning_enabled` wird NICHT
 * mehr hier geschaltet — siehe global-setup.ts.
 */
test.describe('Schichtplanung Follow-ups (#321/#322)', () => {
  const planName = `E2E-FU-Plan-${Date.now()}`;

  test.afterEach(async ({ adminApi }) => {
    const plans = await adminApi.get('/shift-planning/plans');
    for (const p of plans) if (p.name === planName) await adminApi.delete(`/shift-planning/plans/${p.id}`);
  });

  test('#321 day view toggle shows a single weekday', async ({ adminPage, adminApi }) => {
    await adminApi.post('/shift-planning/plans', { name: planName });
    await adminPage.goto('/admin/shift-planning');
    await adminPage.getByRole('button', { name: new RegExp(planName) }).click();
    await expect(adminPage.getByRole('heading', { name: planName })).toBeVisible({ timeout: 10000 });

    // switch to Tag → the weekday <select> appears
    await adminPage.getByRole('button', { name: 'Tag', exact: true }).click();
    const wdSelect = adminPage.locator('select').filter({ has: adminPage.locator('option', { hasText: 'Donnerstag' }) }).first();
    await expect(wdSelect).toBeVisible({ timeout: 5000 });
    await wdSelect.selectOption('3'); // Donnerstag
    // back to Woche
    await adminPage.getByRole('button', { name: 'Woche', exact: true }).click();
    await expect(wdSelect).toBeHidden();
  });

  test('#322 copy a slot to other weekdays', async ({ adminPage, adminApi }) => {
    const plan = await adminApi.post('/shift-planning/plans', { name: planName });
    const ws = await adminApi.post('/shift-planning/workstations', { name: `Tresen-${Date.now()}` });
    // a Monday slot to copy
    await adminApi.post(`/shift-planning/plans/${plan.id}/slots`, {
      workstation_id: ws.id, weekday: 0, start_time: '07:45', end_time: '13:30', min_staff: 1,
    });

    await adminPage.goto('/admin/shift-planning');
    await adminPage.getByRole('button', { name: new RegExp(planName) }).click();
    await expect(adminPage.getByRole('heading', { name: planName })).toBeVisible({ timeout: 10000 });

    // open the slot (click its block) → edit dialog
    await adminPage.getByText('07:45–13:30').first().click();
    const modal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Zeitslot bearbeiten' });
    await expect(modal).toBeVisible({ timeout: 10000 });

    // pick Tue + Wed in the copy section, then copy
    await modal.getByRole('button', { name: 'Di', exact: true }).click();
    await modal.getByRole('button', { name: 'Mi', exact: true }).click();
    const createResp = adminPage.waitForResponse(
      (r) => r.url().includes(`/api/shift-planning/plans/${plan.id}/slots`) && r.request().method() === 'POST',
    );
    await modal.getByRole('button', { name: /Auf 2 Tage kopieren/ }).click();
    await createResp;

    // the plan now has 3 slots (Mon + the 2 copies)
    await expect.poll(async () => {
      const detail = await adminApi.get(`/shift-planning/plans/${plan.id}`);
      return detail.slots.length;
    }, { timeout: 10000 }).toBe(3);
  });
});
