import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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

// #494: „x von y h heute" zählte nur die Laufzeit des OFFENEN Eintrags
// (`elapsed_minutes`). Geteilte Dienste verloren den Vormittag, nach dem
// Ausstempeln stand 0:00. Das Tages-Ist kommt jetzt als `today_net_minutes`,
// das Tagessoll als `today_target_hours` (Snapshot #431) aus /clock-status.
describe('Dashboard Stempelkarte „x von y h heute" (#494)', () => {
  function withClockStatus(data: unknown) {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status' ? Promise.resolve({ data }) : base(url),
    );
  }

  it('zählt abgeschlossene Blöcke des Tages mit, auch ohne offenen Eintrag', async () => {
    withClockStatus({
      is_clocked_in: false, elapsed_minutes: null,
      today_net_minutes: 424, today_target_hours: 7,
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('7:04 von 7:00 h heute')).toBeInTheDocument();
    // Wer heute schon gearbeitet hat, ist nicht „noch nicht eingestempelt".
    expect(screen.queryByText('Noch nicht eingestempelt')).not.toBeInTheDocument();
    expect(screen.getByText('Ausgestempelt')).toBeInTheDocument();
  });

  it('addiert im Nachmittagsblock den Vormittag (nicht nur die laufenden Minuten)', async () => {
    withClockStatus({
      is_clocked_in: true, elapsed_minutes: 70,
      current_entry: { start_time: '14:17:00' },
      today_net_minutes: 331, today_target_hours: 7,
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('5:31 von 7:00 h heute')).toBeInTheDocument();
    // (Die Desktop-Stempeluhr zeigt denselben Text, daher getAll.)
    expect(screen.getAllByText('Eingestempelt seit 14:17').length).toBeGreaterThan(0);
  });

  it('zeigt am arbeitsfreien Tag keinen Fortschrittsbalken', async () => {
    withClockStatus({
      is_clocked_in: false, elapsed_minutes: null,
      today_net_minutes: 0, today_target_hours: 0,
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
    expect(within(card).getByText('Nicht eingestempelt')).toBeInTheDocument();
    expect(within(card).queryByRole('progressbar')).not.toBeInTheDocument();
    expect(within(card).queryByText(/h heute$/)).not.toBeInTheDocument();
  });

  it('nimmt das Tagessoll aus der API, nicht aus der User-Zeile', async () => {
    withClockStatus({
      is_clocked_in: false, elapsed_minutes: null,
      today_net_minutes: 0, today_target_hours: 4.5,
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('0:00 von 4:30 h heute')).toBeInTheDocument();
    expect(screen.getByText('Noch nicht eingestempelt')).toBeInTheDocument();
  });
});

// #500: Umschalter Monat/Woche wie im Admin-Dashboard. Vergessene Nachmittage
// fallen pro Woche sofort auf, im Monat gehen sie unter.
describe('Dashboard Übersicht Monat/Woche (#500)', () => {
  const HISTORY = [
    { year: 2026, month: 9, target: 60, actual: 63.98, balance: 3.98, cumulative: 7.27 },
    { year: 2026, month: 10, target: 20, actual: 22.65, balance: 2.65, cumulative: 9.92 },
  ];
  // Wie die API: älteste Woche zuerst.
  const WEEKS = [
    { week_start: '2026-09-28', week_end: '2026-10-04', iso_year: 2026, iso_week: 40,
      target: 40, actual: 36, balance: -4, cumulative: -4 },
    { week_start: '2026-10-05', week_end: '2026-10-11', iso_year: 2026, iso_week: 41,
      target: 24, actual: 24.5, balance: 0.5, cumulative: -3.5 },
  ];

  function withOverview() {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) => {
      if (url === '/dashboard/overtime') {
        return Promise.resolve({ data: { current_balance: 9.92, history: HISTORY } });
      }
      if (url === '/dashboard/weekly-overview') return Promise.resolve({ data: WEEKS });
      return base(url);
    });
  }

  function overviewTable(): HTMLTableElement {
    return screen.getByRole('region', { name: /übersicht$/ }).querySelector('table')!;
  }

  // Zelltext; die Wochen-Zelle besteht aus zwei Zeilen („KW 41" / Spanne),
  // die hier mit Leerzeichen verbunden werden.
  function cellText(td: Element): string {
    return td.children.length >= 2
      ? Array.from(td.children).map((el) => el.textContent ?? '').join(' ')
      : td.textContent ?? '';
  }

  function rowsText(table: HTMLTableElement): string[][] {
    return Array.from(table.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td')).map(cellText),
    );
  }

  function firstCells(table: HTMLTableElement): string[] {
    return rowsText(table).map((r) => r[0]);
  }

  beforeEach(() => {
    try { localStorage.removeItem('dashboardOverviewViewMode'); } catch { /* ignore */ }
    // Die Spanne lässt im laufenden Jahr die Jahreszahl weg → „heute" festnageln
    // (nur Date; echte Timer für findBy/waitFor).
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-08T10:00:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('zeigt standardmäßig die Monatsübersicht und lädt keine Wochen', async () => {
    withOverview();
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByRole('heading', { name: 'Monatsübersicht' })).toBeInTheDocument();
    expect(firstCells(overviewTable())).toEqual(['Oktober 2026', 'September 2026']);
    expect(screen.getByRole('button', { name: 'Monat' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Woche' })).toHaveAttribute('aria-pressed', 'false');
    expect(getMock).not.toHaveBeenCalledWith('/dashboard/weekly-overview');
  });

  it('schaltet auf die Wochenübersicht um, neueste Woche zuerst', async () => {
    withOverview();
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    fireEvent.click(await screen.findByRole('button', { name: 'Woche' }));

    expect(await screen.findByRole('heading', { name: 'Wochenübersicht' })).toBeInTheDocument();
    await waitFor(() =>
      expect(firstCells(overviewTable())).toEqual([
        'KW 41 05.–11.10.',
        'KW 40 28.09.–04.10.',
      ]),
    );
    expect(rowsText(overviewTable())).toEqual([
      ['KW 41 05.–11.10.', '24:00h', '24:30h', '+0:30h', '-3:30h'],
      ['KW 40 28.09.–04.10.', '40:00h', '36:00h', '-4:00h', '-4:00h'],
    ]);
    expect(within(overviewTable()).getAllByRole('columnheader')[0]).toHaveTextContent('Woche');
    expect(screen.getByRole('button', { name: 'Woche' })).toHaveAttribute('aria-pressed', 'true');
    expect(getMock).toHaveBeenCalledWith('/dashboard/weekly-overview');
  });

  it('nennt die Jahreszahl außerhalb des laufenden Jahres und über den Jahreswechsel', async () => {
    vi.setSystemTime(new Date('2027-01-02T10:00:00'));
    withOverview();
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/dashboard/weekly-overview'
        ? Promise.resolve({ data: [
            { week_start: '2026-12-21', week_end: '2026-12-27', iso_year: 2026, iso_week: 52,
              target: 32, actual: 32, balance: 0, cumulative: 1 },
            { week_start: '2026-12-28', week_end: '2027-01-03', iso_year: 2026, iso_week: 53,
              target: 16, actual: 16, balance: 0, cumulative: 1 },
          ] })
        : base(url),
    );
    localStorage.setItem('dashboardOverviewViewMode', 'week');
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    await screen.findByRole('heading', { name: 'Wochenübersicht' });
    await waitFor(() => expect(firstCells(overviewTable())).toEqual([
      'KW 53 28.12.2026–03.01.2027',
      'KW 52 21.–27.12.2026',
    ]));
  });

  it('merkt sich die Auswahl pro Browser', async () => {
    withOverview();
    localStorage.setItem('dashboardOverviewViewMode', 'week');
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByRole('heading', { name: 'Wochenübersicht' })).toBeInTheDocument();
    await waitFor(() => expect(firstCells(overviewTable())[0]).toBe('KW 41 05.–11.10.'));

    fireEvent.click(screen.getByRole('button', { name: 'Monat' }));
    expect(localStorage.getItem('dashboardOverviewViewMode')).toBe('month');
    expect(await screen.findByRole('heading', { name: 'Monatsübersicht' })).toBeInTheDocument();
  });
});

// Spec 2026-10-08, 14 / E69: eine geplante Pause zwischen zwei Arbeitsblöcken
// ist kein Fehlverhalten — die Stempelkarte wird dort nicht rot.
describe('Dashboard Stempelkarte in der Lücke zwischen den Arbeitsblöcken (Spec 14, E69)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function at(iso: string) {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(iso));
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: false, elapsed_minutes: null, today_net_minutes: 0,
          today_target_hours: 7, blocks_today: BLOCKS, grace_minutes: 15,
        } })
        : base(url));
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it.each(['2026-06-01T12:00:00', '2026-06-01T12:05:00', '2026-06-01T13:00:00'])(
    'zeigt um %s neutral „Pause zwischen den Arbeitsblöcken"', async (iso) => {
      at(iso);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Pause zwischen den Arbeitsblöcken')).toBeInTheDocument());
      expect(within(card).queryByText('Noch nicht eingestempelt')).not.toBeInTheDocument();
      expect(card.className).not.toMatch(/bg-danger/);
    },
  );

  it.each(['2026-06-01T15:00:00', '2026-06-01T07:30:00'])(
    'um %s (Blockbeginn bzw. vor dem ersten Block) bleibt das bisherige Verhalten', async (iso) => {
      at(iso);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Noch nicht eingestempelt')).toBeInTheDocument());
    },
  );
});
