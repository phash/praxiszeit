import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from './Dashboard';

// Backlog item (Audit 2026-07-31): vacation-day counts were rendered with
// `.toFixed(1)` (English decimal point, "26.5 Tage") right next to hour
// values formatted with the German comma elsewhere in the app. Fix reuses
// the existing `deHoursExact` helper (utils/formatters.ts) instead of
// inventing a second formatting rule.

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  // authStore.ts pulls these named exports in transitively — never invoked
  // in this test, but the mock module must expose them so the import
  // itself doesn't blow up (pattern from Users.test.tsx).
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

const VACATION_ACCOUNT = {
  year: 2026,
  budget_hours: 0,
  budget_days: 27.5,
  used_hours: 0,
  used_days: 3.5,
  remaining_hours: 0,
  remaining_days: 26.5,
};

function mockDashboardEndpoints() {
  getMock.mockImplementation((url: string) => {
    if (url === '/dashboard') {
      return Promise.resolve({ data: { year: 2026, month: 7, target_hours: 0, actual_hours: 0, balance: 0 } });
    }
    if (url === '/dashboard/overtime') {
      return Promise.resolve({ data: { current_balance: 0, history: [] } });
    }
    if (url === '/dashboard/vacation') {
      return Promise.resolve({ data: VACATION_ACCOUNT });
    }
    if (url === '/absences/team/upcoming') {
      return Promise.resolve({ data: [] });
    }
    if (url === '/absences') {
      return Promise.resolve({ data: [] });
    }
    if (url === '/absences/next-vacation') {
      return Promise.resolve({ data: null });
    }
    if (url === '/dashboard/ytd-overtime') {
      return Promise.resolve({ data: { year: 2026, target_hours: 0, actual_hours: 0, overtime: 0, carryover_hours: 0 } });
    }
    if (url === '/dashboard/missing-bookings') {
      return Promise.resolve({ data: { entries: [] } });
    }
    if (url === '/time-entries/clock-status') {
      return Promise.resolve({ data: { is_clocked_in: false } });
    }
    if (url.startsWith('/time-entries')) {
      return Promise.resolve({ data: [] });
    }
    return Promise.resolve({ data: null });
  });
}

beforeEach(() => {
  getMock.mockReset();
  mockDashboardEndpoints();
  // Deliberately no useAuthStore.setState() here: the persist middleware's
  // setItem() crashes in this sandbox's Node/jsdom combination whenever
  // *anything* writes to the store (pre-existing, unrelated environment gap —
  // see the ~20 known authStore/ImpersonationBanner failures). Dashboard only
  // READS the store (never writes), and its default `user: null` is exactly
  // the state this test wants, so no write is needed.
});

describe('Dashboard vacation-day formatting (Audit 2026-07-31 backlog item)', () => {
  it('renders the vacation account with a German decimal comma, not an English dot', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('Urlaubskonto')).toBeInTheDocument());

    expect(await screen.findByText('26,5 Tage')).toBeInTheDocument();
    expect(screen.getByText('3,5 Tage')).toBeInTheDocument();
    expect(screen.getByText('27,5 Tage')).toBeInTheDocument();

    // The old `.toFixed(1)` output must be gone.
    expect(screen.queryByText('26.5 Tage')).not.toBeInTheDocument();
    expect(screen.queryByText('3.5 Tage')).not.toBeInTheDocument();
    expect(screen.queryByText('27.5 Tage')).not.toBeInTheDocument();
  });
});

// #476: Betriebsferien, die als Ueberstundenausgleich gebucht sind, liessen den
// Countdown leer. Das Backend meldet sie jetzt als kind="closure".
describe('Dashboard Urlaubscountdown mit Praxisschliessung (#476)', () => {
  function withNextVacation(data: unknown) {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/absences/next-vacation' ? Promise.resolve({ data }) : base(url),
    );
  }

  it('zaehlt bis zur Praxisschliessung und nennt sie', async () => {
    withNextVacation({
      date: '2026-10-12', end_date: '2026-10-16', days_until: 14,
      kind: 'closure', closure_name: 'Herbstschließung',
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('Noch 14 Tage bis zur Praxisschließung')).toBeInTheDocument();
    expect(screen.getByText('Herbstschließung')).toBeInTheDocument();
    expect(screen.getByText('16.10.2026')).toBeInTheDocument();
    expect(screen.queryByText('Kein Urlaub geplant')).not.toBeInTheDocument();
  });

  it('meldet den Beginn der Praxisschliessung am selben Tag', async () => {
    withNextVacation({
      date: '2026-10-12', end_date: '2026-10-16', days_until: 0,
      kind: 'closure', closure_name: 'Herbstschließung',
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('Die Praxisschließung hat begonnen!')).toBeInTheDocument();
    expect(screen.queryByText('Heute beginnt dein Urlaub!')).not.toBeInTheDocument();
  });

  it('laesst den Urlaubsfall unveraendert (auch ohne kind aus aelterem Backend)', async () => {
    withNextVacation({ date: '2026-10-05', days_until: 7 });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('Noch 7 Tage')).toBeInTheDocument();
    expect(screen.queryByText(/Praxisschließung/)).not.toBeInTheDocument();
  });
});

// #493: Die Karte „Letzte Einträge" (mobil) nahm `slice(-5).reverse()` auf die
// Monatsliste — das setzt eine AUFSTEIGEND sortierte Antwort voraus. Die API
// liefert aber absteigend (date desc, start_time desc), also standen dort ab der
// zweiten Monatswoche die fünf ÄLTESTEN Einträge.
describe('Dashboard „Letzte Einträge" (#493)', () => {
  function withMonthEntries(entries: unknown[]) {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url.startsWith('/time-entries?month=') ? Promise.resolve({ data: entries }) : base(url),
    );
  }

  const entry = (id: string, date: string, start: string, end: string | null) => ({
    id, date, start_time: start, end_time: end, net_hours: 1,
  });

  // Reihenfolge exakt wie GET /api/time-entries?month=… sie liefert (neueste zuerst).
  const API_DESC = [
    entry('e8b', '2026-10-08', '14:17:00', '17:00:00'),
    entry('e8a', '2026-10-08', '07:43:00', '12:04:00'),
    entry('e6', '2026-10-06', '07:40:00', '12:10:00'),
    entry('e5b', '2026-10-05', '14:14:00', '17:02:00'),
    entry('e5a', '2026-10-05', '07:44:00', '12:01:00'),
    entry('e2', '2026-10-02', '07:39:00', '12:05:00'),
    entry('e1b', '2026-10-01', '14:11:00', '17:00:00'),
    entry('e1a', '2026-10-01', '07:41:00', '12:00:00'),
  ];

  const NEWEST_FIVE = [
    '14:17–17:00',
    '07:43–12:04',
    '07:40–12:10',
    '14:14–17:02',
    '07:44–12:01',
  ];

  async function renderedRanges(): Promise<string[]> {
    const heading = await screen.findByText('Letzte Einträge');
    const card = heading.closest('div')!.parentElement!;
    return Array.from(card.querySelectorAll('span'))
      .map((s) => s.textContent ?? '')
      .filter((t) => /^\d\d:\d\d–/.test(t));
  }

  it('zeigt die fünf NEUESTEN Einträge, neueste zuerst', async () => {
    withMonthEntries(API_DESC);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await renderedRanges()).toEqual(NEWEST_FIVE);
  });

  it('hängt nicht von der Sortierung der API-Antwort ab', async () => {
    withMonthEntries([...API_DESC].reverse());
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await renderedRanges()).toEqual(NEWEST_FIVE);
  });
});
