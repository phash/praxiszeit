import { test, expect } from '../../fixtures/base.fixture';

/**
 * #443: Ein Admin gibt einen noch nicht geltenden Plan für Mitarbeitende frei;
 * der Mitarbeitende findet ihn daraufhin in seiner Ansicht.
 *
 * Der Plan wird über die API angelegt statt über die Oberfläche — der Weg
 * "Plan anlegen per Dialog" ist bereits in shift-planning.spec.ts abgedeckt,
 * und dieser Test soll die Sichtbarkeitsnaht prüfen, nicht sie wiederholen.
 * Die Freigabe selbst läuft bewusst über die Oberfläche: der Schalter im
 * Einstellungsdialog ist Teil dessen, was hier belegt werden soll.
 */
test.describe('Schichtplan-Freigabe (#443)', () => {
  test.describe.configure({ mode: 'serial' });

  const unique = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const releasedName = `E2E-Freigegeben-${unique}`;
  const draftName = `E2E-Entwurf-${unique}`;

  test.afterAll(async ({ adminApi }) => {
    try {
      // Eine parallel laufende Schichtplanungs-Spec kann die mandantenweite
      // Einstellung zwischenzeitlich abgeschaltet haben — ohne dieses
      // Wiederanschalten würde der folgende GET 404 werfen (vom catch
      // verschluckt), und unsere Pläne blieben liegen.
      await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'true' });
      const plans = await adminApi.get('/shift-planning/plans');
      for (const p of plans) {
        if (p.name === releasedName || p.name === draftName) {
          await adminApi.delete(`/shift-planning/plans/${p.id}`);
        }
      }
    } catch {
      /* ignore */
    }
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'false' });
  });

  test('ein freigegebener, noch nicht geltender Plan erscheint beim Mitarbeitenden', async ({
    adminPage,
    adminApi,
    employeePage,
  }) => {
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'true' });

    // Zwei Pläne, beide inaktiv und ohne Datumsfenster — beide gelten heute nicht.
    const released = await adminApi.post('/shift-planning/plans', { name: releasedName });
    await adminApi.post('/shift-planning/plans', { name: draftName });

    // Gegenprobe VOR der Freigabe: der Mitarbeitende sieht keinen der beiden.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.getByRole('heading', { name: 'Schichtplan' })).toBeVisible();
    // In `main` scopen: die Hilfe-Seitenleiste dupliziert Texte und löst sonst
    // strict-mode-Verstöße aus.
    await expect(employeePage.locator('main').getByText(releasedName)).toHaveCount(0);
    await expect(employeePage.locator('main').getByText(draftName)).toHaveCount(0);

    // Freigabe über die Oberfläche: Plan öffnen, Einstellungen, Schalter, speichern.
    await adminPage.goto('/admin/shift-planning');
    await adminPage.locator('main').getByText(releasedName).first().click();
    await expect(adminPage.getByRole('heading', { name: releasedName })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Bearbeiten' }).click();

    const modal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Plan-Einstellungen' });
    await expect(modal.getByRole('heading', { name: 'Plan-Einstellungen' })).toBeVisible();
    await modal.getByLabel(/Für Mitarbeitende sichtbar/i).check();

    const save = adminPage.waitForResponse(
      (r) => r.url().includes(`/api/shift-planning/plans/${released.id}`) && r.request().method() === 'PUT',
    );
    await modal.getByRole('button', { name: 'Speichern' }).click();
    await save;

    // Jetzt sieht der Mitarbeitende den freigegebenen Plan — den Entwurf aber nicht.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.locator('main').getByText(releasedName).first()).toBeVisible();
    await expect(employeePage.locator('main').getByText(draftName)).toHaveCount(0);

    // Und er ist als noch nicht geltend gekennzeichnet.
    await expect(employeePage.locator('main').getByText(/gilt noch nicht/i)).toBeVisible();
  });

  test('der PDF-Knopf liefert dem Mitarbeitenden eine Datei', async ({ employeePage }) => {
    // Läuft nach dem ersten Test: der freigegebene Plan steht noch.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.locator('main').getByText(releasedName).first()).toBeVisible();

    // Nicht ungescoped: seit #443 hat JEDER heute geltende Plan seinen eigenen
    // PDF-Knopf, dazu ggf. der Vorschau-Block — mehrere sichtbare Pläne (auch
    // durch eine parallel laufende Spec im selben Mandanten) würden sonst
    // einen strict-mode-Verstoß auslösen. Überschrift und PDF-Knopf sind in
    // `PlanBlock` (ShiftPlanning.tsx) Geschwister in derselben Kopfzeile —
    // darüber lässt sich der Knopf des RICHTIGEN Plans eindeutig treffen.
    const planRow = employeePage.getByRole('heading', { name: releasedName }).locator('..');
    const download = employeePage.waitForEvent('download');
    await planRow.getByRole('button', { name: 'PDF' }).click();
    const file = await download;
    // Nicht nur "irgendein PDF kam an" belegen, sondern dass es der RICHTIGE
    // Plan war: der Dateiname wird clientseitig aus dem Plannamen gebaut
    // (`Schichtplan_${safe}.pdf`, siehe frontend/src/api/shiftPlanning.ts).
    // `unique` besteht nur aus Ziffern und einem Bindestrich — beides bleibt
    // von der Bereinigung (nicht-alphanumerische Zeichen → `_`) unangetastet,
    // der Teil übersteht die Umformung also garantiert unverändert.
    expect(file.suggestedFilename()).toContain(unique);
    expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  });
});
