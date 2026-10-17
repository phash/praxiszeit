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

const baseEditUser = {
  id: 'u1', username: 'jd', first_name: 'Jane', last_name: 'Doe', role: 'employee',
  weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
  is_active: true, use_daily_schedule: false,
};

describe('Task 6+11: Wochenstunden/Tagesplan nur Anzeige beim Bearbeiten (#431)', () => {
  it('zeigt beim Bearbeiten ein read-only-Feld plus Button (kein Eingabefeld)', () => {
    renderForm({ editUser: baseEditUser });
    expect(screen.getByText('40,0 h/Woche')).toBeInTheDocument();
    expect(document.getElementById('f-weekly-hours')?.tagName).not.toBe('INPUT');
    expect(screen.getByRole('button', { name: /Arbeitszeit anpassen/i })).toBeInTheDocument();
  });

  // Abschluss-Review #431, Fund B (a11y): im Bearbeiten-Zweig trägt die
  // Anzeige-Box ein `<div>`, kein labelable Element — `<label for>` assoziiert
  // sich damit NICHT (nur input/select/textarea/... sind "labelable"). Ohne
  // Fix landet der Wert namenlos im Accessibility-Tree; `getByLabelText`
  // findet ihn deshalb NUR über den neuen `aria-labelledby`.
  it('Fund B: read-only-Anzeigeboxen (Wochenstunden, Arbeitstage) sind über aria-labelledby erreichbar', () => {
    renderForm({ editUser: { ...baseEditUser, work_days_per_week: 4 } });
    const weeklyHoursBox = screen.getByLabelText('Wochenstunden');
    expect(weeklyHoursBox).toBe(document.getElementById('f-weekly-hours'));
    expect(weeklyHoursBox.tagName).not.toBe('INPUT');
    expect(weeklyHoursBox).toHaveTextContent('40,0 h/Woche');

    const workDaysBox = screen.getByLabelText('Arbeitstage pro Woche');
    expect(workDaysBox).toBe(document.getElementById('f-work-days'));
    expect(workDaysBox.tagName).not.toBe('INPUT');
    expect(workDaysBox).toHaveTextContent('4');
  });

  it('Fund B: beim Anlegen bleibt die klassische htmlFor-Assoziation auf den echten Eingabefeldern', () => {
    // Regressions-Gegenprobe: der Fix darf den Create-Zweig (echte <input>s)
    // nicht anfassen — `getByLabelText` muss weiterhin auf `htmlFor` treffen.
    renderForm();
    const weeklyHoursInput = screen.getByLabelText('Wochenstunden');
    expect(weeklyHoursInput.tagName).toBe('INPUT');
    expect(weeklyHoursInput).toBe(document.getElementById('f-weekly-hours'));

    const workDaysInput = screen.getByLabelText('Arbeitstage pro Woche');
    expect(workDaysInput.tagName).toBe('INPUT');
    expect(workDaysInput).toBe(document.getElementById('f-work-days'));
  });

  it('zeigt beim Anlegen ein Eingabefeld (kein Button)', () => {
    renderForm();
    expect(document.getElementById('f-weekly-hours')?.tagName).toBe('INPUT');
    expect(screen.queryByRole('button', { name: /Arbeitszeit anpassen/i })).not.toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: /Arbeitszeit anpassen/i })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: /Arbeitszeit anpassen/i }));
    expect(onOpenHoursHistory).toHaveBeenCalledWith(baseEditUser);
  });

  it('erlaubt alle Felder beim Anlegen', () => {
    renderForm({ editUser: null });
    expect(screen.getByLabelText('Wochenstunden')).toBeEnabled();
  });
});

describe('Bug-Tracker #4: Schrittweite der geplanten Arbeitszeit', () => {
  it('nimmt Viertelstunden beim Anlegen an — wie der Bearbeiten-Dialog (Fund C, #431)', () => {
    // step="0.5" wies 20,25 h beim ANLEGEN als Schrittfehler ab, während
    // dieselbe Zahl über "Arbeitszeit anpassen…" längst gespeichert werden
    // konnte. Zwei Wege zum selben Feld dürfen nicht verschieden streng sein.
    renderForm({ editUser: null });
    expect(document.getElementById('f-weekly-hours')).toHaveAttribute('step', '0.25');
  });

  it('erlaubt bei der Monatsarbeitszeit eine Nachkommastelle (= Genauigkeit der Spalte)', () => {
    // Der eigene Vorschlagswert (Wochenstunden × 13/3 ≈ 86,7) fiel bei step="0.5"
    // durch die native Schrittprüfung.
    renderForm({ editUser: null });
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    expect(document.getElementById('f-agreed-monthly')).toHaveAttribute('step', '0.1');
  });
});

describe('Bug-Tracker #3: Kalenderfarben-Kacheln überdecken den Text nicht', () => {
  it('hält eine feste Kachelgröße statt einer an der Spaltenbreite hängenden', () => {
    // `w-full aspect-square` im Raster machte die Kacheln so hoch wie die
    // Spalte breit war — im breiten Formular (bzw. bei Browser-Zoom, wo die
    // sm:-Stufe wegfällt) wuchsen sie über Label und Hilfetext.
    renderForm({ editUser: null });
    const swatch = screen.getByLabelText('Farbe Blau');
    expect(swatch.className).toContain('h-10');
    expect(swatch.className).toContain('w-10');
    expect(swatch.className).not.toContain('aspect-square');
    expect(swatch.className).not.toContain('w-full');
  });
});

describe('Spec 2026-10-08 (PR1): Arbeitszeit-Blöcke statt Soll-Fenster', () => {
  const baseEditUser = {
    id: 'u1', username: 'jd', first_name: 'Jane', last_name: 'Doe', role: 'employee',
    weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
    is_active: true, use_daily_schedule: false,
  };
  const empty = { blocks: [], pause_minutes: 0 };
  const TWO_BLOCKS = [
    { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
    empty, empty, empty, empty,
  ];
  const legacyEmpty = { blocks: [], pause_minutes: null };
  const LEGACY = [
    { blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
    legacyEmpty, legacyEmpty, legacyEmpty,
    { blocks: [{ start: '07:30', end: '23:59' }], pause_minutes: null },
  ];

  async function fillAndSave() {
    fireEvent.change(screen.getByLabelText(/Benutzername/i), { target: { value: 'newemployee' } });
    fireEvent.change(screen.getByLabelText('Passwort *'), { target: { value: 'TestPass123!' } });
    fireEvent.change(screen.getByLabelText('Vorname'), { target: { value: 'New' } });
    fireEvent.change(screen.getByLabelText('Nachname'), { target: { value: 'User' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
  }

  it('zeigt keine Soll-Fenster-Felder mehr (Anlegen und Bearbeiten)', () => {
    const { unmount } = renderForm();
    expect(screen.queryByLabelText(/Soll-Beginn/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Soll-Arbeitszeiten je Wochentag/)).not.toBeInTheDocument();
    unmount();
    renderForm({ editUser: baseEditUser });
    expect(screen.queryByLabelText(/Soll-Ende/)).not.toBeInTheDocument();
  });

  it('POST-Payload trägt keinen Schlüssel mit Präfix scheduled_ (sonst 400)', async () => {
    renderForm();
    await fillAndSave();
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const keys = Object.keys(postMock.mock.calls[0][1] as object);
    expect(keys.filter((k) => k.startsWith('scheduled_'))).toEqual([]);
    expect(keys).not.toContain('work_blocks');
  });

  it('PUT-Payload trägt weder scheduled_* noch work_blocks/work_blocks_today (sonst 400)', async () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks: LEGACY, work_blocks_today: LEGACY } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      const keys = Object.keys(call![1] as object);
      expect(keys.filter((k) => k.startsWith('scheduled_'))).toEqual([]);
      expect(keys).not.toContain('work_blocks');
      expect(keys).not.toContain('work_blocks_today');
    });
  });

  it('zeigt beim Bearbeiten die heute gültigen Blöcke (displayBlocks)', () => {
    renderForm({ editUser: baseEditUser, displayBlocks: TWO_BLOCKS });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent(
      'Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min)',
    );
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('kennzeichnet ein Altfenster aus Migration 073 und zeigt Altwerte unverändert', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY } });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Mo 07:37–16:30 · Fr 07:30–23:59');
    expect(screen.getByText(/Altbestand: kappt die erfasste Zeit/)).toBeInTheDocument();
  });

  // E63/P2: ohne Stundenzählung kappt das Backend nie (`_clamp_core`/`clamp_applies`
  // brechen bei track_hours=False ab), 073 übernimmt Altfenster aber unabhängig davon.
  // Der Kappungs-Hinweis wäre dort eine falsche Aussage.
  it('Altfenster bei track_hours=false: kein Kappungs-Hinweis, sondern „ohne Wirkung"', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false, work_blocks_today: LEGACY } });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Mo 07:37–16:30 · Fr 07:30–23:59');
    expect(screen.queryByText(/kappt die erfasste Zeit/)).not.toBeInTheDocument();
    expect(screen.getByText(/Altbestand gespeichert, ohne Wirkung \(keine Stundenzählung\)/)).toBeInTheDocument();
  });

  it('Blöcke bei track_hours=false: „gespeichert, ohne Wirkung" (Wortlaut wie im Dialog, Spec 12.1)', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false }, displayBlocks: TWO_BLOCKS });
    expect(screen.getByText('Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung).')).toBeInTheDocument();
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('Hinweis folgt dem Haken „Stundenzählung aktiv" im Formular', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY } });
    expect(screen.getByText(/Altbestand: kappt die erfasste Zeit/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Stundenzählung aktiv/));
    expect(screen.queryByText(/kappt die erfasste Zeit/)).not.toBeInTheDocument();
    expect(screen.getByText(/Altbestand gespeichert, ohne Wirkung/)).toBeInTheDocument();
  });

  it('ohne Blöcke bei track_hours=false: kein „ohne Wirkung"-Hinweis', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false }, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
    expect(screen.queryByText(/ohne Wirkung/)).not.toBeInTheDocument();
  });

  it('ohne Blöcke: „Keine Arbeitszeit-Blöcke hinterlegt"', () => {
    renderForm({ editUser: baseEditUser, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
  });

  // Vorrangregel nach dem Muster `displayDayHours` (Spec 12.2, vgl. #431 Fund 3):
  // ein frisch nachgeführtes `displayBlocks = null` (Fenster entfernt, Verlaufszeile
  // gelöscht) schlägt den beim Öffnen übergebenen Stand. Ein `??` an dieser Stelle
  // fiele auf das alte Altfenster samt Altbestand-Hinweis zurück.
  it('frisches displayBlocks=null schlägt veraltete editUser.work_blocks_today', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY }, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('beim Anlegen keine Blöcke-Anzeige (der Editor folgt mit PR3)', () => {
    renderForm();
    expect(screen.queryByLabelText('Arbeitszeit heute')).not.toBeInTheDocument();
  });
});

describe('Spec 2026-10-08 (12.2): Anlegen mit Arbeitszeit-Blöcken', () => {
  function fillBasics() {
    fireEvent.change(screen.getByLabelText(/Benutzername/i), { target: { value: 'blockneu' } });
    fireEvent.change(screen.getByLabelText('Passwort *'), { target: { value: 'TestPass123!' } });
    fireEvent.change(screen.getByLabelText('Vorname'), { target: { value: 'Anna' } });
    fireEvent.change(screen.getByLabelText('Nachname'), { target: { value: 'Beispiel' } });
  }

  function enterAnnaMonday() {
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '15:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
  }

  it('drei Modi; „Nach Arbeitsblöcken" zeigt den Editor und leitet Wochenstunden/Arbeitstage schreibgeschützt ab', () => {
    renderForm({ editUser: null });
    expect(screen.getByRole('radio', { name: 'Gleichmäßig' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Nach Tagen' })).not.toBeChecked();
    enterAnnaMonday();
    expect(screen.getByTestId('f-blocks-day-0')).toHaveTextContent('Tagessoll 6:30 h');
    const weekly = document.getElementById('f-weekly-hours') as HTMLInputElement;
    expect(weekly).toHaveAttribute('readonly');
    expect(weekly.value).toBe('6.5');
    const workDays = document.getElementById('f-work-days') as HTMLInputElement;
    expect(workDays).toHaveAttribute('readonly');
    expect(workDays.value).toBe('1');
  });

  it('sendet work_blocks samt abgeleiteten Feldern (der Server leitet erneut ab, 4.2)', async () => {
    renderForm({ editUser: null });
    fillBasics();
    enterAnnaMonday();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const body = postMock.mock.calls[0][1];
    expect(body).toMatchObject({
      use_daily_schedule: true, weekly_hours: 6.5, work_days_per_week: 1, hours_monday: 6.5, hours_tuesday: 0,
    });
    expect(body.work_blocks[0]).toEqual({
      blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30,
    });
    expect(body.work_blocks[1]).toEqual({ blocks: [], pause_minutes: 0 });
  });

  it('sperrt Speichern bei ungültigen Blöcken mit der wortgleichen Meldung (3.4)', () => {
    renderForm({ editUser: null });
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Mindestens ein Wochentag braucht einen Block.');
    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
  });

  it('ohne Stundenzählung: Editor ausgeblendet, keine Blöcke im Payload', async () => {
    renderForm({ editUser: null });
    fillBasics();
    enterAnnaMonday();
    fireEvent.click(screen.getByLabelText('Stundenzählung aktiv (Soll-Stunden werden berechnet)'));
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).not.toHaveProperty('work_blocks');
  });

  // Das Formular darf sich nicht selbst widersprechen: zeigt das Feld
  // „Arbeitstage pro Woche" 1 (aus den Blöcken), muss die Urlaubsempfehlung
  // ebenfalls mit 1 rechnen — nicht mit den verdeckten Formularwerten 40 h/5 Tage.
  it('Urlaubsempfehlung, MiLoG-Schätzung und Festmonats-Hinweis folgen den abgeleiteten Werten', () => {
    renderForm({ editUser: null });
    enterAnnaMonday();
    // 30 × 1/5 = 6 Tage
    expect(screen.getByText(/6 Tage \(basierend auf 1 Arbeitstagen\/Woche\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    // 6,5 h × 13/3 ≈ 28,2 h
    expect(screen.getByText(/aus den Wochenstunden \(≈ 28\.2 h\)/)).toBeInTheDocument();
    expect(document.getElementById('f-agreed-monthly')).toHaveAttribute('placeholder', 'aus Wochenstunden ≈ 28.2');
    fireEvent.click(screen.getByLabelText(/Feste Monatsarbeitszeit/));
    // Die Blöcke hinterlegen die geplante Anwesenheit bereits.
    expect(screen.queryByText(/Empfehlung bei fester Monatsarbeitszeit/)).not.toBeInTheDocument();
  });

  it('Bearbeiten: Knopf heißt „Arbeitszeit anpassen…", kein Modus-Umschalter', () => {
    renderForm({ editUser: baseEditUser });
    expect(screen.getByRole('button', { name: 'Arbeitszeit anpassen…' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
  });
});

// Gesamtreview 1.20 (Fund 6): das Formular kennt den Block-Modus auch in seinen
// Texten. Bearbeiten: Modus „Nach Arbeitsblöcken" und der Blocksatz wie im
// Dialog-Kopf (describeSchedule) statt „Individuelle Tagesstunden aktiv" und
// dezimalem Tagesplan. Anlegen: unter den schreibgeschützten Feldern steht, dass
// sie abgeleitet sind — nicht die Eingabeanleitung „(1-7)".
describe('Gesamtreview 1.20 Fund 6: Texte im Block-Modus', () => {
  const empty = { blocks: [], pause_minutes: 0 };
  const ANNA = [
    { blocks: [{ start: '07:30', end: '12:00' }, { start: '13:00', end: '16:25' }], pause_minutes: 0 },
    empty, empty, empty, empty,
  ];
  const blockUser = {
    id: 'u1', username: 'ab', first_name: 'Anna', last_name: 'Block', role: 'employee',
    weekly_hours: 7.92, vacation_days: 30, work_days_per_week: 1, track_hours: true,
    is_active: true, use_daily_schedule: true,
    hours_monday: 7.92, hours_tuesday: 0, hours_wednesday: 0, hours_thursday: 0, hours_friday: 0,
  };
  const display = {
    displayBlocks: ANNA, displayWeeklyHours: 7.92, displayUseDailySchedule: true,
    displayDayHours: [7.92, 0, 0, 0, 0], displayWorkDays: 1,
  };

  it('Bearbeiten: Modus „Nach Arbeitsblöcken" und Blocksatz statt dezimalem Tagesplan', () => {
    renderForm({ editUser: blockUser, ...display });
    expect(document.getElementById('f-weekly-hours')).toHaveTextContent(
      'Mo 07:30–12:00 + 13:00–16:25 = 7,92 h/Woche',
    );
    expect(screen.queryByText(/Mo 7,92/)).not.toBeInTheDocument();
    expect(screen.getByText('Nach Arbeitsblöcken')).toBeInTheDocument();
    expect(screen.queryByText('Individuelle Tagesstunden aktiv')).not.toBeInTheDocument();
    expect(screen.getByText(/Wird aus den Arbeitszeit-Blöcken abgeleitet/)).toBeInTheDocument();
    expect(screen.queryByText(/im Tagesplan abgeleitet/)).not.toBeInTheDocument();
  });

  it('Bearbeiten mit fester Monatsarbeitszeit: „Nach Arbeitsblöcken (geplante Anwesenheit)"', () => {
    renderForm({
      editUser: { ...blockUser, milog_working_time_account: true, agreed_monthly_hours: 40, use_fixed_monthly_target: true },
      ...display,
    });
    expect(screen.getByText('Nach Arbeitsblöcken (geplante Anwesenheit)')).toBeInTheDocument();
    expect(screen.queryByText('Geplante Anwesenheit aktiv')).not.toBeInTheDocument();
  });

  it('Kontrolle: Altfenster ist kein Block-Modus (der Dialog nennt es nie „Blöcke")', () => {
    const legacyEmpty = { blocks: [], pause_minutes: null };
    const LEGACY = [{ blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
      legacyEmpty, legacyEmpty, legacyEmpty, legacyEmpty];
    renderForm({
      editUser: { ...blockUser, use_daily_schedule: false, weekly_hours: 40, work_days_per_week: 5 },
      displayBlocks: LEGACY,
    });
    expect(screen.getByText('Einheitliche Tagesstunden (kein individueller Tagesplan)')).toBeInTheDocument();
    expect(screen.queryByText('Nach Arbeitsblöcken')).not.toBeInTheDocument();
    expect(document.getElementById('f-weekly-hours')).toHaveTextContent('40,0 h/Woche');
  });

  it('Kontrolle: ohne Stundenzählung bleibt der Satz ohne Blöcke (wie describeSchedule)', () => {
    renderForm({ editUser: { ...blockUser, track_hours: false }, ...display });
    expect(document.getElementById('f-weekly-hours')).not.toHaveTextContent('07:30');
  });

  it('Anlegen im Block-Modus: beide Felder beschreiben sich als abgeleitet, keine Eingabeanleitung', () => {
    renderForm({ editUser: null });
    expect(screen.getByText('Anzahl der Arbeitstage pro Woche (1-7)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    expect(screen.queryByText('Anzahl der Arbeitstage pro Woche (1-7)')).not.toBeInTheDocument();
    expect(document.getElementById('f-weekly-hours')).toHaveAccessibleDescription(
      'Aus den Arbeitszeit-Blöcken abgeleitet.',
    );
    expect(document.getElementById('f-work-days')).toHaveAccessibleDescription(
      'Aus den Arbeitszeit-Blöcken abgeleitet (Tage mit Blöcken).',
    );
  });
});

// Gesamtreview 1.20 (Fund 14): Anlegen mit fester Monatsarbeitszeit und Blöcken —
// der Editor nennt die Werte „geplant", der Hinweis darunter kein Tagessoll.
describe('Gesamtreview 1.20 Fund 14: Block-Editor beim Anlegen mit fester Monatsarbeitszeit', () => {
  it('beschriftet die Blöcke als geplante Anwesenheit', () => {
    renderForm({ editUser: null });
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    fireEvent.change(screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/), { target: { value: '40' } });
    fireEvent.click(screen.getByLabelText(/Feste Monatsarbeitszeit/));
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    expect(screen.getByTestId('f-blocks-day-0')).toHaveTextContent('geplant 4:00 h');
    expect(screen.getByTestId('f-blocks-week')).toHaveTextContent('geplant 4:00 h');
    expect(screen.getByText(
      'Wochenstunden, geplante Anwesenheit und Arbeitstage werden aus den Blöcken abgeleitet; das Monats-Soll bleibt die vereinbarte Monatsarbeitszeit.',
    )).toBeInTheDocument();
    expect(screen.queryByText(/Tagessoll und Arbeitstage werden aus den Blöcken abgeleitet/)).not.toBeInTheDocument();
  });

  it('Kontrolle: ohne feste Monatsarbeitszeit „Tagessoll"', () => {
    renderForm({ editUser: null });
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    expect(screen.getByTestId('f-blocks-day-0')).toHaveTextContent('Tagessoll 4:00 h');
    expect(screen.getByText('Wochenstunden, Tagessoll und Arbeitstage werden aus den Blöcken abgeleitet.')).toBeInTheDocument();
  });
});

// Gesamtreview 1.20 (Fund 25, Nachzug): Urlaubsempfehlung und MiLoG-Schätzung
// rechnen beim Bearbeiten mit dem heute gültigen Vertragsstand — wie die
// Anzeigen daneben. Die User-Zeile (40 h / 5 Tage) zieht eine zukunftsdatierte
// Änderung erst beim nächsten Schreibvorgang nach; heute gelten 32 h / 4 Tage.
// Vorher stand „Arbeitstage 4" neben „Empfehlung: 30 Tage (basierend auf 5
// Arbeitstagen/Woche)", und „Übernehmen" schrieb 30 Tage für eine 4-Tage-Woche.
describe('Gesamtreview 1.20 Fund 25: Empfehlung und MiLoG-Schätzung aus dem heute gültigen Stand', () => {
  const today = {
    weekly_hours: 32, use_daily_schedule: false, work_days_per_week: 4,
    hours_monday: null, hours_tuesday: null, hours_wednesday: null, hours_thursday: null, hours_friday: null,
  };
  const rowUser = {
    id: 'u1', username: 'jd', first_name: 'Jane', last_name: 'Doe', role: 'employee',
    weekly_hours: 40, vacation_days: 20, work_days_per_week: 5, track_hours: true,
    is_active: true, use_daily_schedule: false, milog_working_time_account: true,
    schedule_today: today,
  };

  beforeEach(() => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', minimum_wage: { current: 13.9, since: '2026-01-01', next: null } },
      isLoaded: true,
    } as never);
  });

  function expectToday() {
    expect(document.getElementById('f-work-days')?.textContent).toBe('4');
    expect(document.getElementById('f-weekly-hours')).toHaveTextContent('32,0 h/Woche');
    // 30 × 4/5 = 24 Tage
    expect(screen.getByText(/24 Tage \(basierend auf 4 Arbeitstagen\/Woche\)/)).toBeInTheDocument();
    expect(screen.queryByText(/basierend auf 5 Arbeitstagen/)).not.toBeInTheDocument();
    // 32 h × 13/3 ≈ 138,7 h (so rechnet auch milog_service.agreed_monthly_hours)
    expect(screen.getByText(/aus den Wochenstunden \(≈ 138\.7 h\)/)).toBeInTheDocument();
    expect(document.getElementById('f-agreed-monthly')).toHaveAttribute('placeholder', 'aus Wochenstunden ≈ 138.7');
    expect(screen.queryByText(/173\.3/)).not.toBeInTheDocument();
  }

  it('mit den display*-Props aus Users.tsx', () => {
    renderForm({
      editUser: rowUser,
      displayWeeklyHours: 32, displayWorkDays: 4, displayUseDailySchedule: false,
      displayDayHours: [null, null, null, null, null],
    });
    expectToday();
  });

  it('ohne display*-Props aus editUser.schedule_today (nicht aus der User-Zeile)', () => {
    renderForm({ editUser: rowUser });
    expectToday();
    expect(screen.getByText('Einheitliche Tagesstunden (kein individueller Tagesplan)')).toBeInTheDocument();
  });

  it('ohne display*-Props: Modus und Tagesplan ebenfalls aus schedule_today', () => {
    renderForm({
      editUser: {
        ...rowUser,
        schedule_today: {
          ...today, use_daily_schedule: true, weekly_hours: 17, work_days_per_week: 3,
          hours_monday: 8, hours_tuesday: 5, hours_wednesday: 4, hours_thursday: 0, hours_friday: 0,
        },
      },
    });
    expect(screen.getByText('Individuelle Tagesstunden aktiv')).toBeInTheDocument();
    expect(screen.getByText('Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche')).toBeInTheDocument();
    expect(document.getElementById('f-work-days')?.textContent).toBe('3');
  });

  it('„Übernehmen" schreibt die Empfehlung für die heute gültige Woche', async () => {
    renderForm({ editUser: rowUser });
    fireEvent.click(screen.getByRole('button', { name: 'Übernehmen' }));
    expect((screen.getByLabelText('Urlaubstage') as HTMLInputElement).value).toBe('24');
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      expect(call![1]).toMatchObject({ vacation_days: 24 });
    });
  });

  it('Kontrolle: ohne schedule_today (ältere Antwort) gilt weiter die User-Zeile', () => {
    renderForm({ editUser: { ...rowUser, schedule_today: undefined } });
    expect(screen.getByText(/30 Tage \(basierend auf 5 Arbeitstagen\/Woche\)/)).toBeInTheDocument();
    expect(screen.getByText(/aus den Wochenstunden \(≈ 173\.3 h\)/)).toBeInTheDocument();
  });
});
