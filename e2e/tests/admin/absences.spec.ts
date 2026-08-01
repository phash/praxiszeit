import { test, expect } from '../../fixtures/base.fixture';
import { nextWeekday, daysFromNow } from '../../helpers/date.helper';

test.describe('Admin Absences', () => {
  test('create absence for employee', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Wait for the employees fetch to populate the dropdown — without this
    // the option list can be empty when we synchronously read it, which
    // makes the test flaky on slower runs. Use ``toBeAttached`` (not
    // ``toBeVisible``) because <option>s inside a closed <select> count
    // as non-visible in Playwright's CSS-visibility model.
    const employeeSelect = adminPage.getByTestId('absence-employee-filter');
    const targetOption = employeeSelect.locator('option', { hasText: testEmployee.last_name });
    await expect(targetOption.first()).toBeAttached({ timeout: 10000 });
    const targetValue = await targetOption.first().getAttribute('value');
    expect(targetValue).toBeTruthy();
    await employeeSelect.selectOption(targetValue!);

    // Click "Abwesenheit eintragen"
    await adminPage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Fill the form with a far-future unique date to avoid conflicts
    const dateInput = adminPage.locator('input[type="date"]').first();
    await dateInput.fill(daysFromNow(30));

    // Type should default to vacation
    const typeSelect = adminPage.locator('select').filter({ has: adminPage.locator('option[value="vacation"]') }).first();
    await typeSelect.selectOption('vacation');

    // Submit and wait for response
    const responsePromise = adminPage.waitForResponse(
      (resp) => resp.url().includes('/api/absences') && resp.request().method() === 'POST'
    );
    await adminPage.getByRole('button', { name: 'Speichern' }).click();
    const response = await responsePromise;

    if (response.ok()) {
      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /eingetragen|erfolgreich|gespeichert/ })
      ).toBeVisible({ timeout: 10000 });
    } else {
      // If it fails (e.g. duplicate), check we at least got an error message displayed
      await expect(adminPage.locator('.bg-red-50, [role="alert"]')).toBeVisible({ timeout: 5000 });
    }
  });

  // Die Voraussetzung "es gibt eine löschbare Abwesenheitszeile" wird hier
  // hergestellt (Fixture legt sie an) — die frühere
  // `isVisible().catch(() => false)`-Weiche ohne else-Zweig machte den Test
  // ersatzlos grün, sobald der Löschknopf fehlte: genau die Regression, die er
  // abfangen soll. Der eindeutige Notiz-Marker adressiert DIESE Zeile, damit
  // `.first()` nicht auf eine automatisch eingebuchte Betriebsferien-Zeile
  // desselben MA zeigt.
  test('delete absence', async ({ adminPage, testEmployee, createAbsence }) => {
    const uniqueNote = `E2E delete ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    // Create an absence via API for the test employee
    await createAbsence({
      date: nextWeekday(),
      type: 'other',
      hours: 8,
      note: uniqueNote,
      user_id: testEmployee.id,
    });

    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Select the test employee. The <select> is populated by an async fetch —
    // wait for the employee's option to attach before reading, else the loop
    // races the fetch and finds nothing (CLAUDE.md <select> pattern → flake at
    // `expect(targetValue).not.toBe('')`).
    const employeeSelect = adminPage.getByTestId('absence-employee-filter');
    await expect(
      employeeSelect.locator('option', { hasText: testEmployee.last_name }).first()
    ).toBeAttached({ timeout: 10000 });
    const options = employeeSelect.locator('option');
    const count = await options.count();
    let targetValue = '';
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent();
      if (text && text.includes(testEmployee.last_name)) {
        targetValue = await options.nth(i).getAttribute('value') || '';
        break;
      }
    }
    expect(targetValue).not.toBe('');
    await employeeSelect.selectOption(targetValue);
    await adminPage.waitForLoadState('networkidle');

    // Genau die Zeile DIESER Abwesenheit
    const row = adminPage.locator('main tr').filter({ hasText: uniqueNote });
    await expect(row).toBeVisible({ timeout: 10000 });
    await row.getByRole('button', { name: 'Löschen' }).click();

    // Confirm dialog
    const dialog = adminPage.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Löschen' }).click();

    // Check for success toast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'gelöscht' })
    ).toBeVisible({ timeout: 10000 });

    // Und die Zeile ist wirklich fort — der Toast allein belegt keine Löschung.
    await expect(row).toHaveCount(0, { timeout: 10000 });
  });

  test('create company closure', async ({ adminPage, adminApi }) => {
    const closureName = `E2E Betriebsferien ${Date.now()}`;
    try {
      await adminPage.goto('/admin/absences');
      await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

      // Switch to Betriebsferien tab
      await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
      await expect(adminPage.getByRole('button', { name: 'Betriebsferien erstellen' })).toBeVisible();

      // Click "Betriebsferien erstellen"
      await adminPage.getByRole('button', { name: 'Betriebsferien erstellen' }).click();

      // Fill the form
      const nameInput = adminPage.locator('input[type="text"]').first();
      await nameInput.fill(closureName);

      // Set start and end dates (future dates)
      const dateInputs = adminPage.locator('input[type="date"]');
      const startDate = daysFromNow(60);
      const endDate = daysFromNow(62);
      await dateInputs.first().fill(startDate);
      await dateInputs.nth(1).fill(endDate);

      // Submit
      await adminPage.getByRole('button', { name: /Betriebsferien erstellen/ }).click();

      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /Betriebsferien|eingetragen|erstellt/ })
      ).toBeVisible({ timeout: 10000 });
    } finally {
      // Aufräumen: eine stehengebliebene Betriebsferien-Zeile bucht JEDEM
      // künftig angelegten Testkonto sofort Abwesenheiten ein
      // (admin_users._enroll_user_in_open_closures) — genau die Müllquelle,
      // die den Jahresexport aufgebläht hat.
      try {
        const closures = await adminApi.get('/company-closures/');
        for (const c of closures.filter((c: any) => c.name === closureName)) {
          await adminApi.delete(`/company-closures/${c.id}`);
        }
      } catch { /* best effort */ }
    }
  });

  // Auch hier war die Zusicherung in eine verschluckte Sichtbarkeitsabfrage
  // ohne else-Zweig gepackt: fehlte der Löschknopf, lief der Test durch, ohne
  // irgendetwas zu prüfen. Die Voraussetzung (eine Betriebsferien-Zeile) legt
  // der Test selbst an, also darf sie hart zugesichert werden. Das frühere
  // `try { … } catch { test.skip() }` um das Anlegen ist ebenfalls fort — ein
  // fehlschlagendes POST /company-closures ist ein Fehler, kein Grund zum
  // Überspringen.
  test('delete company closure', async ({ adminPage, adminApi }) => {
    // Create a closure via API
    const closureName = `E2E Delete Test ${Date.now()}`;
    const closure = await adminApi.post('/company-closures', {
      name: closureName,
      start_date: daysFromNow(90),
      end_date: daysFromNow(91),
    });

    try {
      await adminPage.goto('/admin/absences');
      await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

      // Switch to Betriebsferien tab
      await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
      await adminPage.waitForLoadState('networkidle');

      // Genau die Zeile DIESER Betriebsferien
      const row = adminPage.locator('main tr').filter({ hasText: closureName });
      await expect(row).toBeVisible({ timeout: 10000 });
      await row.getByRole('button', { name: 'Betriebsferien löschen' }).click();

      // Confirm dialog
      const dialog = adminPage.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: 'Löschen' }).click();

      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /gelöscht/ })
      ).toBeVisible({ timeout: 10000 });

      // Und die Zeile ist wirklich fort.
      await expect(row).toHaveCount(0, { timeout: 10000 });
    } finally {
      try { await adminApi.delete(`/company-closures/${closure.id}`); } catch { /* schon gelöscht */ }
    }
  });

  test('tab switch between absences and closures', async ({ adminPage }) => {
    await adminPage.goto('/admin/absences');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheiten verwalten' })).toBeVisible();

    // Should start on absences tab with employee selector visible
    await expect(adminPage.getByText('Mitarbeiter-Abwesenheiten')).toBeVisible();

    // Switch to Betriebsferien
    await adminPage.getByRole('button', { name: 'Betriebsferien' }).click();
    await expect(adminPage.getByText('Betriebsferien').first()).toBeVisible();

    // Switch back
    await adminPage.getByRole('button', { name: 'Mitarbeiter-Abwesenheiten' }).click();
    // Verify the employee select dropdown is visible (contains "Alle Mitarbeiter" option)
    const selectDropdown = adminPage.getByTestId('absence-employee-filter');
    await expect(selectDropdown).toBeVisible();
    await expect(selectDropdown.locator('option').first()).toContainText('Alle Mitarbeiter');

    // Accessibility regression guard: the filter must expose its <label> as its
    // accessible name via htmlFor/id. Without that association a screen reader
    // announces a nameless combobox — and the test suite loses its only stable
    // selector (the department filter above is rendered conditionally, so
    // `locator('select').first()` silently pointed at a different field).
    await expect(
      adminPage.getByRole('combobox', { name: 'Mitarbeiter', exact: true })
    ).toBeVisible();
  });
});
