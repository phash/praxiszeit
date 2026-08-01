import { test, expect } from '../../fixtures/base.fixture';
import { daysAgo } from '../../helpers/date.helper';

test.describe('Admin Change Requests', () => {
  test('shows filter tabs', async ({ adminPage }) => {
    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();

    // Check all 4 filter buttons
    await expect(adminPage.getByRole('button', { name: 'Offen' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Genehmigt' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Abgelehnt' })).toBeVisible();
    await expect(adminPage.getByRole('button', { name: 'Alle' })).toBeVisible();
  });

  // Genehmigen/Ablehnen sind die beiden Pfade, auf denen ein Antrag echte
  // Daten verändert — und beide steckten in einer verschluckten
  // Sichtbarkeitsabfrage ohne else-Zweig: verschwand der Knopf, war der Test
  // grün. Dazu kam ein `try { … } catch { test.skip() }` um das Anlegen des
  // Antrags („Backend enum issue may prevent creation"), das einen kaputten
  // Antragspfad in ein stilles Überspringen verwandelt hätte. Beides ist fort;
  // die Karte wird über einen eindeutigen Begründungs-Marker adressiert, damit
  // `.first()` keinen Rest-Antrag aus einem früheren Lauf trifft.
  test('approve change request', async ({
    adminPage,
    testEmployee,
    createTimeEntry,
    createChangeRequest,
  }) => {
    // Create a past entry (locked)
    const pastDate = daysAgo(14);
    const entry = await createTimeEntry(testEmployee.id, {
      date: pastDate,
      start_time: '09:00',
      end_time: '17:00',
      break_minutes: 30,
    });

    // Create a change request via employee API
    const uniqueReason = `E2E approve ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createChangeRequest({
      request_type: 'update',
      time_entry_id: entry.id,
      proposed_date: pastDate,
      proposed_start_time: '09:00',
      proposed_end_time: '18:00',
      proposed_break_minutes: 30,
      proposed_note: '',
      reason: uniqueReason,
    });

    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Make sure we're on "Offen" tab
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Genau die Karte DIESES Antrags
    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueReason }).last();
    await expect(card).toBeVisible({ timeout: 10000 });
    await card.getByRole('button', { name: 'Genehmigen' }).click();

    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /genehmigt/ })
    ).toBeVisible({ timeout: 10000 });

    // Und der Antrag ist danach nicht mehr offen.
    await expect(card).toHaveCount(0, { timeout: 10000 });
  });

  test('reject change request with reason', async ({
    adminPage,
    testEmployee,
    createTimeEntry,
    createChangeRequest,
  }) => {
    // Create a past entry (locked)
    const pastDate = daysAgo(14);
    const entry = await createTimeEntry(testEmployee.id, {
      date: pastDate,
      start_time: '08:00',
      end_time: '16:00',
      break_minutes: 30,
    });

    // Create a change request via employee API
    const uniqueReason = `E2E reject ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await createChangeRequest({
      request_type: 'update',
      time_entry_id: entry.id,
      proposed_date: pastDate,
      proposed_start_time: '08:00',
      proposed_end_time: '17:00',
      proposed_break_minutes: 45,
      proposed_note: '',
      reason: uniqueReason,
    });

    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    // Genau die Karte DIESES Antrags
    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueReason }).last();
    await expect(card).toBeVisible({ timeout: 10000 });
    await card.getByRole('button', { name: 'Ablehnen' }).click();

    // Fill rejection reason (Formular klappt in derselben Karte auf)
    const textarea = card.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5000 });
    await textarea.fill('E2E Test: Ablehnung mit Begründung');

    // Click the "Ablehnen" button in the expanded area
    await card.getByRole('button', { name: 'Ablehnen' }).click();

    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /abgelehnt/ })
    ).toBeVisible({ timeout: 10000 });

    // Und der Antrag ist danach nicht mehr offen.
    await expect(card).toHaveCount(0, { timeout: 10000 });
  });

  test('filter tabs switch correctly', async ({ adminPage }) => {
    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();

    // Click through all tabs to verify no crashes
    await adminPage.getByRole('button', { name: 'Alle' }).click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Genehmigt' }).click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Abgelehnt' }).click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();

    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();
  });
});
