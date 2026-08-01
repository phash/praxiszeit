import { test, expect } from '../../fixtures/base.fixture';
import { weekdayFromNow } from '../../helpers/date.helper';

test.describe('Admin Vacation Approvals', () => {
  // Mehrere Tests hier schalten die Genehmigungspflicht ein. Bricht einer
  // vorzeitig ab, bliebe sie an und veränderte das Verhalten aller folgenden
  // Specs (Urlaub direkt buchen → 400). Das Zurücksetzen gehört deshalb in ein
  // afterEach und nicht ans Ende des Erfolgspfads — genau die Lücke, die die
  // entfernten `catch { test.skip() }` bisher verdeckt haben.
  test.afterEach(async ({ adminApi }) => {
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' });
    } catch { /* best effort */ }
  });

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

  // Dieser Test lief bis hierher NIE: er buchte den Urlaub direkt über
  // ``POST /absences`` — was die Anwendung bei aktiver Genehmigungspflicht seit
  // MA-ABS-01 bewusst mit 400 ablehnt (sonst ließe sich die Genehmigung über
  // die API umgehen). Der `catch { test.skip() }` schluckte genau diese 400,
  // der Test wurde übersprungen (er war das eine „skipped" im Gesamtlauf), und
  // die Zusicherung dahinter war zudem tautologisch
  // (`if (hasRequest) expect(requestCard).toBeVisible()`).
  //
  // Jetzt prüft er die zwei Aussagen, die dahinter stehen: (1) der
  // Direktbuchungs-Weg ist bei Genehmigungspflicht für MA gesperrt, (2) der
  // richtige Weg (Antrag) landet sichtbar in der offenen Warteschlange.
  test('employee vacation request shows as pending', async ({
    adminPage,
    adminApi,
    employeeApi,
    testEmployee,
    createVacationRequest,
  }) => {
    await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });

    try {
      // (1) Direktbuchung muss abgelehnt werden (kein Approval-Bypass)
      await expect(
        employeeApi.post('/absences', {
          date: weekdayFromNow(30),
          type: 'vacation',
          hours: 8,
          note: 'E2E direct-booking bypass probe',
        })
      ).rejects.toThrow(/400/);

      // (2) Der richtige Weg: Antrag stellen → erscheint unter "Offen"
      const uniqueNote = `E2E pending ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await createVacationRequest({
        date: weekdayFromNow(30),
        hours: 8,
        note: uniqueNote,
      });

      await adminPage.goto('/admin/vacation-approvals');
      await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();

      await adminPage.getByRole('button', { name: 'Offen' }).click();
      await adminPage.waitForLoadState('networkidle');

      const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueNote }).last();
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card).toContainText(testEmployee.last_name);
    } finally {
      // Zurückschalten übernimmt das afterEach.
    }
  });

  test('approve vacation request', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    // Enable approval requirement. Kein `catch { test.skip() }` mehr: schlägt
    // das Setzen der Einstellung fehl, ist das ein Fehler und kein Grund, den
    // Test lautlos zu überspringen.
    await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });

    // Create the request via the fixture so the teardown deletes the row
    // (or withdraws it if the test runs the approve step). Unique note marker
    // disambiguates THIS request from any leftover pending entries that
    // share the employee's last_name. weekdayFromNow ensures Mon-Fri so the
    // approve path doesn't bail out with "Keine gültigen Arbeitstage im Zeitraum".
    const futureDate = weekdayFromNow(35);
    const uniqueNote = `E2E approve ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createVacationRequest({
      date: futureDate,
      hours: 8,
      note: uniqueNote,
    });

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

  });

  test('reject vacation request with reason', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    // Enable approval requirement. Kein `catch { test.skip() }` mehr: schlägt
    // das Setzen der Einstellung fehl, ist das ein Fehler und kein Grund, den
    // Test lautlos zu überspringen.
    await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });

    // Create via fixture so teardown deletes the rejected request row.
    // Unique note marker for disambiguation; weekdayFromNow for valid workdays.
    const futureDate = weekdayFromNow(40);
    const uniqueNote = `E2E reject ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createVacationRequest({
      date: futureDate,
      hours: 8,
      note: uniqueNote,
    });

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

  });

  test('admin edits pending vacation request — note + date', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });

    const startDate = weekdayFromNow(45);
    const newDate = weekdayFromNow(50);
    const uniqueNote = `E2E admin-edit ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const newNote = `${uniqueNote} edited`;
    await createVacationRequest({
      date: startDate,
      hours: 8,
      note: uniqueNote,
    });

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Bearbeiten' }).click();

    // Modal opens
    const dialog = adminPage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Change date + note
    await dialog.locator('input[type="date"]').first().fill(newDate);
    const noteInput = dialog.locator('input[type="text"]').first();
    await noteInput.fill(newNote);
    await dialog.getByRole('button', { name: 'Speichern' }).click();

    // Toast confirms
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /aktualisiert/ })
    ).toBeVisible({ timeout: 10000 });

    // Card should reflect the new note
    await adminPage.waitForLoadState('networkidle');
    const updated = adminPage.locator('div.bg-white').filter({ hasText: 'edited' }).first();
    await expect(updated).toBeVisible({ timeout: 5000 });

  });
});
