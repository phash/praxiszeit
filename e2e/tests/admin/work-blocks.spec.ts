import { test, expect } from '../../fixtures/base.fixture';
import { purgeUser } from '../../fixtures/test-data.fixture';
import { ApiHelper } from '../../helpers/api.helper';
import { currentMonth, daysAgo, today, weekdayFromNow } from '../../helpers/date.helper';
import type { Browser, Page } from '@playwright/test';

// Spec 2026-10-08, 17.8 — Arbeitszeit-Blöcke Ende zu Ende.
//
// Je Test EIGENE Mitarbeitende (`workers: 2`): eine Neuberechnung kappt alle
// Einträge der Person im Wirkungsbereich — eine geteilte Testperson ließe einen
// parallel laufenden Test fremde Einträge umschreiben.
type Day = { blocks: { start: string; end: string }[]; pause_minutes: number };
const day = (spans: [string, string][], pause = 0): Day => ({
  blocks: spans.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const week = (d: Day): Day[] => [d, d, d, d, d];
const SPLIT = week(day([['08:00', '12:00'], ['15:00', '18:00']]));      // Tagessoll 7:00
const MORNING = week(day([['08:00', '12:00']]));                         // Tagessoll 4:00

const deDate = (iso: string) => iso.split('-').reverse().join('.');

async function employeeWithBlocks(createUser: (d: Record<string, unknown>) => Promise<any>, blocks: Day[], tag: string) {
  // Nur Ziffern im eindeutigen Teil: der Nachname landet in einer Regex
  // (`openDialog`) und in einem CSS-Attribut-Selektor (Admin-Dashboard).
  const unique = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return createUser({
    username: `e2e_blocks_${tag}_${unique}`,
    password: 'TestPass123!',
    first_name: 'Block',
    last_name: `${tag}${unique}`,
    role: 'employee',
    weekly_hours: 40,
    work_days_per_week: 5,
    vacation_days: 30,
    track_hours: true,
    work_blocks: blocks,
  });
}

// Login als die eigene Testperson (Muster `employeePage` in e2e/fixtures/test-data.fixture.ts):
// Refresh-Cookie aus dem Node-Login in einen frischen Kontext, Onboarding serverseitig abschließen.
async function loginAs(browser: Browser, username: string, password: string) {
  const api = new ApiHelper();
  const login = await api.login(username, password);
  await api.post('/auth/onboarding/complete').catch(() => {});
  const user = { ...login.user, onboarding_completed_at: new Date().toISOString() };
  const context = await browser.newContext();
  await context.addCookies([{
    name: 'refresh_token', value: api.refreshCookie, url: 'http://localhost/api/auth/refresh',
    httpOnly: true, sameSite: 'Lax',
  }]);
  const page = await context.newPage();
  await page.addInitScript((u) => {
    localStorage.setItem('auth-storage', JSON.stringify({ state: { user: u, isAuthenticated: true }, version: 0 }));
  }, user);
  await page.goto('/');
  await page.waitForURL('/');
  return { page, context };
}

async function openDialog(page: Page, lastName: string) {
  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
  await page.getByPlaceholder('Suche nach Name oder Benutzername...').fill(lastName);
  const clock = page.getByRole('button', { name: new RegExp(`^Arbeitszeit & Wochenstunden für Block ${lastName}$`) }).first();
  await expect(clock).toBeVisible({ timeout: 5000 });
  await clock.click();
  const dialog = page.getByRole('dialog', { name: /Wochenstunden/i });
  await expect(dialog).toBeVisible({ timeout: 5000 });
  return dialog;
}

test.describe('Arbeitszeit-Blöcke (Spec 2026-10-08)', () => {
  test('1: Anlegen mit Blöcken → Tagessoll in der Benutzerliste', async ({ adminPage, adminApi }) => {
    const unique = `${Date.now()}`;
    const lastName = `Anlage${unique}`;
    await adminPage.goto('/admin/users');
    await adminPage.getByRole('button', { name: 'Neue:r Mitarbeiter:in' }).click();
    await adminPage.locator('#f-username').fill(`e2e_blocks_new_${unique}`);
    await adminPage.locator('#f-firstname').fill('Block');
    await adminPage.locator('#f-lastname').fill(lastName);
    await adminPage.locator('#f-password').fill('TestPass123!');
    await adminPage.getByRole('radio', { name: 'Nach Arbeitsblöcken' }).check();
    await adminPage.getByRole('button', { name: 'Mo: Block hinzufügen' }).click();
    await adminPage.getByLabel('Mo Block 1 von').fill('08:00');
    await adminPage.getByLabel('Mo Block 1 bis').fill('12:00');
    await adminPage.getByRole('button', { name: 'Mo: Block hinzufügen' }).click();
    await adminPage.getByLabel('Mo Block 2 von').fill('15:00');
    await adminPage.getByLabel('Mo Block 2 bis').fill('18:00');
    await adminPage.getByLabel('Mo Pause innerhalb der Blöcke (Min)').fill('30');
    await expect(adminPage.getByTestId('f-blocks-day-0')).toContainText('Tagessoll 6:30 h');
    await adminPage.getByRole('button', { name: 'Speichern' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })).toBeVisible({ timeout: 10000 });

    const users = await adminApi.get('/admin/users?include_inactive=true&include_hidden=true&limit=500');
    const created = users.find((u: any) => u.last_name === lastName);
    try {
      expect(created).toBeTruthy();
      expect([created.hours_monday, created.weekly_hours, created.work_days_per_week]).toEqual([6.5, 6.5, 1]);
      await adminPage.getByPlaceholder('Suche nach Name oder Benutzername...').fill(lastName);
      await expect(adminPage.locator('tr', { hasText: lastName }).first()).toContainText('6.5');
    } finally {
      if (created) await purgeUser(adminApi, created.id);
    }
  });

  test('2: rückwirkende Verlängerung — Vorschau nennt den Eintrag, Journal zeigt neuen Wert und Lückenzeile', async ({
    adminPage, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Verl');
    const workday = weekdayFromNow(-14);
    // 11:00–16:00 liegt über der Lücke (12:15–14:45 nach Puffer) → 2:30 h angerechnet.
    await createTimeEntry(user.id, { date: workday, start_time: '11:00', end_time: '16:00', break_minutes: 0 });

    const dialog = await openDialog(adminPage, user.last_name);
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    // Nachmittag 14:00–18:00 mit 60 Min Pause: Tagessoll bleibt 7:00 h, die Lücke schrumpft.
    for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
      await dialog.getByLabel(`${label} Block 2 von`).fill('14:00');
      await dialog.getByLabel(`${label} Pause innerhalb der Blöcke (Min)`).fill('60');
    }
    await expect(dialog.getByText(/^Rückwirkende Änderung:/)).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText('Zeiteinträge: 1 neu berechnet')).toBeVisible();
    await expect(dialog.getByRole('region', { name: 'Verkürzung' })).toHaveCount(0);
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await dialog.getByRole('button', { name: 'Speichern' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert. 1 Zeiteintrag neu berechnet' }))
      .toBeVisible({ timeout: 10000 });

    await adminPage.goto(`/admin/users/${user.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });
    if (workday.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }
    await expect(adminPage.getByText(/1:30 h zwischen den Blöcken nicht angerechnet/).first()).toBeVisible({ timeout: 10000 });
  });

  test('3: Verkürzung — Standard „Ab heute", danach rückwirkend mit Grund und Haken', async ({
    adminPage, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Kurz');
    await createTimeEntry(user.id, { date: weekdayFromNow(-14), start_time: '15:00', end_time: '18:00', break_minutes: 0 });

    const dialog = await openDialog(adminPage, user.last_name);
    const shorten = async () => {
      for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
        await dialog.getByLabel(`${label} Block 2 bis`).fill('17:00');
      }
    };
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    await shorten();
    const region = dialog.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByText(/^1 Eintrag verliert angerechnete Zeit/)).toBeVisible();
    const lossless = region.getByRole('radio', {
      name: `Ab heute (${deDate(today())}) wirksam – vergangene Einträge bleiben unverändert`,
    });
    await expect(lossless).toBeChecked();
    const save = dialog.getByRole('button', { name: 'Speichern' });
    await expect(save).toBeEnabled({ timeout: 10000 });
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(today())} bis heute:`))).toBeVisible({ timeout: 5000 });

    // Dieselbe Kürzung jetzt rückwirkend: das Formular steht nach dem Speichern
    // auf dem neuen Stand (Ende 17:00), nur das Datum wandert zurück. Die
    // nächste Änderung (heute) begrenzt das verlustfreie Datum → nur Option 2 (P25).
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByRole('radio', { name: /^Ab heute/ })).toHaveCount(0);
    await expect(region.getByLabel('Grund').locator('option')).toHaveText([
      'Bitte wählen…', 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)', 'Mit der beschäftigten Person vereinbart',
      'Sonstiges',
    ]);
    await expect(save).toBeDisabled();
    await region.getByLabel('Grund').selectOption('erfassungsfehler');
    await region.getByLabel('Begründung').fill('Nachmittagsblock war falsch hinterlegt');
    await region.getByRole('checkbox', { name: /hinterlegte Arbeitszeit falsch war/ }).check();
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await expect(save).toBeEnabled();
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: '1 Zeiteintrag neu berechnet' })).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(daysAgo(21))} bis `))).toBeVisible();
  });

  test('4: rückwirkende Soll-Erhöhung ohne verlierenden Eintrag verlangt Grund und Haken (19.1 Nr. 1)', async ({
    adminPage, createUser,
  }) => {
    const user = await employeeWithBlocks(createUser, MORNING, 'Soll');
    const dialog = await openDialog(adminPage, user.last_name);
    await dialog.getByLabel('Gültig ab').fill(daysAgo(14));
    for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
      await dialog.getByLabel(`${label} Block 1 bis`).fill('13:00');
    }
    const region = dialog.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByText(/^Das Überstundenkonto sinkt im Wirkungsbereich um .* \(höheres Soll\), obwohl kein Eintrag angerechnete Zeit verliert$/))
      .toBeVisible();
    await region.getByRole('radio', { name: /^Rückwirkend ab/ }).check();
    const save = dialog.getByRole('button', { name: 'Speichern' });
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await expect(save).toBeDisabled();
    await region.getByLabel('Grund').selectOption('einvernehmlich');
    await region.getByLabel('Begründung').fill('Mit der Mitarbeiterin vereinbart');
    await region.getByRole('checkbox', { name: /mit der beschäftigten Person vereinbart ist/ }).check();
    await expect(save).toBeEnabled();
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });
  });

  test('5: Anerkennen im Admin-Dashboard — Kennzeichen „anerkannt", Netto 10:00 (13.3)', async ({
    adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Anerk');
    const workday = weekdayFromNow(-7);
    // K1: 08:00–18:00 über die Lücke → 7:30 h angerechnet, 2:30 h nicht angerechnet.
    const entry = await createTimeEntry(user.id, { date: workday, start_time: '08:00', end_time: '18:00', break_minutes: 0 });

    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();
    if (workday.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }
    await adminPage.waitForLoadState('networkidle');
    const employeeRow = adminPage.locator(`[aria-label*="${user.last_name}"]`).first();
    await expect(employeeRow).toBeVisible({ timeout: 10000 });
    await employeeRow.click();
    // Das Detail-Modal über seinen Schließen-Knopf adressieren — der Bestätigungsdialog ist ein zweiter Dialog.
    const details = adminPage.getByRole('dialog').filter({
      has: adminPage.getByRole('button', { name: `Details für ${user.first_name} ${user.last_name} schließen` }),
    });
    await expect(details).toBeVisible({ timeout: 5000 });
    const row = details.locator('tr').filter({
      has: adminPage.locator(`button[aria-label="Eintrag vom ${deDate(workday)} bearbeiten"]`),
    });
    await expect(row).toBeVisible({ timeout: 10000 });

    await row.getByRole('button', { name: 'Anerkennen' }).click();
    await expect(adminPage.getByText(/^Die gesamte gestempelte Zeit \(08:00–18:00\) wird angerechnet\./)).toBeVisible();
    await adminPage.getByRole('button', { name: 'Zeit anerkennen' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Zeit anerkannt' }).first()).toBeVisible({ timeout: 10000 });

    await expect(row.getByText('anerkannt', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(row).toContainText('10:00 h');   // Netto-Spalte (PR2 Task 14), vorher 7:30 h
    await expect(row.getByRole('button', { name: 'Anerkennen' })).toHaveCount(0);
    const entries = await adminApi.get(`/time-entries/?user_id=${user.id}&month=${workday.slice(0, 7)}`);
    const recognized = entries.find((e: any) => e.id === entry.id);
    expect([recognized.credit_override, recognized.net_hours, recognized.not_credited_minutes]).toEqual([true, 10, 0]);
  });

  test('6: Mitarbeiter-Sicht — Profilkarte und Dashboard-Hinweis nach einer Änderung „ab heute"', async ({
    adminApi, employeePage, testEmployee,
  }) => {
    const blocks = week(day([['08:00', '12:00'], ['13:00', '17:00']]));
    await adminApi.post(`/admin/users/${testEmployee.id}/working-hours-changes`, { effective_from: today(), blocks });

    await employeePage.goto('/');
    await expect(employeePage.getByText(new RegExp(`Ihre Arbeitszeit wurde ab ${deDate(today()).replace(/\./g, '\\.')} geändert`)))
      .toBeVisible({ timeout: 10000 });

    await employeePage.goto('/profile');
    await expect(employeePage.getByRole('heading', { name: 'Meine Arbeitszeit' })).toBeVisible({ timeout: 10000 });
    await expect(employeePage.getByRole('list', { name: 'Arbeitszeit heute' })).toContainText('Mo 08:00–12:00 + 13:00–17:00');
  });

  test('7: Mitarbeiterin beantragt die Anrechnung, Verwaltung genehmigt und erkennt an (P21)', async ({
    browser, adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Antrag');
    const workday = weekdayFromNow(-7);  // Anträge gibt es nur für vergangene Tage
    const entry = await createTimeEntry(user.id, { date: workday, start_time: '08:00', end_time: '18:00', break_minutes: 0 });
    const reason = `E2E Anrechnung ${Date.now()}-${Math.random().toString(36).slice(2, 8)}: Patienten in der Pause versorgt`;

    const employee = await loginAs(browser, user.username, 'TestPass123!');
    try {
      const page = employee.page;
      await page.goto('/time-tracking');
      if (workday.slice(0, 7) !== currentMonth()) {
        await page.getByRole('button', { name: 'Vorheriger Monat' }).click();
      }
      // Tabelle und Mobilkarte rendern beide eine RawStampNote — nur die sichtbare zählt.
      const request = page.locator('button:visible', { hasText: 'Anrechnung beantragen' });
      await expect(request).toHaveCount(1, { timeout: 10000 });
      await request.click();
      await expect(page.getByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeVisible({ timeout: 5000 });
      // ChangeRequestForm: Felder „Von"/„Bis" tragen die IDs cr-start/cr-end (Rohstempel vorbelegt, P21).
      await expect(page.locator('#cr-start')).toHaveValue('08:00');
      await expect(page.locator('#cr-end')).toHaveValue('18:00');
      await page.getByPlaceholder('Warum ist diese Änderung notwendig?').fill(reason);
      await page.getByRole('button', { name: 'Antrag stellen' }).click();
      await expect(page.locator('[role="alert"]').filter({ hasText: 'Antrag auf Anrechnung eingereicht' })).toBeVisible({ timeout: 10000 });
    } finally {
      await employee.context.close();
    }

    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');
    const card = adminPage.locator('div.bg-white').filter({ hasText: reason }).last();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.getByText('Anrechnung beantragt')).toBeVisible();
    await expect(card.getByText('Nicht angerechnet (Lücke): 2:30 h')).toBeVisible();
    await card.getByRole('button', { name: 'Genehmigen und anerkennen' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: /genehmigt/ }).first()).toBeVisible({ timeout: 10000 });
    await expect(card).toHaveCount(0, { timeout: 10000 });

    const entries = await adminApi.get(`/time-entries/?user_id=${user.id}&month=${workday.slice(0, 7)}`);
    const recognized = entries.find((e: any) => e.id === entry.id);
    expect([recognized.credit_override, recognized.net_hours, recognized.not_credited_minutes]).toEqual([true, 10, 0]);
  });

  test('8: Löschen einer verkürzenden Änderung → Standard „auf vorherigen Stand zurücksetzen" (19.1 Nr. 4)', async ({
    adminPage, adminApi, createUser,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Reset');
    // Soll-Senkung rückwirkend: verlängert (Saldo steigt) → ohne Grund zulässig.
    const lowered = week(day([['08:00', '12:00'], ['15:00', '17:00']]));
    const effective = daysAgo(14);
    await adminApi.post(`/admin/users/${user.id}/working-hours-changes`, { effective_from: effective, blocks: lowered });

    const dialog = await openDialog(adminPage, user.last_name);
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(effective)} bis heute:`))).toBeVisible({ timeout: 5000 });
    await dialog.getByRole('button', { name: 'Löschen' }).click();
    const panel = dialog.getByRole('alertdialog', { name: `Arbeitszeit-Änderung ab ${deDate(effective)} löschen` });
    const region = panel.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByRole('radio', { name: `Ab ${deDate(today())} auf den vorherigen Stand zurücksetzen` })).toBeChecked();
    const reset = panel.getByRole('button', { name: 'Zurücksetzen' });
    await expect(reset).toBeEnabled({ timeout: 10000 });
    await reset.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });

    // Die zurückgesetzte Zeile bleibt stehen (jetzt mit Ende), die neue gilt ab heute.
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(effective)} bis `))).toBeVisible();
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(today())} bis heute:`))).toBeVisible();
  });
});
