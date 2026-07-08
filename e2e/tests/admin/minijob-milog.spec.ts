import { expect } from '@playwright/test';
import { authTest as test } from '../../fixtures/auth.fixture';

/**
 * #377 Minijob / § 2 Abs. 2 MiLoG: Mindestlohn-Ausgabe + weiche 50-%-Warnung.
 *
 * API-driven end-to-end (real nginx → backend → Postgres, real JWT). Isoliert +
 * self-cleaning: eigener ephemerer Minijob-MA (Flag an, ~33 h/Monat vereinbart);
 * genug Ist-Stunden im laufenden Monat, dass die Konto-Plusstunden > 50 % reißen.
 * Läuft gegen den /api-Proxy (E2E_API_BASE überschreibt den Port).
 */
test.describe('#377 Minijob MiLoG', () => {
  // bis zu n Werktage des laufenden Monats, die NICHT in der Zukunft liegen
  // (Backend lehnt Zukunftsdaten ab), als YYYY-MM-DD (noon-UTC → kein Rollover).
  const currentMonthWeekdays = (n: number): string[] => {
    const now = new Date();
    const y = now.getUTCFullYear();
    const m = now.getUTCMonth(); // 0-based
    const todayDay = now.getUTCDate();
    const out: string[] = [];
    for (let day = 1; day <= todayDay && out.length < n; day++) {
      const d = new Date(Date.UTC(y, m, day, 12));
      if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(d.toISOString().slice(0, 10));
    }
    return out;
  };

  test('system_info exposes the minimum wage', async ({ adminApi }) => {
    const info = await adminApi.get('/system/info');
    expect(info.minimum_wage).toBeTruthy();
    expect(info.minimum_wage.current).toBeGreaterThan(0);
    expect(info.minimum_wage.since).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test('over-50% month raises a soft MILOG_ACCOUNT_50 warning in the admin overview', async ({ adminApi }) => {
    const stamp = Date.now();
    let empId: string | undefined;
    const entryIds: string[] = [];
    try {
      // Minijob-MA: 7,62 h/Woche ≈ 33 h/Monat vereinbart, Konto-Flag an
      const created = await adminApi.post('/admin/users', {
        username: `e2e-milog-${stamp}`, first_name: 'E2E', last_name: 'MiLoG',
        password: 'E2ePass1234!', role: 'employee', weekly_hours: 7.62,
        vacation_days: 30, work_days_per_week: 5, milog_working_time_account: true,
      });
      empId = created.user.id;

      // ~51 h Ist im laufenden Monat (6 × 8,5 h netto; 30-Min-Pause erfüllt §4 ArbZG)
      // → Konto 51−33 = 18 h > Cap 16,5 h
      for (const date of currentMonthWeekdays(6)) {
        const e = await adminApi.post(`/admin/users/${empId}/time-entries`, {
          date, start_time: '08:00', end_time: '17:00', break_minutes: 30,
        }).catch(() => null);
        if (e && e.id) entryIds.push(e.id);
      }
      expect(entryIds.length, 'need enough entries to exceed the 50% cap').toBeGreaterThanOrEqual(6);

      const rows = await adminApi.get('/admin/users-overview');
      const row = rows.find((r: { user_id: string }) => r.user_id === empId);
      expect(row).toBeTruthy();
      expect(row.milog_warnings.some((w: string) => w.includes('MILOG_ACCOUNT_50'))).toBe(true);

      // Flag aus → keine MiLoG-Warnung mehr
      await adminApi.put(`/admin/users/${empId}`, { milog_working_time_account: false });
      const rows2 = await adminApi.get('/admin/users-overview');
      const row2 = rows2.find((r: { user_id: string }) => r.user_id === empId);
      expect(row2.milog_warnings).toEqual([]);
    } finally {
      for (const id of entryIds) await adminApi.delete(`/admin/time-entries/${id}`).catch(() => {});
      if (empId) await adminApi.delete(`/admin/users/${empId}`).catch(() => {});
    }
  });
});
