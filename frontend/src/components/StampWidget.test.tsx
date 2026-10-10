import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StampWidget from './StampWidget';
import { useSystemStore } from '../stores/systemStore';

// ---------------------------------------------------------------------------
// #499 (Kundenmeldung): 08:49–13:59 + 13:59–18:00 wurde ohne Pause und ohne
// Begründung ausgestempelt. Der Dialog prüfte nur den laufenden Block (je < 6 h)
// — der Tagesverstoß kam allein als Warn-Toast. Seit #499 lehnt der Server das
// Ausstempeln ab; das Widget zeigt die Server-Meldung im Pausen-Dialog und
// bietet dort Pause bzw. (falls erlaubt) Begründung an.
// ---------------------------------------------------------------------------

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({ user: { id: 'u1', exempt_from_arbzg: false, track_hours: true } }),
}));

const S4 =
  'Bei mehr als 9 Stunden Arbeitszeit ist eine Pause von mindestens 45 Minuten erforderlich (ArbZG §4). ' +
  'Aktuelle Netto-Arbeitszeit: 9h 11min, Gesamtpause: 0 Minuten.';
const DISABLED = ' Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis abgeschaltet – bitte die Pause erfassen.';

/** "HH:MM:00" für jetzt minus `minutes` (Tagesgrenze egal: die Prüfung rechnet über Mitternacht). */
function startedAgo(minutes: number): string {
  const d = new Date(Date.now() - minutes * 60_000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:00`;
}

function clockedInSince(start: string) {
  getMock.mockImplementation((url: string) => {
    if (url === '/time-entries/clock-status') {
      return Promise.resolve({
        data: { is_clocked_in: true, current_entry: { id: 'te-open', start_time: start }, elapsed_minutes: 5 },
      });
    }
    return Promise.resolve({ data: {} });
  });
}

function rejectWith(detail: string) {
  postMock.mockRejectedValueOnce(Object.assign(new Error(detail), { response: { status: 400, data: { detail } } }));
}

async function openBreakDialog() {
  render(<StampWidget />);
  fireEvent.click(await screen.findByRole('button', { name: /Ausstempeln/ }));
  await screen.findByLabelText('Pause (Min.):');
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
  useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
});

describe('<StampWidget /> §4 über den ganzen Tag (#499)', () => {
  it('zeigt die Tages-Meldung des Servers im Dialog statt eines Toasts und bietet die Begründung an', async () => {
    clockedInSince(startedAgo(5)); // laufender Block kurz → die Vorprüfung im Browser greift nicht
    rejectWith(S4);
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    expect(await screen.findByText(S4)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Notfall, keine Vertretung/)).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('meldet zusätzlich per Toast, dass NICHT ausgestempelt wurde (bleibt sichtbar, wenn das Sheet zugeht)', async () => {
    // #499-Review F2: wer das Sheet nach der Sperre schließt, bliebe sonst
    // unbemerkt eingestempelt — am Folgetag schließt der Server den Eintrag auf
    // 23:59 ohne Pause.
    clockedInSince(startedAgo(5));
    rejectWith(S4);
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    await screen.findByText(S4);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toMatch(/NICHT ausgestempelt/);
    expect(toast.error.mock.calls[0][0]).toMatch(/oder begründen/);
  });

  it('meldet auch bei der Vorprüfung im Browser per Toast, dass NICHT ausgestempelt wurde', async () => {
    clockedInSince(startedAgo(7 * 60)); // 7 h ohne Pause → Vorprüfung schlägt an
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    expect(await screen.findByText(/mind\. 30 Min\. Pause/)).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toMatch(/NICHT ausgestempelt/);
  });

  it('schickt die Begründung beim zweiten Versuch mit', async () => {
    clockedInSince(startedAgo(5));
    rejectWith(S4);
    postMock.mockResolvedValueOnce({ data: { warnings: [] } });
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    fireEvent.change(await screen.findByPlaceholderText(/Notfall, keine Vertretung/), {
      target: { value: 'Notfall' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(2));
    expect(postMock.mock.calls[1][1]).toMatchObject({ break_waiver_reason: 'Notfall' });
  });
});

describe('<StampWidget /> Ausnahme abgeschaltet (#499)', () => {
  beforeEach(() => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', break_exception_allowed: false },
      isLoaded: true,
    });
  });

  it('bietet bei der Vorprüfung keine Begründung an — nur die Pause', async () => {
    clockedInSince(startedAgo(7 * 60)); // 7 h ohne Pause → Vorprüfung schlägt an
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    expect(await screen.findByText(/mind\. 30 Min\. Pause/)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Notfall, keine Vertretung/)).not.toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('bietet auch nach der Server-Meldung keine Begründung an', async () => {
    clockedInSince(startedAgo(5));
    rejectWith(S4 + DISABLED);
    await openBreakDialog();

    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));

    expect(await screen.findByText(S4 + DISABLED)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Notfall, keine Vertretung/)).not.toBeInTheDocument();
    // Toast nennt nur den Weg, den es gibt: Pause nachtragen, keine Begründung.
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toMatch(/NICHT ausgestempelt/);
    expect(toast.error.mock.calls[0][0]).not.toMatch(/begründen/);
  });
});

describe('<StampWidget /> §4-Vorprüfung mit Lückensegmenten (Spec 8.4)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function clockedInWithBlocks(blocks: unknown[]) {
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: true, current_entry: { id: 'te-open', start_time: '08:00:00' },
          elapsed_minutes: 600, blocks_today: blocks, grace_minutes: 15,
        } })
        : Promise.resolve({ data: {} }));
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it('verlangt keine Pause, wenn die Lücke zwischen den Blöcken §4 deckt', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T18:00:00'));
    clockedInWithBlocks(BLOCKS);
    postMock.mockResolvedValueOnce({ data: { warnings: [] } });
    await openBreakDialog();
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/time-entries/clock-out', expect.objectContaining({ break_minutes: 0 })));
  });

  // Gesamtreview PR2 (Fund 13): Altfenster 08:00–13:30, Puffer 15, eingestempelt
  // 07:45, Ausstempeln 14:30 — angerechnet 07:45–13:45 = 6:00 h, der Server
  // braucht keine Pause (E43; die Anwesenheit meldet er nur weich, P14). Wer
  // hier eine nicht genommene Pause einträgt, verlöre 30 Min angerechnete Zeit.
  it('rechnet §4 auf der gekappten Zeit: Altfenster, Ausstempeln nach der Hülle', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T14:30:00'));
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: true, current_entry: { id: 'te-open', start_time: '07:45:00' },
          elapsed_minutes: 405, blocks_today: [{ start: '08:00', end: '13:30' }], grace_minutes: 15,
        } })
        : Promise.resolve({ data: {} }));
    postMock.mockResolvedValueOnce({ data: { warnings: [] } });
    await openBreakDialog();
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/time-entries/clock-out', expect.objectContaining({ break_minutes: 0 })));
    expect(screen.queryByText(/ArbZG §4/)).not.toBeInTheDocument();
  });

  it('Kontrolle: ohne Blöcke greift die Vorprüfung wie bisher (10 h ohne Pause)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T18:00:00'));
    clockedInWithBlocks([]);
    await openBreakDialog();
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    expect(await screen.findByText('Bei >9h Arbeitszeit sind mind. 45 Min. Pause erforderlich (ArbZG §4)')).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
  });
});
