import { test, expect } from '../../fixtures/base.fixture';

/**
 * E2E coverage for the 2026-06 feature batch:
 *   #311 Monatsjournal heading shows employee name
 *   #312 eigene Abwesenheitsgründe (Settings CRUD + booking picker)
 *   #313 Monatssaldo „bis heute / Monatsende" toggle (Admin-Dashboard)
 *
 * Der #314-Schalter (Betriebsferien-Überstundenabbau) ist eine mandantenweite
 * Einstellung und liegt deshalb in
 * tests/tenant-settings/closure-overtime-setting.spec.ts (Gesamtreview 1.20 B9).
 */

test.describe('#312 Eigene Abwesenheitsgründe', () => {
  test('create a custom reason in Settings and see it in the list + booking picker', async ({ adminPage, testEmployee }) => {
    const name = `E2E-Schule-${Date.now()}`;
    await adminPage.goto('/admin/settings');
    await expect(adminPage.getByRole('heading', { name: 'Eigene Abwesenheitsgründe' })).toBeVisible();

    // fill the create form (scoped to the reasons section)
    const section = adminPage.locator('div', { has: adminPage.getByRole('heading', { name: 'Eigene Abwesenheitsgründe' }) }).last();
    await section.getByPlaceholder('z. B. Schule').fill(name);
    // behaviour select defaults to "Zählt als gearbeitet" (worked)

    const createResp = adminPage.waitForResponse(
      (r) => r.url().includes('/api/admin/absence-reasons') && r.request().method() === 'POST',
    );
    await section.getByRole('button', { name: 'Hinzufügen' }).click();
    await createResp;

    // the new reason appears in the list (an <input> carrying its name)
    await expect(adminPage.locator(`input[value="${name}"]`)).toBeVisible({ timeout: 10000 });

    // and it shows up in the absence booking picker (AdminAbsences) as a custom reason
    await adminPage.goto('/admin/absences');
    const empSelect = adminPage.getByTestId('absence-employee-filter');
    const opt = empSelect.locator('option', { hasText: testEmployee.last_name });
    await expect(opt.first()).toBeAttached({ timeout: 10000 });
    await empSelect.selectOption((await opt.first().getAttribute('value'))!);
    await adminPage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();
    // the type <select> now contains an "Eigene Gründe" optgroup with our reason
    const typeSelect = adminPage.locator('select').filter({ has: adminPage.locator('option[value="vacation"]') }).first();
    await expect(typeSelect.locator('option', { hasText: name })).toBeAttached({ timeout: 10000 });
  });
});

test.describe('#313 Monatssaldo Soll-Basis-Umschalter', () => {
  test('admin dashboard re-fetches the report with soll_basis=monatsende', async ({ adminPage }) => {
    await adminPage.goto('/admin');
    // the "Soll:" select in the Monatsübersicht header
    const sollSelect = adminPage.locator('select').filter({ has: adminPage.locator('option[value="monatsende"]') }).first();
    await expect(sollSelect).toBeVisible({ timeout: 15000 });
    const resp = adminPage.waitForResponse(
      (r) => r.url().includes('/api/admin/reports/monthly') && r.url().includes('soll_basis=monatsende'),
    );
    await sollSelect.selectOption('monatsende');
    expect((await resp).ok()).toBeTruthy();
  });
});

test.describe('#311 Monatsjournal-Überschrift', () => {
  test('admin user journal heading includes the employee name', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    // "Monatsjournal: Vorname Nachname"
    await expect(
      adminPage.getByRole('heading', { name: new RegExp(`Monatsjournal:\\s*${testEmployee.first_name}\\s+${testEmployee.last_name}`) }),
    ).toBeVisible({ timeout: 10000 });
  });
});
