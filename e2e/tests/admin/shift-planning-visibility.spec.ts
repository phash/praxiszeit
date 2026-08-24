import { Page, Locator } from '@playwright/test';
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
 *
 * #451: die mandantenweite Einstellung `shift_planning_enabled` wird NICHT
 * mehr hier geschaltet — siehe global-setup.ts.
 *
 * #451-Folgefix: ShiftPlanning.tsx (Mitarbeiter-Ansicht) zeigt einen
 * freigegebenen, heute nicht geltenden Plan auf zwei Arten, je nachdem, ob
 * er der EINZIGE sichtbare Vorschau-Plan ist:
 *   - `solePreview`: direkt als eigene Karte mit `<h2>{name}</h2>`.
 *   - sonst: als `<option>` in einer Auswahlliste (`aria-label`
 *     "Vorschau-Schichtplan wählen"); das Detail lädt erst nach Auswahl.
 * Läuft parallel im selben Mandanten eine andere Schichtplanungs-Spec, die
 * gerade einen weiteren, heute geltenden Plan anlegt (z. B.
 * shift-planning.spec.ts via "Aktiv schalten"), kippt unser Plan vom ersten
 * in den zweiten Zustand — und eine `<option>` in einem geschlossenen
 * `<select>` ist nie "sichtbar" (CLAUDE.md-Falle „<select>-Optionen").
 * `openReleasedPlan()` bildet BEIDE Zustände nach: im zweiten Fall wählt sie
 * die Option wirklich aus und wartet, bis der Plan sichtbar geöffnet ist
 * (PDF-Knopf erscheint erst, wenn das Detail geladen ist), statt die
 * Zusicherung auf ein bloßes `toBeAttached` aufzuweichen.
 */
async function openReleasedPlan(page: Page, planName: string): Promise<void> {
  const main = page.locator('main');
  const heading = main.getByRole('heading', { name: planName });
  const select = main.getByLabel('Vorschau-Schichtplan wählen');

  // Warten, bis EINER der beiden Zustände erreicht ist — die Seite lädt
  // Pläne asynchron nach, vorher steht evtl. keins von beiden.
  await expect(heading.or(select)).toBeVisible({ timeout: 10000 });

  if ((await heading.count()) > 0) {
    return; // solePreview: schon direkt gerendert, nichts weiter zu tun.
  }

  // Auswahlliste: unsere Option kann in einem geschlossenen <select> nie
  // "sichtbar" sein — nur "attached" prüfen, dann wirklich auswählen, sonst
  // bleibt der Plan für den Test in Wahrheit ungeöffnet.
  const option = select.locator('option', { hasText: planName });
  await expect(option).toBeAttached({ timeout: 10000 });
  const value = await option.first().getAttribute('value');
  await select.selectOption(value!);

  // Wirklich geöffnet, nicht nur ausgewählt: das Detail (Wochenraster/Status)
  // lädt erst nach der Auswahl nach; der PDF-Knopf dieses Vorschau-Blocks
  // erscheint in ShiftPlanning.tsx exakt dann, wenn das Detail da ist.
  await expect(pdfButtonNear(select)).toBeVisible({ timeout: 10000 });
}

/**
 * Der PDF-Knopf des Vorschau-Blocks ist im DOM ein GESCHWISTER des
 * `<select>` (beide Kinder derselben Kopfzeile in ShiftPlanning.tsx), keine
 * Überschrift verrät dort, zu welchem Plan er gehört — anders als bei den
 * heute geltenden Plänen (`PlanBlock`), wo Überschrift und PDF-Knopf
 * Geschwister sind. Es gibt aber nur EINEN Vorschau-Block gleichzeitig
 * (`previewId`/`previewDetail` ist ein Einzelwert), der PDF-Knopf ist also
 * eindeutig unser gerade ausgewählter Plan — solange man ihn über die
 * Kopfzeile DIESES Blocks scopt und nicht ungescoped über die ganze Seite
 * sucht (sonst träfe man zusätzlich den PDF-Knopf jedes heute geltenden
 * Plans einer parallel laufenden Spec).
 */
function pdfButtonNear(select: Locator) {
  return select.locator('..').locator('..').getByRole('button', { name: 'PDF' });
}

test.describe('Schichtplan-Freigabe (#443)', () => {
  test.describe.configure({ mode: 'serial' });

  const unique = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const releasedName = `E2E-Freigegeben-${unique}`;
  const draftName = `E2E-Entwurf-${unique}`;

  test.afterAll(async ({ adminApi }) => {
    try {
      const plans = await adminApi.get('/shift-planning/plans');
      for (const p of plans) {
        if (p.name === releasedName || p.name === draftName) {
          await adminApi.delete(`/shift-planning/plans/${p.id}`);
        }
      }
    } catch {
      /* ignore */
    }
  });

  test('ein freigegebener, noch nicht geltender Plan erscheint beim Mitarbeitenden', async ({
    adminPage,
    adminApi,
    employeePage,
  }) => {
    // Zwei Pläne, beide inaktiv und ohne Datumsfenster — beide gelten heute nicht.
    const released = await adminApi.post('/shift-planning/plans', { name: releasedName });
    await adminApi.post('/shift-planning/plans', { name: draftName });

    // Gegenprobe VOR der Freigabe: der Mitarbeitende sieht keinen der beiden
    // — weder als Überschrift noch (unsichtbar) als Auswahl-Option, das
    // Backend liefert nicht-freigegebene Pläne für Nicht-Admins gar nicht erst.
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

    // Jetzt ist der freigegebene Plan für den Mitarbeitenden erreichbar —
    // den Entwurf sieht er weiterhin nicht, in keiner Form.
    await employeePage.goto('/shift-planning');
    await openReleasedPlan(employeePage, releasedName);
    await expect(employeePage.locator('main').getByText(draftName)).toHaveCount(0);

    // Und er ist als noch nicht geltend gekennzeichnet.
    await expect(employeePage.locator('main').getByText(/gilt noch nicht/i)).toBeVisible();
  });

  test('der PDF-Knopf liefert dem Mitarbeitenden eine Datei', async ({ employeePage }) => {
    // Läuft nach dem ersten Test: der freigegebene Plan steht noch.
    await employeePage.goto('/shift-planning');
    await openReleasedPlan(employeePage, releasedName);

    // Nicht ungescoped: seit #443 hat JEDER heute geltende Plan seinen eigenen
    // PDF-Knopf, dazu der Vorschau-Block — mehrere sichtbare Pläne (auch durch
    // eine parallel laufende Spec im selben Mandanten) würden sonst einen
    // strict-mode-Verstoß auslösen. Je nach Zustand (siehe openReleasedPlan)
    // ist der richtige Knopf entweder der Geschwister-Knopf der Überschrift
    // (solePreview → PlanBlock) oder der Geschwister-Knopf des Auswahl-Selects
    // (Vorschau-Block).
    const main = employeePage.locator('main');
    const heading = main.getByRole('heading', { name: releasedName });
    const select = main.getByLabel('Vorschau-Schichtplan wählen');
    const pdfButton =
      (await heading.count()) > 0 ? heading.locator('..').getByRole('button', { name: 'PDF' }) : pdfButtonNear(select);

    const download = employeePage.waitForEvent('download');
    await pdfButton.click();
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
