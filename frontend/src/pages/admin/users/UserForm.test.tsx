import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../../../contexts/ToastContext';
import { useSystemStore } from '../../../stores/systemStore';
import UserForm from './UserForm';

// Exposed mocks so #383 tests can configure the /carryovers fetch and assert on
// the PUT. Defaults keep the existing tests' carryover-useEffect a no-op.
const getMock = vi.fn();
const putMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));

beforeEach(() => {
  getMock.mockReset().mockResolvedValue({ data: [] });
  putMock.mockReset().mockResolvedValue({ data: {} });
  postMock.mockReset().mockResolvedValue({ data: { user: { id: 'new-user-1' } } });
});

function renderForm(props: Record<string, unknown> = {}) {
  return render(
    <ToastProvider>
      <UserForm onSaved={() => {}} {...props} />
    </ToastProvider>,
  );
}

describe('#377 UserForm MiLoG checkbox', () => {
  beforeEach(() => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', minimum_wage: { current: 13.9, since: '2026-01-01', next: null } },
      isLoaded: true,
    } as never);
  });

  it('renders the Arbeitszeitkonto checkbox (unchecked by default)', () => {
    renderForm();
    const cb = screen.getByLabelText(/Arbeitszeitkonto/i) as HTMLInputElement;
    expect(cb).toBeInTheDocument();
    expect(cb.checked).toBe(false);
  });

  it('shows the derived Mindestlohn/cap info line once enabled', () => {
    renderForm();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    // Default weekly_hours 40 → Monatszeit ≈ 173.3 h → Cap ≈ 86.7 h; Mindestlohn 13,90
    expect(screen.getByText(/13\.90 €\/h/)).toBeInTheDocument();
    expect(screen.getByText(/max\. Konto/)).toBeInTheDocument();
  });

  it('#382: does not crash if minimum_wage is present but has no numeric current', () => {
    // A malformed /system/info minimum_wage object used to throw
    // `minWage.current.toFixed(2)` → ErrorBoundary white-screen for milog users.
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', minimum_wage: {} },
      isLoaded: true,
    } as never);
    renderForm();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    // Renders the rest of the info line; the Mindestlohn prefix is simply omitted.
    expect(screen.getByText(/max\. Konto/)).toBeInTheDocument();
    expect(screen.queryByText(/Aktueller Mindestlohn/)).not.toBeInTheDocument();
  });

  it('prefills the checkbox from editUser', () => {
    renderForm({
      editUser: {
        id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
        weekly_hours: 7.62, vacation_days: 30, work_days_per_week: 5, track_hours: true,
        is_active: true, milog_working_time_account: true,
      },
    });
    expect((screen.getByLabelText(/Arbeitszeitkonto/i) as HTMLInputElement).checked).toBe(true);
  });

  it('#377 2a: shows the monthly-hours field only when the account flag is on', () => {
    renderForm();
    expect(screen.queryByLabelText(/Vereinbarte Monatsarbeitszeit \(h\)/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    expect(screen.getByLabelText(/Vereinbarte Monatsarbeitszeit \(h\)/i)).toBeInTheDocument();
  });

  it('#377 2a: prefills agreed_monthly_hours from editUser', () => {
    renderForm({
      editUser: {
        id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
        weekly_hours: 20, vacation_days: 30, work_days_per_week: 5, track_hours: true,
        is_active: true, milog_working_time_account: true, agreed_monthly_hours: 33,
      },
    });
    expect((screen.getByLabelText(/Vereinbarte Monatsarbeitszeit \(h\)/i) as HTMLInputElement).value).toBe('33');
  });

  it('#377 2a: sends agreed_monthly_hours in the update payload', async () => {
    getMock.mockResolvedValue({ data: [] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={{
          id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
          weekly_hours: 20, vacation_days: 30, work_days_per_week: 5, track_hours: true,
          is_active: true, milog_working_time_account: true, agreed_monthly_hours: 33,
        } as never} />
      </ToastProvider>,
    );
    const field = screen.getByLabelText(/Vereinbarte Monatsarbeitszeit \(h\)/i);
    fireEvent.change(field, { target: { value: '40' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      expect(call![1]).toMatchObject({ agreed_monthly_hours: 40 });
    });
  });
});

describe('#383 Übertrag Urlaubstage', () => {
  const editUser2026 = {
    id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
    weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
    is_active: true, first_work_day: '2026-06-01',
  };

  it('renders the field and prefills it from the start-year vacation_days carryover', async () => {
    getMock.mockResolvedValue({ data: [{ year: 2026, overtime_hours: 5, vacation_days: 8 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('8'));
  });

  it('saves the field value to /carryovers/{startYear} as vacation_days', async () => {
    getMock.mockResolvedValue({ data: [{ year: 2026, overtime_hours: 5, vacation_days: 8 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('8'));
    fireEvent.change(field, { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
      expect(call).toBeTruthy();
      expect(String(call![0])).toContain('/carryovers/2026');
      expect(call![1]).toMatchObject({ vacation_days: 10 });
    });
  });

  it('falls back to the current year when first_work_day is unset', async () => {
    const y = new Date().getFullYear();
    getMock.mockResolvedValue({ data: [{ year: y, overtime_hours: 0, vacation_days: 2 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={{ ...editUser2026, first_work_day: undefined } as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('2')); // loaded for current year
    fireEvent.change(field, { target: { value: '3.5' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
      expect(call).toBeTruthy();
      expect(String(call![0])).toContain(`/carryovers/${y}`);
      expect(call![1]).toMatchObject({ vacation_days: 3.5 });
    });
  });

  it('does not write a carryover when the prefill load failed (no clobber of an unknown value)', async () => {
    getMock.mockRejectedValue(new Error('network')); // /carryovers GET fails
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    fireEvent.change(field, { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(putMock).toHaveBeenCalled()); // the user PUT
    // loadedCarryoverYear stayed null → carryover write is suppressed …
    expect(putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'))).toBeUndefined();
    // … and the admin is warned (not silently told "erfolgreich").
    await waitFor(() =>
      expect(screen.getByText(/konnte nicht geladen werden und wurde NICHT gesetzt/i)).toBeInTheDocument(),
    );
  });

  it('re-prefills the carryover from the NEW start year when first_work_day is changed across a year (M-C1: no clobber)', async () => {
    getMock.mockResolvedValue({
      data: [
        { year: 2026, overtime_hours: 5, vacation_days: 8 },
        { year: 2027, overtime_hours: 9, vacation_days: 12 },
      ],
    });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const vac = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((vac as HTMLInputElement).value).toBe('8')); // 2026 row
    // Move first_work_day into 2027 → the field must reflect 2027's own carryover
    // (12), NOT copy 2026's value (8) into 2027 on save.
    fireEvent.change(screen.getByDisplayValue('2026-06-01'), { target: { value: '2027-03-01' } });
    await waitFor(() => expect((vac as HTMLInputElement).value).toBe('12'));
  });

  it('writes NO carryover row for an untouched user (both values 0, none existing)', async () => {
    getMock.mockResolvedValue({ data: [] }); // no existing carryover
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    await screen.findByLabelText(/Übertrag Urlaubstage/i);
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(putMock).toHaveBeenCalled()); // the user PUT itself
    const carryoverCall = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
    expect(carryoverCall).toBeUndefined();
  });
});

describe('Task 6+11: Wochenstunden/Tagesplan nur Anzeige beim Bearbeiten (#431)', () => {
  const baseEditUser = {
    id: 'u1', username: 'jd', first_name: 'Jane', last_name: 'Doe', role: 'employee',
    weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
    is_active: true, use_daily_schedule: false,
  };

  it('zeigt beim Bearbeiten ein read-only-Feld plus Button (kein Eingabefeld)', () => {
    renderForm({ editUser: baseEditUser });
    expect(screen.getByText('40,0 h/Woche')).toBeInTheDocument();
    expect(document.getElementById('f-weekly-hours')?.tagName).not.toBe('INPUT');
    expect(screen.getByRole('button', { name: /Wochenstunden anpassen/i })).toBeInTheDocument();
  });

  it('zeigt beim Anlegen ein Eingabefeld (kein Button)', () => {
    renderForm();
    expect(document.getElementById('f-weekly-hours')?.tagName).toBe('INPUT');
    expect(screen.queryByRole('button', { name: /Wochenstunden anpassen/i })).not.toBeInTheDocument();
  });

  it('sendet weekly_hours/Tagesplan-Felder beim Update NICHT mit (Backend lehnt sie sonst mit 400 ab)', async () => {
    // Task 7 (#431): nicht nur weekly_hours — alle acht historisierten
    // Felder (Modus, Tagesstunden, Arbeitstage) sind seit Task 7 gesperrt.
    renderForm({ editUser: baseEditUser });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      for (const field of [
        'weekly_hours', 'use_daily_schedule', 'work_days_per_week',
        'hours_monday', 'hours_tuesday', 'hours_wednesday', 'hours_thursday', 'hours_friday',
      ]) {
        expect(call![1]).not.toHaveProperty(field);
      }
    });
  });

  it('sendet weekly_hours beim Anlegen mit (kein Verlauf vorhanden, Startwert nötig)', async () => {
    renderForm();
    fireEvent.change(screen.getByLabelText(/Benutzername/i), { target: { value: 'newemployee' } });
    // Exact text: /Passwort/i also matches the show/hide-toggle button's
    // aria-label ("Passwort anzeigen") and would otherwise be ambiguous.
    fireEvent.change(screen.getByLabelText('Passwort *'), { target: { value: 'TestPass123!' } });
    fireEvent.change(screen.getByLabelText('Vorname'), { target: { value: 'New' } });
    fireEvent.change(screen.getByLabelText('Nachname'), { target: { value: 'User' } });
    fireEvent.change(document.getElementById('f-weekly-hours') as HTMLInputElement, { target: { value: '32' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      expect(postMock).toHaveBeenCalled();
      expect(postMock.mock.calls[0][1]).toMatchObject({ weekly_hours: 32 });
    });
  });

  // Task 11 (#431): der Button fehlte bisher genau für die Gruppe, die ihn am
  // dringendsten braucht — Task 7 sperrte den Update-Payload für
  // Tagesplan-Mitarbeitende bereits, aber das Formular zeigte ihnen
  // weiterhin ein Eingabefeld, dessen Eingabe beim Speichern kommentarlos
  // verworfen wurde (Important-Fund #2 im Task-7-Review). Jetzt bekommen
  // auch sie den Dialog-Button — er ist der einzige verbliebene Schreibweg.
  it('zeigt den Button auch bei individuellem Tagesplan', () => {
    renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true } });
    expect(screen.getByRole('button', { name: /Wochenstunden anpassen/i })).toBeInTheDocument();
    expect(document.getElementById('f-weekly-hours')?.tagName).not.toBe('INPUT');
  });

  it('zeigt Tagesstunden beim Bearbeiten nur als Anzeige (Tagesbreakdown in der Wochenstunden-Box, kein Eingabefeld je Wochentag)', () => {
    renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true, hours_monday: 8 } });
    // Aria-Label der (früheren) Mo-Fr-Eingabefelder ist `Stunden ${Mo|Di|...}`
    // — keins davon darf im Bearbeiten-Modus noch existieren.
    expect(screen.queryByLabelText('Stunden Mo')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Stunden Di')).not.toBeInTheDocument();
    expect(screen.getByText(/Mo 8,0/)).toBeInTheDocument();
  });

  // Task-11-Review Fix-Runde 1 (Important): vorher kombinierte die Box einen
  // FRISCHEN `displayWeeklyHours`-Total mit einem beim Formular-Öffnen
  // EINGEFRORENEN `formData.hours_*`-Breakdown — nach „Dialog öffnen →
  // Tagesplan ändern → speichern" bei weiterhin offenem Formular zeigte die
  // Box z. B. „Mo 8,0 / Di 5,0 / Mi 4,0 = 20,0 h/Woche" (Summanden ergeben
  // 17, nicht 20). `displayDayHours` (Users.tsx, analog zu
  // `displayWeeklyHours`) hält jetzt auch den Breakdown frisch, sodass beide
  // Zahlen wieder zusammenpassen.
  it('zeigt Aufschlüsselung und Summe konsistent, wenn frische Tageswerte über displayDayHours ankommen (statt der eingefrorenen formData-Werte)', () => {
    renderForm({
      editUser: {
        ...baseEditUser, use_daily_schedule: true,
        hours_monday: 8, hours_tuesday: 5, hours_wednesday: 4, hours_thursday: 0, hours_friday: 0,
      },
      // Simuliert: der Dialog hat Di 5→8 geändert und gespeichert, Users.tsx
      // hat refetcht — die Summe UND der Breakdown sind jetzt beide frisch.
      displayWeeklyHours: 20,
      displayDayHours: [8, 8, 4, 0, 0],
    });
    // Der widersprüchliche alte Text darf nirgends auftauchen …
    expect(screen.queryByText(/Di 5,0/)).not.toBeInTheDocument();
    // … stattdessen zeigt die Box den frischen Breakdown mit der frischen Summe zusammen.
    expect(screen.getByText('Mo 8,0 / Di 8,0 / Mi 4,0 = 20,0 h/Woche')).toBeInTheDocument();
  });

  it('zeigt "Arbeitstage pro Woche" beim Bearbeiten nur als Anzeige mit Verweis auf den Dialog', () => {
    renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true, work_days_per_week: 3 } });
    const workDaysEl = document.getElementById('f-work-days');
    expect(workDaysEl?.tagName).not.toBe('INPUT');
    expect(workDaysEl?.textContent).toBe('3');
    expect(screen.getByText(/belegten Wochentage im Tagesplan abgeleitet/)).toBeInTheDocument();
  });

  it('zeigt den "Individuelle Tagesstunden"-Haken beim Bearbeiten nur als Status-Anzeige (nicht klickbar)', () => {
    renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true } });
    expect(document.getElementById('use_daily_schedule')).not.toBeInTheDocument();
    expect(screen.getByText('Individuelle Tagesstunden aktiv')).toBeInTheDocument();
  });

  // Abschluss-Review #431, Fund 3 (Important): die Fix-Runde davor zog nur
  // `weekly_hours` und die fünf `hours_*` nach. `work_days_per_week` und
  // `use_daily_schedule` blieben eingefroren, obwohl der Dialog beide schreibt
  // und `_sync_user_from_change` sie bei einem Wirkungsdatum ≤ heute auf die
  // User-Zeile zurückspiegelt — genau die Kombination „frische Summe neben
  // eingefrorenem Rest", gegen die `displayDayHours` eingeführt wurde.

  it('zieht die Arbeitstage über displayWorkDays nach (frische Summe neben veralteten Arbeitstagen)', () => {
    renderForm({
      // Stand beim Öffnen des Formulars: gleichmäßig 40 h auf 5 Tage.
      editUser: { ...baseEditUser, weekly_hours: 40, work_days_per_week: 5 },
      // Der Dialog hat „20 h auf 4 Tage, gültig ab heute" gespeichert,
      // Users.tsx hat refetcht.
      displayWeeklyHours: 20,
      displayWorkDays: 4,
    });
    expect(screen.getByText('20,0 h/Woche')).toBeInTheDocument();
    expect(document.getElementById('f-work-days')?.textContent).toBe('4');
  });

  it('zieht den Modus über displayUseDailySchedule nach', () => {
    renderForm({
      editUser: { ...baseEditUser, weekly_hours: 40, work_days_per_week: 5, use_daily_schedule: false },
      // Der Dialog hat auf „Nach Tagen" umgestellt.
      displayWeeklyHours: 17,
      displayDayHours: [8, 5, 4, null, null],
      displayWorkDays: 3,
      displayUseDailySchedule: true,
    });
    // Der Modus-Status und die Wochenstunden-Box müssen beide den neuen Modus
    // zeigen — sonst stünde „Einheitliche Tagesstunden" über einem Tagesplan.
    expect(screen.getByText('Individuelle Tagesstunden aktiv')).toBeInTheDocument();
    expect(screen.getByText('Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche')).toBeInTheDocument();
    expect(screen.getByText(/belegten Wochentage im Tagesplan abgeleitet/)).toBeInTheDocument();
    expect(document.getElementById('f-work-days')?.textContent).toBe('3');
  });

  it('zieht auch den Weg zurück auf „gleichmäßig" nach', () => {
    renderForm({
      editUser: {
        ...baseEditUser, use_daily_schedule: true,
        hours_monday: 8, hours_tuesday: 5, hours_wednesday: 4,
        work_days_per_week: 3,
      },
      displayWeeklyHours: 40,
      displayDayHours: [null, null, null, null, null],
      displayWorkDays: 5,
      displayUseDailySchedule: false,
    });
    expect(screen.getByText('Einheitliche Tagesstunden (kein individueller Tagesplan)')).toBeInTheDocument();
    expect(screen.getByText('40,0 h/Woche')).toBeInTheDocument();
    expect(screen.queryByText(/Mo 8,0/)).not.toBeInTheDocument();
    expect(document.getElementById('f-work-days')?.textContent).toBe('5');
  });

  it('fällt ohne die Props auf den Stand des Formulars zurück (Anlegen/kein Treffer)', () => {
    renderForm({ editUser: { ...baseEditUser, work_days_per_week: 3, use_daily_schedule: true, hours_monday: 8 } });
    expect(document.getElementById('f-work-days')?.textContent).toBe('3');
    expect(screen.getByText('Individuelle Tagesstunden aktiv')).toBeInTheDocument();
  });

  it('erlaubt Arbeitstage/Tagesstunden-Haken/Tagesstunden weiterhin uneingeschränkt beim Anlegen', () => {
    renderForm();
    expect(document.getElementById('f-work-days')?.tagName).toBe('INPUT');
    const dailyScheduleCheckbox = document.getElementById('use_daily_schedule') as HTMLInputElement;
    expect(dailyScheduleCheckbox.tagName).toBe('INPUT');
    fireEvent.click(dailyScheduleCheckbox);
    expect(screen.getByLabelText('Stunden Mo')).toBeEnabled();
  });

  it('sendet weekly_hours/Tagesplan-Felder beim Update NICHT mit, auch wenn ein individueller Tagesplan aktiv ist (I2-Ausnahme entfaellt seit #431)', async () => {
    renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      for (const field of [
        'weekly_hours', 'use_daily_schedule', 'work_days_per_week',
        'hours_monday', 'hours_tuesday', 'hours_wednesday', 'hours_thursday', 'hours_friday',
      ]) {
        expect(call![1]).not.toHaveProperty(field);
      }
    });
  });

  it('öffnet den Wochenstunden-Dialog für den bearbeiteten Nutzer', () => {
    const onOpenHoursHistory = vi.fn();
    renderForm({ editUser: baseEditUser, onOpenHoursHistory });
    fireEvent.click(screen.getByRole('button', { name: /Wochenstunden anpassen/i }));
    expect(onOpenHoursHistory).toHaveBeenCalledWith(baseEditUser);
  });

  it('erlaubt alle Felder beim Anlegen', () => {
    renderForm({ editUser: null });
    expect(screen.getByLabelText('Wochenstunden')).toBeEnabled();
  });
});
