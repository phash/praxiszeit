import { expect } from '@playwright/test';
import { authTest as test } from '../../fixtures/auth.fixture';
import { today } from '../../helpers/date.helper';

/**
 * #377 Minijob / § 2 Abs. 2 MiLoG: Mindestlohn-Ausgabe + weiche 50-%-Warnung.
 *
 * API-driven end-to-end (real nginx → backend → Postgres, real JWT). Isoliert +
 * self-cleaning: eigener ephemerer Minijob-MA (Flag an, 1 h/Woche vereinbart);
 * ein einziger langer Arbeitstag reißt damit die 50-%-Grenze des laufenden Monats.
 * Läuft gegen den /api-Proxy (E2E_API_BASE überschreibt den Port).
 *
 * KALENDERUNABHÄNGIG (siehe MILOG_SETUP unten) — der Aufbau nutzt ausschließlich
 * HEUTE und funktioniert daher an jedem Tag des Jahres, auch am Monatsersten und
 * am Wochenende.
 */

/**
 * MILOG_SETUP — warum der Aufbau genau so aussieht:
 *
 * 1. Die 50-%-Prüfung ist eine MONATS-Schwelle des LAUFENDEN Monats
 *    (`admin_users.users_overview` ruft `milog_50_check(db, u, _t.year, _t.month)`
 *    mit `_t = today_local()`). Ein Ausweichen auf den Vormonat würde also etwas
 *    anderes messen als das Merkmal — deshalb bleibt der Aufbau im aktuellen Monat.
 * 2. Der Saldo-Stichtag (#313, `calculation_service.get_soll_cutoff_date`) schneidet
 *    alles NACH dem Stichtag weg; zukunftsdatierte Einträge zählen nicht (und das
 *    Schema lehnt sie ohnehin ab).
 * 3. Der einzige Tag, den es an JEDEM Kalendertag im laufenden Monat gibt, ist damit
 *    heute selbst. Er zählt garantiert mit: der Stichtag ist "heute, sobald heute ein
 *    ausgestempelter TimeEntry existiert" — genau den legt dieser Test an. Der
 *    Ist-Wert ist wochentagsunabhängig (TimeEntry-Netto zählt auch samstags), der
 *    frühere "Werktage seit dem Monatsersten"-Aufbau war an den ersten ~6 Werktagen
 *    jedes Monats garantiert leer.
 * 4. Damit EIN Tag reicht, ist die Vertragsbasis winzig: 1 h/Woche → vereinbarte
 *    Monatszeit = 1 × 13/3 = 4,33 h, Grenze = 2,17 h. Ein Tag mit 8,5 h netto ergibt
 *    Konto-Plusstunden 8,5 − 4,33 = 4,17 h > 2,17 h. (Die Mehrtages-Akkumulation
 *    selbst ist reine Summenarithmetik und im Backend unit-getestet,
 *    `backend/tests/test_milog.py` — hier geht es um die echte Verdrahtung.)
 */
const MILOG_WEEKLY_HOURS = 1;          // → 4,33 h vereinbart, Grenze 2,17 h
const MILOG_DAY = { start_time: '08:00', end_time: '17:00', break_minutes: 30 }; // 8,5 h netto

test.describe('#377 Minijob MiLoG', () => {
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
      // Minijob-MA: 1 h/Woche = 4,33 h/Monat vereinbart, Konto-Flag an
      const created = await adminApi.post('/admin/users', {
        username: `e2e-milog-${stamp}`, first_name: 'E2E', last_name: 'MiLoG',
        password: 'E2ePass1234!', role: 'employee', weekly_hours: MILOG_WEEKLY_HOURS,
        vacation_days: 30, work_days_per_week: 5, milog_working_time_account: true,
      });
      empId = created.user.id;

      // EIN Tag heute mit 8,5 h netto (30-Min-Pause erfüllt §4 ArbZG) → Konto
      // 8,5 − 4,33 = 4,17 h > Grenze 2,17 h. Der Eintrag zieht zugleich den
      // Saldo-Stichtag auf heute, zählt also garantiert mit (siehe MILOG_SETUP).
      const e = await adminApi.post(`/admin/users/${empId}/time-entries`, {
        date: today(), ...MILOG_DAY,
      });
      entryIds.push(e.id);
      expect(entryIds.length, 'setup: der Tageseintrag muss angelegt sein').toBe(1);

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
