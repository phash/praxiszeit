import { test, expect } from '../../fixtures/base.fixture';

/**
 * #281 — Admin-Monatsübersicht zeigt Urlaub/Krank in TAGEN (nicht Stunden),
 * und Krank ist DSGVO-Art.-9-maskiert hinter einem ausdrücklichen Opt-in.
 * UI-Test der in diesem Branch geänderten Bereiche.
 */
test.describe('Admin-Monatsübersicht: Tage statt Stunden + Krank-Opt-in (#281)', () => {
  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();
    // Auf den Monatsbericht warten (Tabelle gerendert)
    await expect(adminPage.getByRole('heading', { name: 'Monatsübersicht' })).toBeVisible();
  });

  test('Urlaub/Krank-Spalten sind in Tagen, nicht in Stunden', async ({ adminPage }) => {
    const main = adminPage.locator('main');
    await expect(main.getByRole('columnheader', { name: /Urlaub \(Tage\)/ })).toBeVisible();
    await expect(main.getByRole('columnheader', { name: /Krank \(Tage\)/ })).toBeVisible();
    // Keine Stunden-Überschriften mehr
    await expect(main.getByRole('columnheader', { name: /Urlaub \(h\)/ })).toHaveCount(0);
    await expect(main.getByRole('columnheader', { name: /Krank \(h\)/ })).toHaveCount(0);
  });

  test('Krank ist standardmäßig maskiert und per DSGVO-Opt-in einblendbar', async ({ adminPage }) => {
    const toggle = adminPage.getByRole('checkbox', { name: /Krankheitstage anzeigen/i });
    await expect(toggle).toBeVisible();
    await expect(toggle).not.toBeChecked();

    // Default maskiert: in der Krank-Spalte steht der Platzhalter "—"
    const desktopTable = adminPage.locator('main table').first();
    const rowCount = await desktopTable.locator('tbody tr').count();

    if (rowCount > 0) {
      // mindestens eine Zelle zeigt den Masken-Platzhalter
      await expect(desktopTable.getByText('—', { exact: true }).first()).toBeVisible();
    }

    // Opt-in aktivieren -> Re-Fetch mit include_health_data, Krank wird eingeblendet
    await toggle.check();
    await expect(toggle).toBeChecked();

    if (rowCount > 0) {
      // nach dem Opt-in keine "—"-Maske mehr in der Krank-Spalte (Tage-Wert sichtbar)
      await expect(desktopTable.getByText('—', { exact: true })).toHaveCount(0);
    }
  });
});
