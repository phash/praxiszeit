import { test, expect } from '../../fixtures/base.fixture';

/**
 * UI coverage for the 1.8.0-beta prod-release features that previously had no
 * e2e spec (#189 Betriebsferien-Flag, #191 Stundenzählung-Toggle,
 * #194 Überstunden-Übersicht, #201 Soll-Arbeitszeit-Fenster + Puffer).
 *
 * Each test drives the real admin UI and verifies persistence through the API,
 * then cleans up after itself.
 */
test.describe('Prod-Release-Features (Admin UI)', () => {
  async function openNewUserForm(adminPage: any) {
    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Neue:r Mitarbeiter:in' }).click();
  }

  async function fillRequired(adminPage: any, username: string) {
    await adminPage.locator('#f-username').fill(username);
    await adminPage.locator('#f-firstname').fill('E2E');
    await adminPage.locator('#f-lastname').fill('Feature');
    await adminPage.locator('#f-password').fill('TestPass123!');
    await adminPage.locator('#f-weekly-hours').fill('40');
    await adminPage.locator('#f-vacation').fill('30');
  }

  async function cleanup(adminApi: any, username: string) {
    try {
      const users = await adminApi.get('/admin/users?include_inactive=true');
      const u = users.find((x: any) => x.username === username);
      if (u) await adminApi.delete(`/admin/users/${u.id}`);
    } catch { /* best effort */ }
  }

  test('#201 + #189: Soll-Arbeitszeit-Fenster und Betriebsferien-Flag werden gespeichert', async ({ adminPage, adminApi }) => {
    const username = `e2e_ww_${Date.now()}`;
    try {
      await openNewUserForm(adminPage);
      await fillRequired(adminPage, username);

      // #201: Soll-Beginn/-Ende für Montag setzen
      await adminPage.getByLabel('Soll-Beginn Mo').fill('09:00');
      await adminPage.getByLabel('Soll-Ende Mo').fill('17:00');

      // #189: Teilnahme an Betriebsferien abwählen
      await adminPage.locator('#receives_company_closures').uncheck();

      await adminPage.getByRole('button', { name: 'Speichern' }).click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })
      ).toBeVisible({ timeout: 10000 });

      // Persistenz über die API verifizieren
      const users = await adminApi.get('/admin/users?include_inactive=true');
      const created = users.find((u: any) => u.username === username);
      expect(created, 'created user should exist').toBeTruthy();
      expect(created.scheduled_start_monday).toMatch(/^09:00/);
      expect(created.scheduled_end_monday).toMatch(/^17:00/);
      expect(created.receives_company_closures).toBe(false);
    } finally {
      await cleanup(adminApi, username);
    }
  });

  test('#191 + #194: MA ohne Stundenzählung erscheint mit „—" in der Überstunden-Übersicht', async ({ adminPage, adminApi }) => {
    const username = `e2e_untracked_${Date.now()}`;
    try {
      await openNewUserForm(adminPage);
      await fillRequired(adminPage, username);

      // #191: Stundenzählung deaktivieren
      await adminPage.locator('#track_hours').uncheck();

      await adminPage.getByRole('button', { name: 'Speichern' }).click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })
      ).toBeVisible({ timeout: 10000 });

      // track_hours=false persistiert?
      const users = await adminApi.get('/admin/users?include_inactive=true');
      const created = users.find((u: any) => u.username === username);
      expect(created, 'created user should exist').toBeTruthy();
      expect(created.track_hours).toBe(false);

      // #194: Übersicht zeigt die Überstunden-Spalte; untracked MA → „—"
      await adminPage.goto('/admin/users');
      await expect(adminPage.getByRole('columnheader', { name: 'Überstunden (JTD)' })).toBeVisible();
      const row = adminPage.locator('tr', { hasText: username });
      await expect(row).toBeVisible({ timeout: 10000 });
      await expect(row.getByTitle('Keine Stundenzählung')).toBeVisible();
    } finally {
      await cleanup(adminApi, username);
    }
  });

  test('#201: Soll-Fenster-Puffer lässt sich in den Einstellungen speichern', async ({ adminPage, adminApi }) => {
    // Originalwert merken, um ihn am Ende wiederherzustellen
    let original = '15';
    try {
      const settings = await adminApi.get('/admin/settings');
      const grace = settings.find((s: any) => s.key === 'work_window_grace_minutes');
      if (grace?.value) original = String(grace.value);
    } catch { /* default 15 */ }

    const newValue = original === '20' ? '25' : '20';
    try {
      await adminPage.goto('/admin/settings');
      await expect(adminPage.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();

      const input = adminPage.locator('#grace-minutes');
      await expect(input).toBeVisible();
      await input.fill(newValue);
      // Scope to the "Soll-Arbeitszeit-Fenster" section — every settings card
      // has its own "Speichern" button.
      const graceSection = adminPage.locator('div.bg-white', {
        has: adminPage.getByRole('heading', { name: 'Soll-Arbeitszeit-Fenster' }),
      });
      await graceSection.getByRole('button', { name: 'Speichern' }).click();

      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'Puffer gespeichert' })
      ).toBeVisible({ timeout: 10000 });

      const after = await adminApi.get('/admin/settings');
      const grace = after.find((s: any) => s.key === 'work_window_grace_minutes');
      expect(String(grace.value)).toBe(newValue);
    } finally {
      // Originalwert zurückschreiben
      try {
        await adminApi.put('/admin/settings/work_window_grace_minutes', { value: original });
      } catch { /* best effort */ }
    }
  });
});
