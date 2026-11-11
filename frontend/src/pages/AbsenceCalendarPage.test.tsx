import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { format, subDays } from 'date-fns';
import { MemoryRouter } from 'react-router-dom';
import AbsenceCalendarPage from './AbsenceCalendarPage';

// F042 (Teil B, Spec B5 „Kalenderlabel"): der Kalender lädt die verkürzten Tage
// des angezeigten Jahres über GET /reduced-days?year= und zeigt ihr Label.

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a), put: vi.fn(), delete: vi.fn(),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));
vi.mock('../api/absenceReasons', () => ({ myReasons: () => Promise.resolve([]) }));
const USER = {
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

function mockApi({ settingsFail = false, absences = [] as unknown[] } = {}) {
  getMock.mockImplementation((raw: unknown) => {
    const url = String(raw);
    if (url.startsWith('/absences?year=')) return Promise.resolve({ data: absences });
    if (url === '/settings') {
      return settingsFail
        ? Promise.reject(new Error('offline'))
        : Promise.resolve({ data: { vacation_approval_required: false, special_days: {
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

beforeEach(() => getMock.mockReset());

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
