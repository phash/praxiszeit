import { test, expect } from '../../fixtures/base.fixture';

/**
 * Schichtplanung (#305) — admin dialog-path E2E.
 *
 * Exercises the robust (non-drag) path: enable the feature flag, create a
 * workstation + plan, add a slot and assign the employee via the dialog,
 * activate the plan, and verify the read-only employee view shows it.
 * Drag & drop is intentionally NOT simulated (flaky); the dialog path covers
 * the same mutations through the same API.
 */
test.describe('Schichtplanung (#305)', () => {
  const unique = `${Date.now()}`;
  const wsName = `E2E-Tresen-${unique}`;
  const planName = `E2E-Plan-${unique}`;

  test.afterAll(async ({ adminApi }) => {
    // Best-effort cleanup + turn the feature back off.
    try {
      const plans = await adminApi.get('/shift-planning/plans');
      for (const p of plans) if (p.name === planName) await adminApi.delete(`/shift-planning/plans/${p.id}`);
      const ws = await adminApi.get('/shift-planning/workstations');
      for (const w of ws) if (w.name === wsName) await adminApi.delete(`/shift-planning/workstations/${w.id}`);
    } catch {
      /* ignore */
    }
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'false' });
  });

  test('admin creates plan + slot + assignment, activates, employee sees it', async ({
    adminPage,
    adminApi,
    testEmployee,
  }) => {
    // 1. Enable the feature for the tenant.
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'true' });

    // 2. Stammdaten: create a workstation.
    await adminPage.goto('/admin/shift-planning');
    await expect(adminPage.getByRole('heading', { name: 'Schichtplanung' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Stammdaten' }).click();

    const main = adminPage.locator('main');
    // Scope to the "Arbeitsplätze" card via its heading — the "Standorte" card
    // both has a "Hinzufügen" button AND mentions "Arbeitsplätze" in its empty
    // state, so text-based scoping is ambiguous; the heading is unique.
    const wsCard = main
      .locator('div.bg-white')
      .filter({ has: adminPage.getByRole('heading', { name: 'Arbeitsplätze', exact: true }) });
    await wsCard.getByLabel('Name').fill(wsName);
    const wsCreate = adminPage.waitForResponse(
      (r) => r.url().includes('/api/shift-planning/workstations') && r.request().method() === 'POST',
    );
    await wsCard.getByRole('button', { name: 'Hinzufügen' }).click();
    await wsCreate;
    await expect(wsCard.getByText(wsName)).toBeVisible();

    // 3. Schichtpläne: create a plan.
    await adminPage.getByRole('button', { name: 'Schichtpläne' }).click();
    await main.getByLabel('Neuer Plan').fill(planName);
    const planCreate = adminPage.waitForResponse(
      (r) => r.url().endsWith('/api/shift-planning/plans') && r.request().method() === 'POST',
    );
    await adminPage.getByRole('button', { name: 'Plan anlegen' }).click();
    await planCreate;

    // Plan auto-selects after creation → editor heading shows the plan name.
    await expect(adminPage.getByRole('heading', { name: planName })).toBeVisible();

    // 4. Add a slot via the dialog and assign the employee.
    await adminPage.getByRole('button', { name: 'Slot', exact: true }).click();
    // Scope to the modal — the employee name also appears in the sidebar list,
    // and other "Speichern" buttons can exist elsewhere on the page.
    const modal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Neuer Zeitslot' });
    await expect(modal.getByRole('heading', { name: 'Neuer Zeitslot' })).toBeVisible();

    await modal.getByLabel('Arbeitsplatz').selectOption({ label: wsName });
    await modal.getByLabel('Von').fill('08:00');
    await modal.getByLabel('Bis').fill('12:00');
    // Assign the employee via the checklist (inside the modal).
    //
    // Wortgrenze, nicht Teilstring: `testUserCounter` in der Fixture ist ein
    // prozesslokaler Zähler, jeder Playwright-Worker vergibt also parallel
    // "Test User1", "Test User2", … Der Dialog listet ALLE Mitarbeitenden,
    // auch die gerade nebenher angelegten — `getByText('Test User1')` traf
    // damit zusätzlich "Test User13" und scheiterte an der Eindeutigkeit.
    // Der Eintrag trägt hinter dem Namen noch das Einweisungs-Kennzeichen
    // ("… nicht eingewiesen"), deshalb `\b` statt `exact: true`.
    const employeeLabel = new RegExp(
      `${testEmployee.first_name} ${testEmployee.last_name}\\b`
    );
    await modal.getByText(employeeLabel).click();

    const slotCreate = adminPage.waitForResponse(
      (r) => r.url().includes('/api/shift-planning/plans/') && r.url().includes('/slots') && r.request().method() === 'POST',
    );
    await modal.getByRole('button', { name: 'Speichern' }).click();
    await slotCreate;

    // Slot block now visible in the grid with the workstation name + time.
    await expect(main.getByText(wsName).first()).toBeVisible();
    await expect(main.getByText('08:00–12:00').first()).toBeVisible();

    // 5. Activate the plan.
    const activate = adminPage.waitForResponse(
      (r) => r.url().includes('/activate') && r.request().method() === 'POST',
    );
    await adminPage.getByRole('button', { name: 'Aktiv schalten' }).click();
    await activate;
    await expect(adminPage.getByRole('button', { name: 'Deaktivieren' })).toBeVisible();

    // 6. Read-only employee-facing view shows the active plan.
    await adminPage.goto('/shift-planning');
    await expect(adminPage.getByRole('heading', { name: 'Schichtplan' })).toBeVisible();
    await expect(adminPage.locator('main').getByText(planName)).toBeVisible();
    await expect(adminPage.locator('main').getByText(wsName).first()).toBeVisible();
  });

  test('feature hidden + endpoints 404 when flag is off', async ({ adminPage, adminApi }) => {
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'false' });

    // API gate: 404 when off.
    const res = await adminApi.getRaw('/shift-planning/plans');
    expect(res.status).toBe(404);

    // Nav entry hidden after reload.
    await adminPage.goto('/');
    await adminPage.reload();
    await expect(adminPage.getByRole('link', { name: 'Schichtplanung' })).toHaveCount(0);
  });
});
