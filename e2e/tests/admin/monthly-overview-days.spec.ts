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

    // Default maskiert: die Krank-Spalte zeigt den Platzhalter "—".
    //
    // Adressiert über data-testid statt über die Spaltenposition. Die
    // Positions-Variante war zweimal brüchig: zuletzt, als 1.16.0 die Spalte
    // "Jahresende (proj.)" ergänzte, die für Mitarbeitende ohne künftigen
    // Freizeitausgleich ebenfalls "—" rendert — die frühere tabellenweite
    // Prüfung "nirgends mehr ein —" schlug seitdem fehl, obwohl die
    // DSGVO-Maskierung selbst korrekt arbeitet.
    const sickCells = adminPage.getByTestId('sick-days-cell');
    const rowCount = await sickCells.count();

    if (rowCount > 0) {
      await expect(sickCells.first()).toHaveText('—');
    }

    // Opt-in aktivieren -> Re-Fetch mit include_health_data, Krank wird eingeblendet
    await toggle.check();
    await expect(toggle).toBeChecked();

    if (rowCount > 0) {
      // Kein Platzhalter mehr in der Krank-Spalte, stattdessen ein Tage-Wert.
      await expect(sickCells.filter({ hasText: /^—$/ })).toHaveCount(0);
      await expect(sickCells.first()).toHaveText(/^\d+[.,]\d$/);
    }
  });
});
