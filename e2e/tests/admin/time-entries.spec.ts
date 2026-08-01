import { test, expect } from '../../fixtures/base.fixture';
import { today, todayDisplay } from '../../helpers/date.helper';

test.describe('Admin Time Entries', () => {
  test('create entry for employee via admin dashboard', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();

    // Wait for data to load
    await adminPage.waitForLoadState('networkidle');

    // Click the test employee row to open detail modal
    const employeeRow = adminPage.locator(`[aria-label*="${testEmployee.last_name}"]`).first();
    await expect(employeeRow).toBeVisible({ timeout: 10000 });
    await employeeRow.click();

    // Wait for the detail modal to appear
    const dialog = adminPage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Click "Neuer Eintrag" button in the detail view
    const newEntryButton = dialog.getByRole('button', { name: /Neuer Eintrag|Neuen Eintrag/ });
    await expect(newEntryButton).toBeVisible({ timeout: 5000 });
    await newEntryButton.click();

    // Fill the form using accessible labels (scoped to dialog)
    // today(): der MA ist frisch angelegt und hat garantiert keinen Eintrag —
    // der frühere "Eintrag existiert vielleicht schon"-Vorbehalt trifft nicht
    // zu. Heute liegt zudem immer im Anzeigemonat des Modals (siehe
    // todayDisplay()).
    const date = today();
    await dialog.getByLabel('Datum').fill(date);
    await dialog.getByLabel('Von (Uhrzeit)').fill('09:00');
    await dialog.getByLabel('Bis (Uhrzeit)').fill('17:00');
    await dialog.getByLabel('Pause in Minuten').fill('30');

    // Save
    await dialog.getByRole('button', { name: 'Speichern' }).click();

    // Der ERFOLGS-Toast, nicht irgendein Alert: `locator('[role="alert"]').first()`
    // war auch dann grün, wenn das Anlegen mit einer Fehlermeldung endete —
    // also genau im Regressionsfall.
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /erstellt|gespeichert|aktualisiert/ })
    ).toBeVisible({ timeout: 15000 });

    // Und der Eintrag muss danach wirklich in der Liste des Modals stehen.
    await expect(
      adminPage.locator(`button[aria-label="Eintrag vom ${todayDisplay()} bearbeiten"]`).first()
    ).toBeVisible({ timeout: 10000 });
  });

  // Die Voraussetzung "es gibt eine Eintragszeile mit Bearbeiten-Knopf" ist
  // herstellbar und wird hergestellt: der Eintrag liegt im ANZEIGEMONAT des
  // Modals (siehe todayDisplay()) und wird über sein exaktes aria-label
  // adressiert. Die frühere `isVisible().catch(() => false)`-Weiche
  // machte den Test in genau dem Fall grün, den er absichern soll (Knopf oder
  // Zeile verschwindet) — der else-Zweig prüfte nur noch die Modal-Überschrift.
  test('edit entry via admin dashboard', async ({ adminPage, testEmployee, createTimeEntry }) => {
    // Create entry via API
    const date = today();
    await createTimeEntry(testEmployee.id, {
      date,
      start_time: '10:00',
      end_time: '14:00',
      break_minutes: 0,
    });

    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Click the employee row
    const employeeRow = adminPage.locator(`[aria-label*="${testEmployee.last_name}"]`).first();
    await expect(employeeRow).toBeVisible({ timeout: 10000 });
    await employeeRow.click();

    // Genau die Zeile DIESES Eintrags (aria-label trägt das Datum)
    const editButton = adminPage.locator(
      `button[aria-label="Eintrag vom ${todayDisplay()} bearbeiten"]`
    ).first();
    await expect(editButton).toBeVisible({ timeout: 10000 });
    await editButton.click();

    // Wait for form to show
    await expect(adminPage.getByRole('button', { name: 'Speichern' })).toBeVisible({ timeout: 5000 });
    // Save (just re-save without changes to test the flow)
    await adminPage.getByRole('button', { name: 'Speichern' }).click();

    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /aktualisiert|gespeichert/ })
    ).toBeVisible({ timeout: 10000 });
  });

  test('delete entry via admin dashboard', async ({ adminPage, testEmployee, createTimeEntry }) => {
    // Create entry via API
    const date = today();
    await createTimeEntry(testEmployee.id, {
      date,
      start_time: '15:00',
      end_time: '16:00',
      break_minutes: 0,
    });

    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Click the employee row
    const employeeRow = adminPage.locator(`[aria-label*="${testEmployee.last_name}"]`).first();
    await expect(employeeRow).toBeVisible({ timeout: 10000 });
    await employeeRow.click();

    // Genau die Zeile DIESES Eintrags
    const deleteButton = adminPage.locator(
      `button[aria-label="Eintrag vom ${todayDisplay()} löschen"]`
    ).first();
    await expect(deleteButton).toBeVisible({ timeout: 10000 });
    await deleteButton.click();

    // Confirm dialog
    const dialog = adminPage.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Löschen' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /gelöscht/ })
    ).toBeVisible({ timeout: 10000 });

    // Und die Zeile ist danach wirklich fort (der Toast allein belegt nichts).
    await expect(deleteButton).toHaveCount(0, { timeout: 10000 });
  });

  test('audit log records admin action', async ({ adminPage, testEmployee, createTimeEntry }) => {
    // Create an entry via API (this should generate an audit log entry)
    const date = today();
    await createTimeEntry(testEmployee.id, {
      date,
      start_time: '08:00',
      end_time: '12:00',
      break_minutes: 0,
    });

    // Navigate to audit log
    await adminPage.goto('/admin/audit-log');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsprotokoll' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Der Test heißt "audit log records admin action" — dann muss er auch DIESE
    // Aktion im Protokoll wiederfinden. Vorher stand hier
    // `expect(hasEntries || hasNoEntries).toBeTruthy()`: ein Protokoll, das
    // "Keine Einträge vorhanden" meldet, obwohl gerade ein Eintrag angelegt
    // wurde, galt ausdrücklich als Erfolg — die Aussage war nur noch "die Seite
    // stürzt nicht ab". Jetzt: auf den frisch angelegten MA filtern (dann ist
    // die Zeile eindeutig dieser Aktion zuzuordnen) und die "Erstellt"-Zeile
    // hart zusichern.
    // Über die ID filtern, nicht über den Nachnamen: die Fixture vergibt
    // `User<n>` je Worker-Prozess, bei zwei Workern gibt es denselben Nachnamen
    // also mehrfach (und `hasText: 'User1'` trifft zusätzlich `User10`).
    const userFilter = adminPage.locator('main select').first();
    await expect(
      userFilter.locator(`option[value="${testEmployee.id}"]`)
    ).toBeAttached({ timeout: 10000 });
    await userFilter.selectOption(testEmployee.id);
    await adminPage.waitForLoadState('networkidle');

    // Der Filter steht auf genau diesem MA — jede sichtbare Zeile gehört ihm.
    const rows = adminPage.locator('main tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10000 });
    await expect(rows.filter({ hasText: 'Erstellt' }).first()).toBeVisible({ timeout: 10000 });
  });
});
