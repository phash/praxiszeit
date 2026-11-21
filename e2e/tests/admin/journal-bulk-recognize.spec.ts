import { test, expect } from '../../fixtures/base.fixture';
import { currentMonth, daysAgo, formatDate, weekdayFromNow } from '../../helpers/date.helper';

// Plan 2026-11-21 Task 11 (Spec Teil 2B): Im Monatsjournal der Verwaltung lassen
// sich mehrere Einträge mit nicht angerechneter Zeit auf einmal anerkennen —
// Häkchen je Eintrag, „Ausgewählte anerkennen (n)“, Bestätigung.
//
// Eigene Person je Lauf (Block 08:00–12:00 an allen Werktagen); Aufräumen über
// die Fixtures `createUser`/`createTimeEntry`.
type Day = { blocks: { start: string; end: string }[]; pause_minutes: number };
const MORNING: Day = { blocks: [{ start: '08:00', end: '12:00' }], pause_minutes: 0 };
const FIVE_DAYS: Day[] = [MORNING, MORNING, MORNING, MORNING, MORNING];

const shortDate = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Monatserster des Vormonats (ISO). */
function firstOfPreviousMonth(): string {
  const d = new Date();
  return formatDate(new Date(d.getFullYear(), d.getMonth() - 1, 1));
}

/** Zwei vergangene Arbeitstage (ohne heute) im selben Monat, jüngster zuerst. */
function twoPastWorkdaysInOneMonth(): [string, string] {
  const byMonth = new Map<string, string[]>();
  for (let n = 1; n <= 21; n += 1) {
    const iso = daysAgo(n);
    // weekdayFromNow(-n) springt nur bei Wochenende/Feiertag weiter.
    // Annahme: die Feiertagsliste des Helpers deckt das Bundesland des
    // Test-Mandanten ab. Ein regionaler Feiertag außerhalb dieser Liste
    // (z. B. Buß- und Bettag in Sachsen) hätte keine Blöcke, also keine
    // nicht angerechnete Zeit und keine Checkbox.
    if (weekdayFromNow(-n) !== iso) continue;
    const days = byMonth.get(iso.slice(0, 7)) ?? [];
    days.push(iso);
    if (days.length === 2) return [days[0], days[1]];
    byMonth.set(iso.slice(0, 7), days);
  }
  throw new Error('Keine zwei vergangenen Arbeitstage im selben Monat in den letzten drei Wochen');
}

test.describe('Sammel-Anerkennen im Monatsjournal (Plan 2026-11-21)', () => {
  test('zwei Einträge außerhalb der Blöcke auswählen, bestätigen, beide anerkannt', async ({
    adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const [dayA, dayB] = twoPastWorkdaysInOneMonth();
    const unique = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
    const user = await createUser({
      username: `e2e_sammel_${unique}`,
      password: 'TestPass123!',
      first_name: 'Sammel',
      last_name: `Anerkennen${unique}`,
      role: 'employee',
      weekly_hours: 20,
      work_days_per_week: 5,
      vacation_days: 30,
      track_hours: true,
      first_work_day: firstOfPreviousMonth(),
      work_blocks: FIVE_DAYS,
    });
    // Beide Tage 07:00–13:00 gestempelt: vor und nach dem Block wird Zeit nicht angerechnet.
    const entryA = await createTimeEntry(user.id, { date: dayA, start_time: '07:00', end_time: '13:00', break_minutes: 0 });
    const entryB = await createTimeEntry(user.id, { date: dayB, start_time: '07:00', end_time: '13:00', break_minutes: 0 });

    await adminPage.goto(`/admin/users/${user.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });
    if (dayA.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }

    const main = adminPage.locator('main');
    const bulk = main.getByRole('button', { name: /^Ausgewählte anerkennen \(\d+\)$/ });
    await expect(bulk).toHaveText('Ausgewählte anerkennen (0)', { timeout: 10000 });
    await expect(bulk).toBeDisabled();

    for (const d of [dayA, dayB]) {
      await main.getByRole('checkbox', { name: new RegExp(`am ${esc(shortDate(d))} zum Anerkennen auswählen$`) }).check();
    }
    await expect(bulk).toHaveText('Ausgewählte anerkennen (2)');
    await bulk.click();

    const confirmDialog = adminPage.getByRole('alertdialog', { name: 'Ausgewählte Einträge anerkennen' });
    await expect(confirmDialog).toBeVisible({ timeout: 5000 });
    await expect(confirmDialog.getByText(new RegExp(
      '^2 Einträge werden mit der ganzen gestempelten Zeit angerechnet \\(zusätzlich \\d+:\\d{2} h\\)\\. '
      + 'Anerkennen lässt sich nicht zurücknehmen\\. Der Vorgang wird protokolliert\\.$',
    ))).toBeVisible();
    await confirmDialog.getByRole('button', { name: 'Einträge anerkennen', exact: true }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: '2 Einträge anerkannt' }).first())
      .toBeVisible({ timeout: 10000 });

    // Beide Zeilen zeigen „anerkannt“, nichts mehr auswählbar.
    for (const d of [dayA, dayB]) {
      const row = main.locator('tr').filter({ hasText: shortDate(d) }).first();
      await expect(row.getByText('anerkannt', { exact: true })).toBeVisible({ timeout: 10000 });
    }
    await expect(main.getByRole('checkbox', { name: /zum Anerkennen auswählen$/ })).toHaveCount(0);

    // Server: beide Einträge anerkannt und voll angerechnet (6 h).
    const [year, month] = dayA.split('-').map(Number);
    const journal = await adminApi.get(`/admin/users/${user.id}/journal?year=${year}&month=${month}`);
    const stamped = journal.days.flatMap((day: any) => day.time_entries)
      .filter((e: any) => e.id === entryA.id || e.id === entryB.id);
    expect(stamped.map((e: any) => [e.credit_override, e.net_hours])).toEqual([[true, 6], [true, 6]]);
  });
});
