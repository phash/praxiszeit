import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { format, subDays, addDays } from 'date-fns';
import { MemoryRouter } from 'react-router-dom';
import { de } from 'date-fns/locale';
import AbsenceCalendarPage from './AbsenceCalendarPage';

// F042 (Teil B, Spec B5 „Kalenderlabel"): der Kalender lädt die verkürzten Tage
// des angezeigten Jahres über GET /reduced-days?year= und zeigt ihr Label.

const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
const toastWarning = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a), put: vi.fn(), delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: toastWarning }),
}));
let reasonsData: unknown[] = [];
vi.mock('../api/absenceReasons', () => ({ myReasons: () => Promise.resolve(reasonsData) }));
const USER: Record<string, any> = {
  id: 'u1', username: 'employee', first_name: 'Max', last_name: 'Muster', role: 'employee',
  weekly_hours: 40, vacation_days: 30, track_hours: true, use_daily_schedule: false,
};
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({ user: USER }),
}));

const now = new Date();
const year = now.getFullYear();
const month = String(now.getMonth() + 1).padStart(2, '0');
// Ein Werktag des laufenden Monats (Wochenende hat kein Label, F099).
const weekday = (() => {
  for (let d = 10; d <= 28; d++) {
    const wd = new Date(year, now.getMonth(), d).getDay();
    if (wd !== 0 && wd !== 6) return `${year}-${month}-${String(d).padStart(2, '0')}`;
  }
  throw new Error('kein Werktag');
})();

function mockApi({ settingsFail = false, absences = [] as unknown[], approval = false } = {}) {
  getMock.mockImplementation((raw: unknown) => {
    const url = String(raw);
    if (url.startsWith('/absences?year=')) return Promise.resolve({ data: absences });
    if (url === '/settings') {
      return settingsFail
        ? Promise.reject(new Error('offline'))
        : Promise.resolve({ data: { vacation_approval_required: approval, special_days: {
          special_day_dec24_mode: 'working_day', special_day_dec24_counts_as_vacation: false,
          special_day_dec24_max_hours: 4, special_day_dec31_mode: 'working_day',
          special_day_dec31_counts_as_vacation: false, special_day_dec31_max_hours: 4,
        } } });
    }
    if (url.startsWith('/reduced-days?year=')) {
      const y = url.split('=')[1];
      return Promise.resolve({ data: y === String(year) ? [{ date: weekday, label: 'Rosenmontag', max_hours: 4 }] : [] });
    }
    return Promise.resolve({ data: [] });
  });
}

beforeEach(() => { getMock.mockReset(); postMock.mockReset(); deleteMock.mockReset(); toastWarning.mockReset(); reasonsData = []; });

describe('<AbsenceCalendarPage /> verkürzte Tage', () => {
  it('lädt /reduced-days für das angezeigte Jahr und zeigt das Label', async () => {
    mockApi();
    render(<AbsenceCalendarPage />);
    expect((await screen.findAllByText('Rosenmontag: verkürzter Tag (max. 4 h)')).length).toBeGreaterThan(0);
    expect(getMock).toHaveBeenCalledWith(`/reduced-days?year=${year}`);
  });

  it('lädt beim Jahreswechsel neu', async () => {
    mockApi();
    render(<AbsenceCalendarPage />);
    await screen.findAllByText('Rosenmontag: verkürzter Tag (max. 4 h)');
    // In den Vorjahresmonat Dezember blättern.
    for (let i = 0; i <= now.getMonth(); i++) fireEvent.click(screen.getByRole('button', { name: 'Vorheriger Monat' }));
    await waitFor(() => expect(getMock).toHaveBeenCalledWith(`/reduced-days?year=${year - 1}`));
  });

  it('F133: zeigt die verkürzten Tage auch, wenn /settings scheitert', async () => {
    mockApi({ settingsFail: true });
    render(<AbsenceCalendarPage />);
    expect((await screen.findAllByText('Rosenmontag: verkürzter Tag (max. 4 h)')).length).toBeGreaterThan(0);
  });
});

// P1.1: vergangene eigene Abwesenheiten löschen Mitarbeitende per Antrag. Der
// Link „per Antrag" führte ins Journal, wo es dafür keinen Weg gab.
describe('<AbsenceCalendarPage /> Löschung beantragen (P1.1)', () => {
  const past = format(subDays(new Date(), 3), 'yyyy-MM-dd');
  const sick = { id: 'a1', user_id: 'u1', date: past, end_date: null, type: 'sick', hours: 8, note: null, closure_id: null };

  it('bietet an einer vergangenen Abwesenheit „Löschung beantragen" an und sendet absence_id', async () => {
    mockApi({ absences: [sick] });
    postMock.mockResolvedValue({ data: {} });
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    const buttons = await screen.findAllByRole('button', { name: /Löschung beantragen/ });
    expect(buttons.length).toBeGreaterThan(0);
    fireEvent.click(buttons[0]);
    const dialog = await screen.findByRole('dialog', { name: 'Änderungsantrag: Löschung beantragen' });
    fireEvent.change(within(dialog).getByLabelText(/Begründung/), { target: { value: 'War im Dienst' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Antrag stellen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/change-requests/', {
      request_type: 'delete', entry_kind: 'absence', absence_id: 'a1', reason: 'War im Dienst',
    }));
  });

  it('nicht an Betriebsferien-Tagen (ändert nur die Verwaltung)', async () => {
    mockApi({ absences: [{ ...sick, id: 'c1', type: 'vacation', closure_id: 'cl1' }] });
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    await screen.findAllByText('8:00 h');
    expect(screen.queryByRole('button', { name: /Löschung beantragen/ })).toBeNull();
  });
});

// Voll-Tag-Typen bucht der Server mit dem Tagessoll laut Vertrag; nur
// Überstundenausgleich (auch als eigener Grund) behält die eingegebenen Stunden.
describe('<AbsenceCalendarPage /> Stundenfeld im Formular', () => {
  const reason = (id: string, base_behavior: string) => ({
    id, name: `Grund ${id}`, color: null, base_behavior, is_active: true, sort_order: 0, tracks_child_sick_limit: false,
  });
  async function openForm() {
    mockApi();
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Abwesenheit eintragen' }));
    return (await screen.findByLabelText(/^Stunden/)) as HTMLInputElement;
  }

  it('Urlaub: Feld gesperrt und leer, Hinweis auf Tagessoll', async () => {
    const hours = await openForm();
    expect(hours).toBeDisabled();
    expect(hours.value).toBe('');
    expect(screen.getByText(/Tagessoll laut Vertrag/)).toBeInTheDocument();
  });

  it('Überstundenausgleich: editierbar, Wert wird gesendet, Hinweis nennt Tagesplan', async () => {
    postMock.mockResolvedValue({ data: {} });
    const hours = await openForm();
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'overtime' } });
    expect(hours).not.toBeDisabled();
    expect(screen.getByText(/bei Tagesplan wird das Tagessoll des Tages gebucht/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
    fireEvent.change(hours, { target: { value: '3.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ type: 'overtime', hours: 3.5 });
  });

  it('eigener Grund Überstundenabbau: editierbar; „bezahlt frei": gesperrt mit Halbtag', async () => {
    reasonsData = [reason('r1', 'overtime_comp'), reason('r2', 'paid_free')];
    const hours = await openForm();
    await screen.findByRole('option', { name: 'Grund r1' });
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'reason:r1' } });
    expect(hours).not.toBeDisabled();
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
    fireEvent.change(screen.getByDisplayValue('Grund r1'), { target: { value: 'reason:r2' } });
    expect(hours).toBeDisabled();
    expect(screen.getByLabelText(/Halber Tag/)).toBeInTheDocument();
  });
});

// Code-Review 2026-11-11 (Slice abw)
describe('<AbsenceCalendarPage /> Review abw', () => {
  const openFormEmpty = async (opts: Parameters<typeof mockApi>[0] = {}) => {
    mockApi(opts);
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Abwesenheit eintragen' }));
    return (await screen.findByLabelText(/^Stunden/)) as HTMLInputElement;
  };

  it('abw-07: Öffnen des Formulars scrollt dorthin und fokussiert das Datum', async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    await openFormEmpty();
    await waitFor(() => expect(scroll).toHaveBeenCalled());
    const dateInput = document.querySelector('form input[type="date"]');
    expect(document.activeElement).toBe(dateInput);
  });

  it('abw-11: Admin bucht bei Genehmigungspflicht direkt statt per Antrag', async () => {
    USER.role = 'admin';
    try {
      postMock.mockResolvedValue({ data: [] });
      await openFormEmpty({ approval: true });
      fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
      await waitFor(() => expect(postMock).toHaveBeenCalled());
      expect(postMock.mock.calls[0][0]).toBe('/absences');
    } finally {
      USER.role = 'employee';
    }
  });

  it('abw-11: Mitarbeitende gehen bei Genehmigungspflicht weiter über den Antrag', async () => {
    postMock.mockResolvedValue({ data: {} });
    await openFormEmpty({ approval: true });
    // /settings lädt asynchron — erst absenden, wenn die Pflicht bekannt ist.
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/settings'));
    await new Promise((r) => setTimeout(r, 0));
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][0]).toBe('/vacation-requests');
  });

  it('abw-03: Antrag für einen vergangenen Tag wird gar nicht erst gesendet', async () => {
    await openFormEmpty({ approval: true });
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/settings'));
    await new Promise((r) => setTimeout(r, 0));
    const dateInput = document.querySelector('form input[type="date"]') as HTMLInputElement;
    fireEvent.change(dateInput, { target: { value: format(subDays(new Date(), 5), 'yyyy-MM-dd') } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await new Promise((r) => setTimeout(r, 20));
    expect(postMock).not.toHaveBeenCalled();
  });

  it('abw-08: jede Zeile zeigt ihr eigenes Datum, nicht die Gesamtspanne', async () => {
    const day = addDays(new Date(), 3);
    const span = { id: 'a9', user_id: 'u1', date: format(day, 'yyyy-MM-dd'), end_date: format(addDays(day, 4), 'yyyy-MM-dd'), type: 'training', hours: 8, note: null, closure_id: null };
    mockApi({ absences: [span] });
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    const expected = format(day, 'EEEE, dd.MM.yyyy', { locale: de });
    expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0);
    expect(screen.queryByText(new RegExp(`${format(day, 'dd.MM.yyyy')} - `))).toBeNull();
  });

  it('abw-15: Monatswechsel im selben Jahr lädt die Jahresdaten nicht neu', async () => {
    mockApi();
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    await screen.findByRole('button', { name: 'Vorheriger Monat' });
    await waitFor(() => expect(getMock).toHaveBeenCalledWith(`/absences?year=${year}`));
    const yearCalls = () => getMock.mock.calls.filter((c) => String(c[0]).startsWith('/absences?year=')).length;
    const calendarCalls = () => getMock.mock.calls.filter((c) => String(c[0]).startsWith('/absences/calendar')).length;
    const before = yearCalls();
    const calBefore = calendarCalls();
    fireEvent.click(screen.getByRole('button', { name: now.getMonth() === 0 ? 'Nächster Monat' : 'Vorheriger Monat' }));
    await waitFor(() => expect(calendarCalls()).toBeGreaterThan(calBefore));
    expect(yearCalls()).toBe(before);
  });

  it('abw-10: Krankmeldung über den Jahreswechsel lädt das Nachbarjahr und fragt nach der Urlaubs-Rückgabe', async () => {
    const nextYear = year + 1;
    getMock.mockImplementation((raw: unknown) => {
      const url = String(raw);
      if (url === `/absences?year=${nextYear}`) {
        return Promise.resolve({ data: [{ id: 'v1', date: `${nextYear}-01-02`, type: 'vacation', hours: 8, closure_id: null }] });
      }
      if (url === '/settings') return Promise.resolve({ data: { vacation_approval_required: false } });
      return Promise.resolve({ data: [] });
    });
    postMock.mockResolvedValue({ data: [] });
    render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Abwesenheit eintragen' }));
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'sick' } });
    fireEvent.click(screen.getByLabelText(/Zeitraum/));
    const [von, bis] = Array.from(document.querySelectorAll('form input[type="date"]'));
    fireEvent.change(von, { target: { value: format(addDays(new Date(), 1), 'yyyy-MM-dd') } });
    fireEvent.change(bis, { target: { value: `${nextYear}-01-03` } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    expect(await screen.findByText(/Sollen diese Urlaubstage zurückerstattet werden/)).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(`/absences?year=${nextYear}`);
  });
});

// api-02 (Release-Review 1.24.0): Löschen in einem abgeschlossenen Jahr liefert
// 200 + {warning} (abw-05) — der Kalender zeigt sie wie AdminAbsences.
describe('<AbsenceCalendarPage /> Löschen im abgeschlossenen Jahr', () => {
  it('zeigt die Warnung der Löschantwort', async () => {
    USER.role = 'admin';
    try {
      const past = format(subDays(new Date(), 3), 'yyyy-MM-dd');
      mockApi({ absences: [{ id: 'a1', user_id: 'u1', date: past, end_date: null, type: 'training', hours: 8, note: null, closure_id: null }] });
      deleteMock.mockResolvedValue({ data: { warning: 'Jahr ist abgeschlossen.' } });
      render(<MemoryRouter><AbsenceCalendarPage /></MemoryRouter>);
      fireEvent.click((await screen.findAllByRole('button', { name: 'Abwesenheit löschen' }))[0]);
      const dialog = await screen.findByRole('alertdialog');
      fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));
      await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/absences/a1'));
      await waitFor(() => expect(toastWarning).toHaveBeenCalledWith('Jahr ist abgeschlossen.'));
    } finally {
      USER.role = 'employee';
    }
  });
});
