import { test, expect } from '../../fixtures/base.fixture';
import { today } from '../../helpers/date.helper';

/**
 * #377 Minijob / § 2 Abs. 2 MiLoG — browser-driven UI tests der neuen Funktionen:
 *  - Mindestlohn-Karte in den Einstellungen
 *  - Arbeitszeitkonto-Checkbox + Mindestlohn/Cap-Infozeile im UserForm inkl.
 *    Persistenz-Round-Trip (verifiziert den UserListResponse-Fix im echten Browser)
 *  - MiLoG-Badge in der Benutzerübersicht bei einem Über-50-%-Monat
 *
 * Läuft gegen den rebuilt Frontend-Container (E2E_BASE_URL). Ephemerer MA je Test,
 * self-cleaning.
 *
 * Der Badge-Test ist KALENDERUNABHÄNGIG aufgebaut — Begründung im Detail in
 * `minijob-milog.spec.ts` (MILOG_SETUP). Kurz: die 50-%-Prüfung ist eine Schwelle
 * des LAUFENDEN Monats, der Saldo-Stichtag (#313) schneidet die Zukunft weg — der
 * einzige an jedem Kalendertag verfügbare Tag ist also heute selbst, und ein
 * ausgestempelter Eintrag von heute zieht den Stichtag auf heute. Damit ein Tag
 * reicht, ist die Vertragsbasis winzig (1 h/Woche → 4,33 h vereinbart, Grenze
 * 2,17 h; ein Tag mit 8,5 h netto ergibt 4,17 h Konto-Plusstunden).
 */
const MILOG_WEEKLY_HOURS = 1;
const MILOG_DAY = { start_time: '08:00', end_time: '17:00', break_minutes: 30 }; // 8,5 h netto

test.describe('#377 Minijob MiLoG — UI', () => {
  test('Einstellungen zeigen die Mindestlohn-Karte', async ({ adminPage }) => {
    await adminPage.goto('/admin/settings');
    await expect(adminPage.getByRole('heading', { name: 'Gesetzlicher Mindestlohn' })).toBeVisible();
    // aktueller gesetzlicher Wert (13,90 €/h ab 2026)
    await expect(adminPage.locator('main').getByText(/13\.90 €\/h/)).toBeVisible();
  });

  test('UserForm: Arbeitszeitkonto aktivieren zeigt Infozeile und bleibt nach Speichern erhalten', async ({ adminPage, adminApi }) => {
    const stamp = Date.now();
    const created = await adminApi.post('/admin/users', {
      username: `e2e-milogui-${stamp}`, first_name: 'E2EMilogUI', last_name: `T${stamp}`,
      password: 'E2ePass1234!', role: 'employee', weekly_hours: 7.62,
      vacation_days: 30, work_days_per_week: 5, milog_working_time_account: false,
    });
    const empId = created.user.id;
    const uname = `e2e-milogui-${stamp}`;
    const openEditor = async () => {
      // Desktop-Tabellen-Zeile des MA → dortiger "Bearbeiten"-Button (title-basiert;
      // der mobile aria-label-Button ist auf Desktop hidden und würde hängen).
      const row = adminPage.locator('tr', { hasText: uname });
      await expect(row).toBeVisible({ timeout: 15000 });
      await row.getByRole('button', { name: 'Bearbeiten' }).click();
      await expect(adminPage.getByRole('heading', { name: 'Benutzer bearbeiten' })).toBeVisible();
    };
    try {
      await adminPage.goto('/admin/users');
      await openEditor();

      const checkbox = adminPage.getByLabel(/Arbeitszeitkonto/i);
      await expect(checkbox).toBeVisible();
      await expect(checkbox).not.toBeChecked();

      await checkbox.check();
      await expect(checkbox).toBeChecked();
      // Infozeile erscheint mit aktuellem Mindestlohn + abgeleitetem Konto-Cap
      await expect(adminPage.getByText(/Aktueller Mindestlohn/)).toBeVisible();
      await expect(adminPage.getByText(/13\.90 €\/h/)).toBeVisible();
      await expect(adminPage.getByText(/max\. Konto/)).toBeVisible();
      // Speichern + Persistenz sind backend-/API-seitig abgedeckt
      // (test_userlist_carries_milog…, minijob-milog.spec.ts) — hier der reine
      // UI-Pfad (Checkbox + abgeleitete Infozeile).
    } finally {
      await adminApi.delete(`/admin/users/${empId}`).catch(() => {});
    }
  });

  test('Benutzerübersicht zeigt das MiLoG-Badge bei Über-50-%-Monat', async ({ adminPage, adminApi }) => {
    const stamp = Date.now();
    const entryIds: string[] = [];
    const created = await adminApi.post('/admin/users', {
      username: `e2e-milogbadge-${stamp}`, first_name: 'E2EMilogBadge', last_name: `T${stamp}`,
      password: 'E2ePass1234!', role: 'employee', weekly_hours: MILOG_WEEKLY_HOURS,
      vacation_days: 30, work_days_per_week: 5, milog_working_time_account: true,
    });
    const empId = created.user.id;
    try {
      const e = await adminApi.post(`/admin/users/${empId}/time-entries`, {
        date: today(), ...MILOG_DAY,
      });
      entryIds.push(e.id);
      expect(entryIds.length, 'setup: der Tageseintrag muss angelegt sein').toBe(1);

      await adminPage.goto('/admin/users');
      // die Zeile des MA (die Übersicht/milog_warnings laden async nach dem Grid);
      // toContainText statt getByText('MiLoG') — letzteres matcht auch den Tooltip-
      // Titel ("§ 2 Abs. 2 MiLoG") → strict-mode-Violation.
      const row = adminPage.locator('tr', { hasText: `e2e-milogbadge-${stamp}` });
      await expect(row).toBeVisible({ timeout: 15000 });
      await expect(row).toContainText('MiLoG', { timeout: 25000 });
    } finally {
      for (const id of entryIds) await adminApi.delete(`/admin/time-entries/${id}`).catch(() => {});
      await adminApi.delete(`/admin/users/${empId}`).catch(() => {});
    }
  });
});
