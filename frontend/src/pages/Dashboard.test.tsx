import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import Dashboard from './Dashboard';
import { useUIStore } from '../stores/uiStore';

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
  // Gesamtreview B6: die Karte fragt die neuesten Einträge OHNE Monatsfilter
  // (`?limit=5`). Eine Monatsabfrage wird hier absichtlich leer beantwortet —
  // so fällt ein Rückfall auf den laufenden Monat sofort auf.
  function withMonthEntries(entries: unknown[]) {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries?limit=5'
        ? Promise.resolve({ data: entries })
        : url.startsWith('/time-entries?month=') ? Promise.resolve({ data: [] }) : base(url),
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

  it('ist am Monatsersten nicht leer — die Einträge des Vormonats erscheinen', async () => {
    // Gesamtreview B6: am 1. vor dem ersten Stempeln lieferte die Monatsabfrage
    // nichts, die Karte verschwand. Jetzt kommen die neuesten Einträge über die
    // Monatsgrenze hinweg.
    withMonthEntries([
      entry('s30b', '2026-09-30', '14:11:00', '17:00:00'),
      entry('s30a', '2026-09-30', '07:41:00', '12:00:00'),
    ]);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await renderedRanges()).toEqual(['14:11–17:00', '07:41–12:00']);
    expect(getMock.mock.calls.map((c) => c[0])).not.toContainEqual(
      expect.stringMatching(/^\/time-entries\?month=/),
    );
  });

  it('lädt nach dem Stempeln dieselbe monatsunabhängige Liste neu', async () => {
    withMonthEntries([entry('s30', '2026-09-30', '07:41:00', '12:00:00')]);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await renderedRanges()).toEqual(['07:41–12:00']);

    withMonthEntries([
      entry('o1', '2026-10-01', '07:39:00', '12:05:00'),
      entry('s30', '2026-09-30', '07:41:00', '12:00:00'),
    ]);
    act(() => useUIStore.getState().notifyStampChange());

    await waitFor(async () => expect(await renderedRanges()).toEqual(['07:39–12:05', '07:41–12:00']));
    act(() => useUIStore.setState({ stampVersion: 0 }));
  });
});

// #494: „x von y h heute" zählte nur die Laufzeit des OFFENEN Eintrags
// (`elapsed_minutes`). Geteilte Dienste verloren den Vormittag, nach dem
// Ausstempeln stand 0:00. Das Tages-Ist kommt jetzt als `today_net_minutes`,
// die heute zu stempelnden Stunden als `today_target_hours` (Präsenz-Soll aus
// `get_day_presence_target`, kein Vertrags-Tagessoll) aus /clock-status.
describe('Dashboard Stempelkarte „x von y h heute" (#494)', () => {
  function withClockStatus(data: unknown) {
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status' ? Promise.resolve({ data }) : base(url),
    );
  }

  it('zählt abgeschlossene Einträge des Tages mit, auch ohne offenen Eintrag', async () => {
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

  it('addiert im laufenden Nachmittagseintrag den Vormittag (nicht nur die laufenden Minuten)', async () => {
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

  // Gesamtreview B6: die Zeile stand auf dem Stand beim Laden — wer die Seite
  // offen ließ, sah um 16 Uhr noch die Zahl von 14 Uhr. Bei laufendem Eintrag
  // zählt sie jetzt minütlich mit (wie der Timer der Stempeluhr), ohne neu zu laden.
  describe('zählt bei laufendem Eintrag live mit', () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
      vi.setSystemTime(new Date('2026-10-08T15:27:00'));
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    const clockStatusCalls = () =>
      getMock.mock.calls.filter((c) => c[0] === '/time-entries/clock-status').length;

    it('schreibt „x von y" jede Minute fort, ohne /clock-status erneut abzufragen', async () => {
      withClockStatus({
        is_clocked_in: true, elapsed_minutes: 70,
        current_entry: { start_time: '14:17:00', break_minutes: 0 },
        today_net_minutes: 331, today_target_hours: 7,
      });
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      expect(await screen.findByText('5:31 von 7:00 h heute')).toBeInTheDocument();
      const callsAfterLoad = clockStatusCalls();

      act(() => { vi.advanceTimersByTime(60_000); });
      expect(screen.getByText('5:32 von 7:00 h heute')).toBeInTheDocument();

      act(() => { vi.advanceTimersByTime(29 * 60_000); });
      expect(screen.getByText('6:01 von 7:00 h heute')).toBeInTheDocument();
      expect(clockStatusCalls()).toBe(callsAfterLoad);
    });

    it('zieht die Pause des laufenden Eintrags wie der Server ab (kein Sprung über die Pause)', async () => {
      // 20 Min gestempelt, 30 Min Pause schon erfasst → laufend netto 0 (Server:
      // max(0, elapsed − Pause)). Erst nach weiteren 10 Minuten zählt es.
      withClockStatus({
        is_clocked_in: true, elapsed_minutes: 20,
        current_entry: { start_time: '15:07:00', break_minutes: 30 },
        today_net_minutes: 261, today_target_hours: 7,
      });
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      expect(await screen.findByText('4:21 von 7:00 h heute')).toBeInTheDocument();

      act(() => { vi.advanceTimersByTime(10 * 60_000); });
      expect(screen.getByText('4:21 von 7:00 h heute')).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(5 * 60_000); });
      expect(screen.getByText('4:26 von 7:00 h heute')).toBeInTheDocument();
    });

    it('zählt die Lücke zwischen den Arbeitsblöcken nicht mit (wie der Server, Ultrareview)', async () => {
      // Mo–Fr 08–12 + 15–18, Puffer 15: seit 08:00 eingestempelt, geladen um
      // 12:00 (angerechnet 240). Vorher zählte die Karte die Wanduhr weiter.
      vi.setSystemTime(new Date('2026-10-08T12:00:00'));
      withClockStatus({
        is_clocked_in: true, elapsed_minutes: 240,
        current_entry: { start_time: '08:00:00', break_minutes: 0, credit_override: false },
        today_net_minutes: 240, today_target_hours: 7,
        blocks_today: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }],
        grace_minutes: 15,
      });
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      expect(await screen.findByText('4:00 von 7:00 h heute')).toBeInTheDocument();

      // 13:00: nur 12:00–12:15 (Puffer) zählt, die Lücke ab 12:15 nicht.
      act(() => { vi.advanceTimersByTime(60 * 60_000); });
      expect(screen.getByText('4:15 von 7:00 h heute')).toBeInTheDocument();
      // 16:00: 14:45–16:00 zählt wieder → 4:15 + 1:15.
      act(() => { vi.advanceTimersByTime(3 * 60 * 60_000); });
      expect(screen.getByText('5:30 von 7:00 h heute')).toBeInTheDocument();
    });

    it('bleibt stehen, wenn nicht eingestempelt', async () => {
      withClockStatus({
        is_clocked_in: false, elapsed_minutes: null,
        today_net_minutes: 424, today_target_hours: 7,
      });
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      expect(await screen.findByText('7:04 von 7:00 h heute')).toBeInTheDocument();

      act(() => { vi.advanceTimersByTime(10 * 60_000); });
      expect(screen.getByText('7:04 von 7:00 h heute')).toBeInTheDocument();
    });
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

  function at(
    iso: string,
    todayTargetHours = 7,
    toFake: ('Date' | 'setInterval' | 'clearInterval')[] = ['Date'],
  ) {
    vi.useFakeTimers({ toFake });
    vi.setSystemTime(new Date(iso));
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: false, elapsed_minutes: null, today_net_minutes: 0,
          today_target_hours: todayTargetHours, blocks_today: BLOCKS, grace_minutes: 15,
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

  // Gesamtreview B6 (Nachzug): der Status hing an der Uhrzeit beim Rendern, der
  // Minutentakt lief aber nur bei laufendem Eintrag. Wer nicht eingestempelt
  // war, sah nach dem Ende der Lücke weiter neutral „Pause …" (bzw. beim
  // Eintritt in die Lücke weiter Rot) — bis zum nächsten Neuladen.
  describe('wechselt den Status beim Übergang der Lücke ohne Neuladen', () => {
    const clockStatusCalls = () =>
      getMock.mock.calls.filter((c) => c[0] === '/time-entries/clock-status').length;

    it('Ende der Lücke: neutral „Pause …" → „Noch nicht eingestempelt"', async () => {
      at('2026-06-01T14:58:00', 7, ['Date', 'setInterval', 'clearInterval']);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Pause zwischen den Arbeitsblöcken')).toBeInTheDocument());
      const callsAfterLoad = clockStatusCalls();

      act(() => { vi.advanceTimersByTime(3 * 60_000); });
      expect(within(card).getByText('Noch nicht eingestempelt')).toBeInTheDocument();
      expect(within(card).queryByText('Pause zwischen den Arbeitsblöcken')).not.toBeInTheDocument();
      expect(card.className).toMatch(/bg-danger/);
      expect(clockStatusCalls()).toBe(callsAfterLoad);
    });

    it('Beginn der Lücke: „Noch nicht eingestempelt" → neutral „Pause …"', async () => {
      at('2026-06-01T11:58:00', 7, ['Date', 'setInterval', 'clearInterval']);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Noch nicht eingestempelt')).toBeInTheDocument());

      act(() => { vi.advanceTimersByTime(3 * 60_000); });
      expect(within(card).getByText('Pause zwischen den Arbeitsblöcken')).toBeInTheDocument();
      expect(card.className).not.toMatch(/bg-danger/);
    });
  });

  // Review Task 17: `blocks_today` kommt aus `get_scheduled_blocks` und ist
  // auch an Tagen ohne Tagessoll gefüllt (ganztägig Urlaub/Krank/Fortbildung,
  // außerhalb des Beschäftigungsfensters) — der StampWidget braucht sie dort
  // zum Kappen. Die Karte darf daraus aber keine „Pause" machen: wer krank
  // ist, ist nicht zwischen zwei Arbeitsblöcken.
  it('zeigt an einem Tag ohne Tagessoll in der Lücke keine Pause', async () => {
    at('2026-06-01T12:30:00', 0);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
    await waitFor(() => expect(within(card).getByText('Nicht eingestempelt')).toBeInTheDocument());
    expect(within(card).queryByText('Pause zwischen den Arbeitsblöcken')).not.toBeInTheDocument();
    expect(card.className).not.toMatch(/bg-danger/);
  });
});

describe('Spec 14: Dashboard-Hinweise zur Arbeitszeit', () => {
  it('zeigt die Hinweise aus GET /dashboard', async () => {
    mockDashboardEndpoints();
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) => {
      if (url === '/dashboard') {
        return Promise.resolve({ data: {
          year: 2026, month: 10, target_hours: 0, actual_hours: 0, balance: 0,
          schedule_change_notices: [{
            created_at: '2026-10-08T08:00:00Z', effective_from: '2026-11-02', kind: 'change',
            text: 'Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche).',
          }],
        } });
      }
      return base(url);
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByText('Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche).'))
      .toBeInTheDocument();
  });
});
