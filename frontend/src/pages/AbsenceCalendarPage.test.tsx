import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AbsenceCalendarPage from './AbsenceCalendarPage';

// F042 (Teil B, Spec B5 „Kalenderlabel"): der Kalender lädt die verkürzten Tage
// des angezeigten Jahres über GET /reduced-days?year= und zeigt ihr Label.

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: vi.fn(), put: vi.fn(), delete: vi.fn(),
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

function mockApi({ settingsFail = false } = {}) {
  getMock.mockImplementation((raw: unknown) => {
    const url = String(raw);
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
