import { test, expect } from '../../fixtures/base.fixture';

/**
 * #305 M2 — KW-/Ganzjahres-Planung (Datums-Fenster, PlanSettingsDialog) +
 * Auto-Generierung (GenerateDialog). Exercises the new M2 UI wiring on a live
 * plan; the greedy generator itself is covered by backend unit tests.
 *
 * #451: die mandantenweite Einstellung `shift_planning_enabled` wird NICHT
 * mehr hier geschaltet — siehe global-setup.ts.
 */
test.describe('Schichtplanung M2 (#305)', () => {
  const planName = `E2E-M2-Plan-${Date.now()}`;

  test.afterEach(async ({ adminApi }) => {
    const plans = await adminApi.get('/shift-planning/plans');
    for (const p of plans) if (p.name === planName) await adminApi.delete(`/shift-planning/plans/${p.id}`);
  });

  test('set an active date window via Bearbeiten + open Automatisch füllen', async ({ adminPage, adminApi }) => {
    // seed a plan via API (the create UI is covered elsewhere)
    const plan = await adminApi.post('/shift-planning/plans', { name: planName });

    await adminPage.goto('/admin/shift-planning');
    // select the plan in the list
    await adminPage.getByRole('button', { name: new RegExp(planName) }).click();
    await expect(adminPage.getByRole('heading', { name: planName })).toBeVisible({ timeout: 10000 });

    // ── KW-Planung: Bearbeiten → set active von/bis → Speichern ──
    await adminPage.getByRole('button', { name: 'Bearbeiten' }).click();
    const settingsModal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Plan-Einstellungen' });
    await expect(settingsModal).toBeVisible({ timeout: 10000 });
    const dateInputs = settingsModal.locator('input[type="date"]');
    await dateInputs.nth(0).fill('2026-07-01');
    await dateInputs.nth(1).fill('2026-08-31');
    const putResp = adminPage.waitForResponse(
      (r) => r.url().includes(`/api/shift-planning/plans/${plan.id}`) && r.request().method() === 'PUT',
    );
    await settingsModal.getByRole('button', { name: 'Speichern' }).click();
    expect((await putResp).ok()).toBeTruthy();
    // the window is now shown in the editor header
    await expect(adminPage.getByText(/Automatisch aktiv ab 2026-07-01 bis 2026-08-31/)).toBeVisible({ timeout: 10000 });

    // ── Auto-Generierung: Automatisch füllen → dialog → Generieren ──
    await adminPage.getByRole('button', { name: 'Automatisch füllen' }).click();
    const genModal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Zielwoche' });
    await expect(genModal).toBeVisible({ timeout: 10000 });
    const genResp = adminPage.waitForResponse(
      (r) => r.url().includes(`/api/shift-planning/plans/${plan.id}/generate`) && r.request().method() === 'POST',
    );
    await genModal.getByRole('button', { name: 'Generieren' }).click();
    expect((await genResp).ok()).toBeTruthy();
  });
});
