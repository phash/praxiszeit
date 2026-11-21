import { test, expect } from '../../fixtures/base.fixture';
import { currentMonth, daysAgo, formatDate, today, weekdayFromNow } from '../../helpers/date.helper';

// Plan 2026-11-21 Task 8 (Spec Teil 1 + 2A, Kundenfall 20.11.2026): Der Vertrag
// mit zwei Tagen wurde „ab heute" statt ab dem ersten Arbeitstag gespeichert.
// Der Dialog bietet „Ab {erster Arbeitstag} übernehmen" an, die Anerkennen-Liste
// wählt den Aushilfe-Mittwoch vor, Speichern erkennt ihn mit an.
//
// Eigene Person je Lauf (die Neuberechnung schreibt alle Einträge der Person im
// Wirkungsbereich um); Aufräumen über die Fixtures `createUser`/`createTimeEntry`.
type Day = { blocks: { start: string; end: string }[]; pause_minutes: number };
const MORNING: Day = { blocks: [{ start: '08:00', end: '12:00' }], pause_minutes: 0 };   // Tagessoll 4:00
const FREE: Day = { blocks: [], pause_minutes: 0 };
const FIVE_DAYS: Day[] = [MORNING, MORNING, MORNING, MORNING, MORNING];
const MON_TUE: Day[] = [MORNING, MORNING, FREE, FREE, FREE];

const deDate = (iso: string) => iso.split('-').reverse().join('.');
const shortDate = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Monatserster des Vormonats (ISO). */
function firstOfPreviousMonth(): string {
  const d = new Date();
  return formatDate(new Date(d.getFullYear(), d.getMonth() - 1, 1));
}

/** Jüngster vergangene Mittwoch, der ein Arbeitstag ist (kein Feiertag). */
function pastWorkingWednesday(): string {
  for (let n = 1; n <= 21; n += 1) {
    const iso = daysAgo(n);
    const isWednesday = new Date(`${iso}T12:00:00`).getDay() === 3;
    // weekdayFromNow(-n) springt nur bei Wochenende/Feiertag weiter.
    if (isWednesday && weekdayFromNow(-n) === iso) return iso;
  }
  throw new Error('Kein vergangener Mittwoch als Arbeitstag in den letzten drei Wochen');
}

test.describe('Vertrag ab dem ersten Arbeitstag (Plan 2026-11-21)', () => {
  test('Hinweis übernimmt den ersten Arbeitstag, der Aushilfe-Mittwoch wird mit anerkannt', async ({
    adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const firstWorkDay = firstOfPreviousMonth();
    const wednesday = pastWorkingWednesday();
    // Nur Ziffern im eindeutigen Teil: der Nachname landet in einer Regex.
    const unique = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
    const user = await createUser({
      username: `e2e_eintritt_${unique}`,
      password: 'TestPass123!',
      first_name: 'Eintritt',
      last_name: `Aushilfe${unique}`,
      role: 'employee',
      weekly_hours: 20,
      work_days_per_week: 5,
      vacation_days: 30,
      track_hours: true,
      first_work_day: firstWorkDay,
      work_blocks: FIVE_DAYS,
    });
    // Aushilfe am Mittwoch: heute voll angerechnet (Block 08:00–12:00).
    const entry = await createTimeEntry(user.id, {
      date: wednesday, start_time: '08:00', end_time: '12:00', break_minutes: 0,
    });
    // Der Fehler aus dem Kundenfall: Mo + Di „ab heute" gespeichert. Das erste
    // Speichern legt die Ausgangszeile am ersten Arbeitstag an.
    await adminApi.post(`/admin/users/${user.id}/working-hours-changes`, { effective_from: today(), blocks: MON_TUE });

    await adminPage.goto('/admin/users');
    await expect(adminPage.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
    await adminPage.getByPlaceholder('Suche nach Name oder Benutzername...').fill(user.last_name);
    const clock = adminPage.getByRole('button', {
      name: new RegExp(`^Arbeitszeit & Wochenstunden für Eintritt ${user.last_name}$`),
    }).first();
    await expect(clock).toBeVisible({ timeout: 5000 });
    await clock.click();
    const dialog = adminPage.getByRole('dialog', { name: /Wochenstunden/i });
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Teil 1: Hinweis mit erstem Arbeitstag und Vortag der gespeicherten Änderung.
    await expect(dialog.getByText(new RegExp(
      `^Vom ${esc(deDate(firstWorkDay))} \\(erster Arbeitstag\\) bis zum ${esc(deDate(daysAgo(1)))} `
      + 'gilt noch der Vertrag vom Anlegen \\(.+\\)\\. Soll die heutige Arbeitszeit schon ab dem ersten Arbeitstag gelten\\?$',
    ))).toBeVisible({ timeout: 10000 });
    await dialog.getByRole('button', { name: `Ab ${deDate(firstWorkDay)} übernehmen`, exact: true }).click();
    await expect(dialog.getByLabel('Gültig ab')).toHaveValue(firstWorkDay);

    // Teil 2A: der Mittwoch verliert seine Zeit (Werktag ohne Block) und ist vorausgewählt.
    const list = dialog.getByRole('region', { name: 'Einträge, die Zeit verlieren' });
    await expect(list).toBeVisible({ timeout: 10000 });
    const row = list.getByRole('checkbox', {
      name: new RegExp(`^Mi ${esc(shortDate(wednesday))} · gestempelt 08:00–12:00 · bisher 4:00 h → neu 0:00 h`),
    });
    await expect(row).toBeChecked();
    await expect(list.getByText('Tag ohne Block')).toBeVisible();
    // Alle Verluste anerkannt → keine Verkürzungswahl.
    await expect(dialog.getByRole('region', { name: 'Verkürzung' })).toHaveCount(0);

    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    const save = dialog.getByRole('button', { name: 'Speichern und 1 Eintrag anerkennen', exact: true });
    await expect(save).toBeEnabled({ timeout: 10000 });
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first())
      .toBeVisible({ timeout: 10000 });

    // Journal: Mittwoch ohne Soll, Eintrag anerkannt und voll angerechnet.
    const [year, month] = wednesday.split('-').map(Number);
    const journal = await adminApi.get(`/admin/users/${user.id}/journal?year=${year}&month=${month}`);
    const day = journal.days.find((d: any) => d.date === wednesday);
    const stamped = day.time_entries.find((e: any) => e.id === entry.id);
    expect([day.target_hours, day.actual_hours, stamped.credit_override]).toEqual([0, 4, true]);

    await adminPage.goto(`/admin/users/${user.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });
    if (wednesday.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }
    const wednesdayRow = adminPage.locator('main tr').filter({ hasText: shortDate(wednesday) }).first();
    await expect(wednesdayRow.getByText('anerkannt', { exact: true }))
      .toBeVisible({ timeout: 10000 });
  });
});
