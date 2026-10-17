import { test, expect } from '../../fixtures/base.fixture';

// Gesamtreview 1.20 (B9): diese Spec schaltet mandantenweite Einstellungen um —
// das Bundesland (`holiday_state`, löscht und erzeugt dabei die Feiertage des
// Mandanten neu) und die Genehmigungspflicht (`vacation_approval_required`).
// Bei `workers: 2` lief das neben Specs, die Urlaub buchen oder beantragen und
// mit Feiertagen rechnen. Sie liegt deshalb in tests/tenant-settings/ und läuft
// im Projekt "tenant-settings" erst nach "chromium", einzeln nacheinander
// (playwright.config.ts). Die Genehmigungspflicht steht dabei auf dem Wert aus
// global-setup.ts (`false`).
//
// Beide Umschalt-Tests lesen den Ausgangswert vor dem Umschalten über die API
// und schreiben ihn im `finally` zurück, auch wenn eine Zusicherung fehlschlägt.
// Vorher stand das Zurückschreiben am Ende des Erfolgswegs: blieb der Toast aus,
// stand die Instanz auf Berlin, die Wiederholung las „Berlin" als Ausgangswert,
// schaltete auf Bayern und „räumte" wieder auf Berlin auf — `holiday_state`
// setzt kein globaler Teardown zurück (nicht in OWNED_SETTINGS), die folgenden
// Läufe rechneten mit Berliner Feiertagen.
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
    // Wirksamer Ausgangswert (auch ohne gespeicherte Einstellung) — derselbe
    // Endpunkt, aus dem die Seite ihre Auswahl vorbelegt.
    const original: string = (await adminApi.get('/holidays/states')).current_state;
    const newValue = original === 'Bayern' ? 'Berlin' : 'Bayern';
    try {
      const select = adminPage.locator('#holiday-state');
      await expect(select).toBeVisible();
      await expect(select).toHaveValue(original);
      await select.selectOption(newValue);
      // Erster Speichern-Button (Bundesland)
      const saveBtn = adminPage.locator('button', { hasText: 'Speichern' }).first();
      await expect(saveBtn).toBeEnabled();
      await saveBtn.click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'Bundesland aktualisiert' })
      ).toBeVisible({ timeout: 15000 });
    } finally {
      await adminApi.put('/admin/settings/holiday_state', { value: original }).catch(() => {});
    }
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
    // Ausgangswert über die API (ohne gespeicherte Zeile gilt „aus").
    const settings = await adminApi.get('/admin/settings');
    const original =
      String(settings.find((s: any) => s.key === 'vacation_approval_required')?.value).toLowerCase() === 'true'
        ? 'true'
        : 'false';
    try {
      const toggle = adminPage.locator('#approval-toggle');
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('aria-checked', original);
      await toggle.click();
      const saveApprovalBtn = section.getByRole('button', { name: 'Speichern' });
      await expect(saveApprovalBtn).toBeEnabled();
      await saveApprovalBtn.click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'Urlaubsgenehmigung' })
      ).toBeVisible({ timeout: 10000 });
    } finally {
      await adminApi
        .put('/admin/settings/vacation_approval_required', { value: original })
        .catch(() => {});
    }
  });
});
