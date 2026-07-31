import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider } from '../../../contexts/ToastContext';
import WorkingHoursModal from './WorkingHoursModal';

// Same pattern as UserForm.test.tsx: mock the API client, expose the mocks so
// each test can configure GET (list vs. preview), POST and DELETE responses.
const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));

// #431: eine Verlaufszeile ist ein vollständiger Vertrags-Snapshot (Modus,
// Tageswerte, Arbeitstage, Wochenstunden) — die Defaults hier bilden den
// gleichmäßigen Normalfall ab, die Tests überschreiben gezielt.
type HistoryRow = {
  id: string;
  effective_from: string;
  weekly_hours: number;
  note?: string;
  use_daily_schedule?: boolean;
  hours_monday?: number | null;
  hours_tuesday?: number | null;
  hours_wednesday?: number | null;
  hours_thursday?: number | null;
  hours_friday?: number | null;
  work_days_per_week?: number | null;
};

function historyResponse(rows: Array<HistoryRow>) {
  return {
    data: rows.map((r) => ({
      user_id: 'u1',
      created_at: '2026-01-01T10:00:00Z',
      use_daily_schedule: false,
      hours_monday: null,
      hours_tuesday: null,
      hours_wednesday: null,
      hours_thursday: null,
      hours_friday: null,
      work_days_per_week: 5,
      ...r,
    })),
  };
}

type PreviewOverrides = Partial<{
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  day_targets_current: number[];
  day_targets_new: number[];
  overtime_before: number;
  overtime_after: number;
  vacation_days_before: number;
  vacation_days_after: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
}>;

function previewResponse(overrides: PreviewOverrides = {}) {
  return {
    data: {
      is_retroactive: true,
      period_start: '2026-06-01',
      period_end: '2026-07-26',
      current_daily_target: 8,
      new_daily_target: 6,
      day_targets_current: [8, 8, 8, 8, 8],
      day_targets_new: [6, 6, 6, 6, 6],
      overtime_before: 12.5,
      overtime_after: 12.5,
      vacation_days_before: 10,
      vacation_days_after: 10,
      affected_absences: 2,
      blocked_reason: null,
      closed_years: [],
      closed_year_warning: null,
      ...overrides,
    },
  };
}

// Vorschau-Antwort konfigurieren, Verlauf bleibt leer — das Muster, das die
// meisten Tests hier brauchen.
function mockPreview(overrides: PreviewOverrides = {}) {
  getMock.mockImplementation((url: string) => {
    if (String(url).includes('/preview')) return Promise.resolve(previewResponse(overrides));
    return Promise.resolve(historyResponse([]));
  });
}

function renderModal(props: Record<string, unknown> = {}) {
  return render(
    <ToastProvider>
      <WorkingHoursModal
        userId="u1"
        userName="Jane Doe"
        currentWeeklyHours={40}
        onClose={() => {}}
        onChanged={() => {}}
        {...props}
      />
    </ToastProvider>,
  );
}

beforeEach(() => {
  // Only Date is mocked (for a deterministic "today" in the is-retroactive
  // check) — setTimeout/setInterval stay REAL, so the component's own
  // debounce timer and Testing Library's async queries (findBy/waitFor) keep
  // working without needing to fake-advance them.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-07-26T12:00:00Z'));
  getMock.mockReset().mockImplementation((url: string) => {
    if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
    return Promise.resolve(historyResponse([]));
  });
  postMock.mockReset().mockResolvedValue({ data: { id: 'c-new', adjusted_absences: 0, warning: null } });
  deleteMock.mockReset().mockResolvedValue({});
});

afterEach(() => {
  vi.useRealTimers();
});

// Real-time wait past the component's PREVIEW_DEBOUNCE_MS (400ms) — setTimeout
// is NOT mocked (only Date is, see beforeEach), so this is an actual pause.
async function flushDebounce(ms = 500) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

describe('Task 7: Stundenverlauf mit ab/bis + rückwirkende Vorschau', () => {
  it('Verlauf zeigt "ab … bis …", der jüngste Eintrag "bis heute"', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2026-01-01', weekly_hours: 30 },
        { id: 'c2', effective_from: '2026-03-01', weekly_hours: 40 },
      ]));
    });
    renderModal();
    await screen.findByText(/Ab 01\.01\.2026 bis 28\.02\.2026: 30,0 Std\/Woche/);
    expect(screen.getByText(/Ab 01\.03\.2026 bis heute: 40,0 Std\/Woche/)).toBeInTheDocument();
  });

  it('zukünftiges Datum OHNE betroffene Abwesenheiten zeigt keinen Hinweis', async () => {
    // Release-Review 1.17.0: hieß früher „zukünftiges Datum zeigt keinen
    // rückwirkenden Hinweis" und prüfte zusätzlich, dass für ein Datum ab heute
    // GAR KEINE Vorschau abgerufen wird. Genau das war der Fehler: auch ein
    // zukünftiges Wirkungsdatum schreibt bereits gebuchte Abwesenheiten um
    // (genehmigter Urlaub, Betriebsferien, geplante Fortbildung). Die Vorschau
    // läuft jetzt immer; ohne Befund bleibt der Dialog aber unverändert still.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          is_retroactive: false,
          period_start: '2026-12-31',
          period_end: '2026-12-31',
          affected_absences: 0,
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-12-31' } });
    // #431: ohne echte Änderung am Snapshot gibt es nichts zu speichern — der
    // Button wäre dann schon deshalb gesperrt und die Aussage dieses Tests
    // („kein Hinweis, Speichern möglich") ginge verloren.
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hinzufügen/i })).not.toBeDisabled();
  });

  it('zukünftiges Datum MIT bereits gebuchten Abwesenheiten warnt und verlangt eine Bestätigung', async () => {
    // Der Regelfall des Dialogs („ab dem 1.9. arbeitet sie 20 Stunden") schrieb
    // bereits genehmigte Urlaubs-/Fortbildungstage still auf das neue Tagessoll
    // um — ohne dass der Dialog das je angekündigt hätte.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          is_retroactive: false,
          period_start: '2026-09-01',
          period_end: '2026-09-18',
          affected_absences: 3,
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    expect(await screen.findByText(/3 Abwesenheit\(en\) betroffen/)).toBeInTheDocument();
    expect(screen.getByText(/01\.09\.2026.*18\.09\.2026/)).toBeInTheDocument();
    // Kein „Rückwirkende Änderung" — das Datum liegt in der Zukunft.
    expect(screen.queryByText(/Rückwirkende Änderung/)).not.toBeInTheDocument();

    const submit = screen.getByRole('button', { name: /Hinzufügen/i });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(submit).not.toBeDisabled();
  });

  it('rückwirkendes Datum löst die Vorschau aus und zeigt Zeitraum, Tagessoll und Anzahl', async () => {
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    await flushDebounce();

    await waitFor(() => {
      const call = getMock.mock.calls.find((c) => String(c[0]).includes('/preview'));
      expect(call).toBeTruthy();
      expect(call![1]?.params).toMatchObject({ effective_from: '2026-06-01', weekly_hours: 40 });
    });

    expect(await screen.findByText(/01\.06\.2026.*26\.07\.2026/)).toBeInTheDocument();
    // #431: statt eines Skalars („8.0h → 6.0h") das Tagessoll je Wochentag —
    // ein Wert bildet einen individuellen Tagesplan nicht ab.
    expect(screen.getByText(/Mo 8,0 → 6,0/)).toBeInTheDocument();
    expect(screen.getByText(/2 Abwesenheit\(en\) betroffen/)).toBeInTheDocument();
  });

  it('zeigt den Hinweis auf ein abgeschlossenes Jahr, wenn die Vorschau ihn liefert', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          closed_years: [2025],
          closed_year_warning: 'Das Jahr 2025 ist bereits abgeschlossen — der Carryover 2026 könnte veraltet sein.',
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2025-12-01' } });
    await flushDebounce();
    expect(await screen.findByText(/2025 ist bereits abgeschlossen/)).toBeInTheDocument();
  });

  it('Speichern ist erst nach ausdrücklicher Bestätigung der rückwirkenden Vorschau möglich', async () => {
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await screen.findByText(/Abwesenheit\(en\) betroffen/);

    const submit = screen.getByRole('button', { name: /Hinzufügen/i });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox'));
    expect(submit).not.toBeDisabled();

    // Changing the date again must revoke the earlier confirmation.
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-02' } });
    expect(submit).toBeDisabled();
  });

  it('blocked_reason sperrt den Speichern-Button und zeigt den Grund', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          blocked_reason: 'Für Mitarbeitende mit individuellem Tagesplan wird die Stunden-Historie nicht unterstützt.',
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await screen.findByText(/individuellem Tagesplan/);

    expect(screen.getByRole('button', { name: /Hinzufügen/i })).toBeDisabled();
    // No confirmation checkbox is offered for a blocked change — there is
    // nothing to confirm your way past.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('blocked_reason greift auch bei einem Datum in der ZUKUNFT', async () => {
    // Regression (Release-Review 1.17.0, Nachtrag): `blockedReason` war auf
    // `isRetroactive` gegattert — ein Rest aus der Zeit, als die Vorschau nur
    // für rückwirkende Daten geladen wurde. Der POST weist aber unabhängig vom
    // Datum mit 400 ab (individueller Tagesplan, bereits belegtes
    // Wirkungsdatum). Ohne den Fix zeigte der Dialog bei einem Zukunftsdatum
    // weder den Grund noch sperrte er — der Admin lief sehenden Auges in den
    // Fehler, den `blocked_reason` gerade verhindern soll.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          is_retroactive: false,
          affected_absences: 0,
          blocked_reason: 'Für dieses Datum existiert bereits eine Änderung.',
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    await screen.findByText(/existiert bereits eine Änderung/);
    expect(screen.getByRole('button', { name: /Hinzufügen/i })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('meldet adjusted_absences und warning nach dem Speichern per Toast', async () => {
    postMock.mockResolvedValue({
      data: { id: 'c-x', adjusted_absences: 3, warning: 'Das Jahr 2026 ist bereits abgeschlossen.' },
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await screen.findByText(/Abwesenheit\(en\) betroffen/);
    fireEvent.click(screen.getByRole('checkbox'));

    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(await screen.findByText(/3 Abwesenheit\(en\) auf das neue Tagessoll umgerechnet/)).toBeInTheDocument();
    expect(await screen.findByText(/Das Jahr 2026 ist bereits abgeschlossen\./)).toBeInTheDocument();
  });
});

describe('M1: "heute" ist das LOKALE Datum, nicht das UTC-Datum', () => {
  // Zwischen 00:00 und 02:00 Berliner Zeit lag das UTC-Datum einen Tag zurück:
  // der Dialog hielt das gestrige Datum für "heute" → keine Vorschau, keine
  // Bestätigungspflicht, während das Backend (today_local()) es als
  // rückwirkend behandelte und retargetete.
  //
  // `process.env.TZ` lässt sich im vitest-Worker-Thread nicht mehr umstellen
  // (die V8-Zeitzone steht dort fest), deshalb wird die lokale Sicht direkt
  // über die Date-Getter simuliert: Systemzeit 26.07. 22:30 UTC, lokal
  // 27.07. — genau die Konstellation, in der die beiden Datumsformen
  // auseinanderfallen.
  const AROUND_MIDNIGHT_BERLIN = new Date('2026-07-26T22:30:00Z');

  function mockLocalDate(y: number, m: number, d: number) {
    vi.spyOn(Date.prototype, 'getFullYear').mockReturnValue(y);
    vi.spyOn(Date.prototype, 'getMonth').mockReturnValue(m - 1);
    vi.spyOn(Date.prototype, 'getDate').mockReturnValue(d);
  }

  beforeEach(() => {
    vi.setSystemTime(AROUND_MIDNIGHT_BERLIN);
    mockLocalDate(2026, 7, 27);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('setzt das Vorgabe-Datum auf den lokalen Tag', async () => {
    expect(new Date().toISOString().split('T')[0]).toBe('2026-07-26'); // UTC-Sicht
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    expect((screen.getByLabelText('Gültig ab') as HTMLInputElement).value).toBe('2026-07-27');
  });

  it('behandelt den lokalen Vortag als rückwirkend (Bestätigung wird erzwungen)', async () => {
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    // 26.07. ist lokal GESTERN — vorher hielt der Dialog es für "heute" und
    // liess ohne Vorschau und ohne Bestätigung speichern.
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-07-26' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await screen.findByText(/Abwesenheit\(en\) betroffen/);
    expect(screen.getByRole('button', { name: /Hinzufügen/i })).toBeDisabled();
  });
});

describe('Löschen einer Stundenänderung', () => {
  // I3: Das Backend antwortet beim Löschen mit 200 + {warning}, wenn die
  // Rückrechnung ein bereits abgeschlossenes Jahr berührt (sonst 204 ohne Body).
  it('zeigt die Jahresabschluss-Warnung aus der 200-Antwort', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2025-06-01', weekly_hours: 30 },
      ]));
    });
    deleteMock.mockResolvedValue({
      status: 200,
      data: { warning: 'Das Jahr 2025 ist bereits abgeschlossen — der Carryover 2026 könnte veraltet sein.' },
    });
    renderModal();
    await screen.findByText(/Ab 01\.06\.2025/);

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));

    await waitFor(() => expect(deleteMock).toHaveBeenCalled());
    expect(await screen.findByText(/2025 ist bereits abgeschlossen/)).toBeInTheDocument();
  });

  it('zeigt die Backend-Begründung statt einer pauschalen Fehlermeldung', async () => {
    // I4: Der Grund („…verankert den davor gültigen Wert…") wurde von einer
    // hardcodierten Meldung verschluckt.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2026-06-01', weekly_hours: 30 },
      ]));
    });
    deleteMock.mockRejectedValue({
      response: { data: { detail: 'Dies ist die früheste erfasste Stundenänderung dieses Mitarbeiters.' } },
    });
    renderModal();
    await screen.findByText(/Ab 01\.06\.2026/);

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));

    expect(await screen.findByText(/früheste erfasste Stundenänderung/)).toBeInTheDocument();
  });

  it('deaktiviert den Löschen-Button der frühesten Zeile, solange spätere existieren', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c2', effective_from: '2026-03-01', weekly_hours: 40 },
        { id: 'c1', effective_from: '2026-01-01', weekly_hours: 30 },
      ]));
    });
    renderModal();
    await screen.findByText(/Ab 01\.01\.2026/);

    const locked = screen.getByRole('button', { name: /Löschen nicht möglich/ });
    expect(locked).toBeDisabled();
    // Die spätere Zeile bleibt löschbar — genau ein aktiver Löschen-Button.
    expect(screen.getAllByRole('button', { name: 'Löschen' })).toHaveLength(1);
  });

  it('bietet das Löschen der EINZIGEN Zeile weiterhin an', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2026-01-01', weekly_hours: 30 },
      ]));
    });
    renderModal();
    await screen.findByText(/Ab 01\.01\.2026/);

    expect(screen.getByRole('button', { name: 'Löschen' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /Löschen nicht möglich/ })).not.toBeInTheDocument();
  });

  it('zeigt keine Warnung bei der leeren 204-Antwort', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2026-06-01', weekly_hours: 30 },
      ]));
    });
    // axios liefert bei 204 data === '' — darf nicht als Warnung durchgehen.
    deleteMock.mockResolvedValue({ status: 204, data: '' });
    renderModal();
    await screen.findByText(/Ab 01\.06\.2026/);

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));

    await waitFor(() => expect(deleteMock).toHaveBeenCalled());
    expect(await screen.findByText(/erfolgreich gelöscht/)).toBeInTheDocument();
    expect(screen.queryByText(/abgeschlossen/)).not.toBeInTheDocument();
  });
});

describe('Fund 1 (Release-Review 1.17.0): Sequenz-Guard gegen veraltete Vorschau-Antworten', () => {
  // Vorher fehlte jeder Cancel-Mechanismus (weder `cancelled`-Flag noch
  // AbortController) — eine spät eintreffende Antwort auf ein DATUM, das der
  // Admin längst verlassen hat, überschrieb unbedingt `preview`. Das ist genau
  // die Vorschau, unter der die Pflicht-Bestätigungs-Checkbox für eine
  // rückwirkende Änderung hängt.
  it('verwirft eine verspätete Antwort auf ein bereits verlassenes Datum, statt sie anzuzeigen', async () => {
    let resolveStale: (value: unknown) => void = () => {};
    const stale = new Promise((resolve) => {
      resolveStale = resolve;
    });
    let previewCallCount = 0;
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        previewCallCount += 1;
        // Request A (older date, issued first) hangs until resolved manually.
        if (previewCallCount === 1) return stale;
        // Request B (the date the admin actually settles on) resolves fast.
        return Promise.resolve(previewResponse({ affected_absences: 9 }));
      }
      return Promise.resolve(historyResponse([]));
    });

    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');

    // Admin picks an older retroactive date first — request A goes out …
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2025-06-01' } });
    await flushDebounce();

    // … but before it resolves, the admin moves to a DIFFERENT retroactive
    // date. Request B fires and resolves immediately.
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    await flushDebounce();
    await screen.findByText(/9 Abwesenheit\(en\) betroffen/);

    // A finally resolves LATE, for a period/Tagessoll that belongs to the
    // date the admin left minutes ago. It must be discarded, not displayed.
    resolveStale(previewResponse({ affected_absences: 2 }));
    await flushDebounce(50);

    expect(screen.getByText(/9 Abwesenheit\(en\) betroffen/)).toBeInTheDocument();
    expect(screen.queryByText(/2 Abwesenheit\(en\) betroffen/)).not.toBeInTheDocument();
  });
});

describe('Fund 3 (Release-Review 1.17.0): Kopfzeile + Formular ziehen nach dem Speichern nach', () => {
  // `currentWeeklyHours` ist ein Snapshot von VOR dem Öffnen des Dialogs und
  // wird vom Elternteil nicht nachgezogen (der Dialog bleibt nach dem
  // Speichern offen) — die Kopfzeile und das Eingabefeld müssen daher aus dem
  // frisch geladenen Verlauf abgeleitet werden, nicht aus der Prop.
  it('zeigt nach dem Speichern das NEUE Wochenstunden im Kopf und im Eingabefeld, nicht die stale Prop', async () => {
    let historyRows: Array<{ id: string; effective_from: string; weekly_hours: number }> = [];
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse(historyRows));
    });
    postMock.mockImplementation(async () => {
      // Simulates the backend having created the row the GET below now returns.
      historyRows = [{ id: 'c-new', effective_from: '2026-07-26', weekly_hours: 20 }];
      return { data: { id: 'c-new', adjusted_absences: 0, warning: null } };
    });

    renderModal({ currentWeeklyHours: 40 });
    await screen.findByText('Keine Änderungen vorhanden');
    expect(screen.getByText(/Aktuell: 40,0 Std\/Woche/)).toBeInTheDocument();

    // Today's date (not retroactive) — no preview/confirmation needed, keeps
    // this test focused on the post-save refresh.
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByText(/erfolgreich hinzugefügt/);

    // Header must reflect the NEW value — not the stale `currentWeeklyHours` prop.
    await waitFor(() => expect(screen.getByText(/Aktuell: 20,0 Std\/Woche/)).toBeInTheDocument());
    // The input must also be prefilled with the new value, not reset to 40.
    expect((screen.getByLabelText('Wochenstunden') as HTMLInputElement).value).toBe('20');
  });
});

describe('Fund 4 (Release-Review 1.17.0): Vorschau-Fehler wird sichtbar gemacht', () => {
  // Vorher: `.catch(() => setPreview(null))` ohne jede Rückmeldung → ein
  // sichtbar leerer amber Kasten neben einem gesperrten „Hinzufügen"-Button.
  it('zeigt eine Fehlermeldung statt eines leeren Kastens und erlaubt erneutes Prüfen', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.reject({ response: { data: { detail: 'Netzwerkfehler' } } });
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    expect(await screen.findByText('Netzwerkfehler')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hinzufügen/i })).toBeDisabled();
    // No silently empty box — an explicit retry affordance is offered instead.
    const retry = screen.getByRole('button', { name: /Erneut prüfen/i });

    // The retry succeeds without the admin having to touch date/hours again.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([]));
    });
    fireEvent.click(retry);
    await flushDebounce();

    await screen.findByText(/Abwesenheit\(en\) betroffen/);
    expect(screen.queryByText('Netzwerkfehler')).not.toBeInTheDocument();
  });
});

describe('#431: Modus-Umschalter, Tagesplan und erweiterte Vorschau', () => {
  it('zeigt fünf Tagesfelder, wenn der Tagesplan-Modus gewählt ist', async () => {
    renderModal({ currentUseDailySchedule: true });
    expect(await screen.findByLabelText('Montag')).toBeInTheDocument();
    expect(screen.getByLabelText('Freitag')).toBeInTheDocument();
    // Im Tagesplan-Modus gibt es kein eigenes Wochenstunden-Feld: der Wert ist
    // die Summe der Tageswerte und wird serverseitig gesetzt.
    expect(screen.queryByLabelText('Wochenstunden')).not.toBeInTheDocument();
  });

  it('berechnet die Wochenstunden als Summe der Tageswerte', async () => {
    renderModal({ currentUseDailySchedule: true });
    fireEvent.change(await screen.findByLabelText('Montag'), { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('Mittwoch'), { target: { value: '4' } });
    expect(screen.getByText(/12,0 h\/Woche/)).toBeInTheDocument();
    // Die Arbeitstage ergeben sich aus den Tagen MIT Stunden.
    expect(screen.getByText(/2 Arbeitstage/)).toBeInTheDocument();
  });

  it('wechselt über die Modus-Auswahl von gleichmäßig auf Tagesplan', async () => {
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    expect(screen.getByLabelText('Wochenstunden')).toBeInTheDocument();
    expect(screen.queryByLabelText('Montag')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: /Nach Tagen/ }));

    expect(screen.queryByLabelText('Wochenstunden')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Montag')).toBeInTheDocument();
  });

  it('schickt den Tagesplan an den Endpoint', async () => {
    mockPreview({ affected_absences: 0 });
    renderModal({ currentUseDailySchedule: true });
    fireEvent.change(await screen.findByLabelText('Montag'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/ }));
    await waitFor(() => {
      const call = postMock.mock.calls.at(-1);
      expect(call![1]).toMatchObject({ use_daily_schedule: true, hours_monday: 8 });
      // Die Wochensumme setzt der Server (check_mode) — ein eigener Wert des
      // Clients könnte ihr widersprechen.
      expect(call![1]).not.toHaveProperty('weekly_hours');
    });
  });

  it('schickt im gleichmäßigen Modus keine Tageswerte', async () => {
    // Das Backend lehnt Tageswerte im gleichmäßigen Modus mit 400 ab
    // ("Tagesstunden gehören zum Tagesplan-Modus") — inerte Reste im Payload
    // wären also kein Schönheitsfehler, sondern ein harter Fehler.
    mockPreview({ affected_absences: 0 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/ }));
    await waitFor(() => {
      const call = postMock.mock.calls.at(-1);
      expect(call![1]).toMatchObject({ use_daily_schedule: false, weekly_hours: 20 });
      for (const f of ['hours_monday', 'hours_tuesday', 'hours_wednesday', 'hours_thursday', 'hours_friday']) {
        expect(call![1]).not.toHaveProperty(f);
      }
    });
  });

  it('schickt den Tagesplan auch an die Vorschau', async () => {
    mockPreview({ affected_absences: 0 });
    renderModal({ currentUseDailySchedule: true });
    fireEvent.change(await screen.findByLabelText('Montag'), { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('Dienstag'), { target: { value: '5' } });
    await flushDebounce();

    await waitFor(() => {
      const call = getMock.mock.calls.filter((c) => String(c[0]).includes('/preview')).at(-1);
      expect(call![1]?.params).toMatchObject({
        use_daily_schedule: true,
        hours_monday: 8,
        hours_tuesday: 5,
        work_days_per_week: 2,
      });
      expect(call![1]?.params).not.toHaveProperty('weekly_hours');
    });
  });

  it('zeigt Saldo und Urlaub vorher/nachher aus der Vorschau', async () => {
    mockPreview({
      overtime_before: 89, overtime_after: 41.5,
      vacation_days_before: 18, vacation_days_after: 18,
      day_targets_current: [8, 5, 4, 0, 0], day_targets_new: [6, 5, 4, 0, 0],
      affected_absences: 12, is_retroactive: true,
    });
    renderModal({ currentUseDailySchedule: true });
    expect(await screen.findByText(/Überstunden/)).toBeInTheDocument();
    expect(screen.getByText(/−47,5/)).toBeInTheDocument();
    // Tagessoll je Wochentag statt eines Skalars; Tage ohne Soll auf beiden
    // Seiten bleiben weg.
    expect(screen.getByText(/Mo 8,0 → 6,0/)).toBeInTheDocument();
    expect(screen.getByText(/Di 5,0 → 5,0/)).toBeInTheDocument();
    expect(screen.queryByText(/Do /)).not.toBeInTheDocument();
  });

  it('nennt beim Urlaub das Jahr des Wirkungszeitraums', async () => {
    // Die Urlaubszahlen der Vorschau beziehen sich auf das Jahr von
    // period_start — ohne Jahreszahl liest der Admin sie als "dieses Jahr".
    mockPreview({ period_start: '2025-11-01', period_end: '2025-12-31', vacation_days_before: 18, vacation_days_after: 19 });
    renderModal();
    expect(await screen.findByText(/Urlaub 2025/)).toBeInTheDocument();
  });

  it('erklärt einen unveränderten Saldo bei einem Wirkungsdatum in der Zukunft', async () => {
    // "Saldo 12,5 → 12,5" heißt NICHT "keine Auswirkung": der Saldo-Stichtag
    // (#313) liegt vor dem Wirkungsfenster. Ohne diesen Satz liest der Admin
    // die gleiche Zahl als Entwarnung — obwohl 3 Abwesenheiten umgeschrieben
    // werden.
    mockPreview({
      is_retroactive: false, period_start: '2026-09-01', period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 12.5,
      vacation_days_before: 10, vacation_days_after: 10,
      affected_absences: 3,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    expect(await screen.findByText(/wirkt erst ab dem 01\.09\.2026/)).toBeInTheDocument();
  });

  it('sperrt Hinzufügen, solange der eingegebene Stand dem gültigen entspricht', async () => {
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    const submit = screen.getByRole('button', { name: /Hinzufügen/i });
    expect(submit).toBeDisabled();
    // Ein gesperrter Button ohne Begründung ist genau der Fund-4-Fehler.
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    expect(submit).not.toBeDisabled();
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();
  });

  it('vergleicht gegen den Stand AM Wirkungsdatum, nicht gegen den von heute', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        { id: 'c1', effective_from: '2026-01-01', weekly_hours: 40 },
        { id: 'c2', effective_from: '2026-06-01', weekly_hours: 20 },
      ]));
    });
    renderModal({ currentWeeklyHours: 20 });
    await screen.findByText(/Ab 01\.01\.2026/);
    // Heute gelten 20 h — für den 01.03.2026 galten aber 40 h. Eine Zeile
    // "ab 01.03.: 20 h" ist dort also sehr wohl eine Änderung.
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-03-01' } });
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();

    // Zurück auf heute: derselbe Wert ist dort nichts Neues.
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-07-26' } });
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
  });

  it('Verlauf und Kopfzeile zeigen den Tagesplan der Zeile', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.resolve(previewResponse());
      return Promise.resolve(historyResponse([
        {
          id: 'c1', effective_from: '2026-03-01', weekly_hours: 17,
          use_daily_schedule: true, hours_monday: 8, hours_tuesday: 5, hours_wednesday: 4,
          work_days_per_week: 3,
        },
      ]));
    });
    renderModal({
      currentWeeklyHours: 17, currentUseDailySchedule: true,
      currentDayHours: [8, 5, 4, null, null], currentWorkDays: 3,
    });
    expect(
      await screen.findByText(/Ab 01\.03\.2026 bis heute: Mo 8,0 \/ Di 5,0 \/ Mi 4,0 = 17,0 Std\/Woche/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Aktuell: Mo 8,0 \/ Di 5,0 \/ Mi 4,0 = 17,0 Std\/Woche/)).toBeInTheDocument();
  });

  it('löst trotz fünf zusätzlicher Felder nur EINE Vorschau je Eingabepause aus', async () => {
    // Der Dialog hängt jetzt an acht Formularwerten. Ohne den (bestehenden)
    // Debounce plus Cleanup liefe pro Tastendruck ein eigener Request — und
    // die späteste Antwort gewänne, nicht die neueste Eingabe.
    renderModal({ currentUseDailySchedule: true });
    await screen.findByLabelText('Montag');
    await flushDebounce();
    const previewCalls = () => getMock.mock.calls.filter((c) => String(c[0]).includes('/preview')).length;
    const afterMount = previewCalls();
    expect(afterMount).toBe(1);

    fireEvent.change(screen.getByLabelText('Montag'), { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('Dienstag'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Mittwoch'), { target: { value: '4' } });
    await flushDebounce();
    expect(previewCalls()).toBe(afterMount + 1);

    // Die Notiz geht die Vorschau nichts an.
    fireEvent.change(screen.getByLabelText('Notiz (optional)'), { target: { value: 'Teilzeit' } });
    await flushDebounce();
    expect(previewCalls()).toBe(afterMount + 1);
  });
});

describe('Abschluss-Review #431, Fund 2: Vorschau erscheint auch bei reiner Saldo-/Urlaubswirkung', () => {
  // Der Kasten hing an „rückwirkend ODER Abwesenheits-Stunden werden
  // umgeschrieben ODER blockiert". Eine ZUKUNFTSdatierte Änderung, die einen
  // Wochentag wegfallen lässt, ändert aber den Urlaubsverbrauch, ohne eine
  // einzige Abwesenheits-Stunde umzuschreiben: `retarget_absence_hours`
  // überspringt Tage, deren neues Tagessoll 0 ist. `affected_absences = 0`,
  // `is_retroactive = false` → der ganze Kasten blieb aus, obwohl
  // `vacation_days_after` um 1 niedriger war. Handbuch und In-App-Hilfe fordern
  // ausdrücklich auf, genau diese Zeile zu prüfen.

  it('zeigt den Kasten, wenn nur die Urlaubstage sich ändern (Mittwoch fällt weg)', async () => {
    mockPreview({
      is_retroactive: false,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 12.5,
      vacation_days_before: 12, vacation_days_after: 11,
      affected_absences: 0,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '24' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Urlaub 2026/)).toBeInTheDocument();
    expect(within(box).getByText('12,0 Tage')).toBeInTheDocument();
    expect(within(box).getByText('11,0 Tage')).toBeInTheDocument();
    // Nicht als „betrifft gebuchte Abwesenheiten" überschreiben — es sind null.
    expect(within(box).queryByText(/Betrifft bereits gebuchte Abwesenheiten/)).not.toBeInTheDocument();
    expect(within(box).queryByText(/Rückwirkende Änderung/)).not.toBeInTheDocument();
  });

  it('verlangt für diese Auswirkung dieselbe ausdrückliche Bestätigung', async () => {
    mockPreview({
      is_retroactive: false,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 12.5,
      vacation_days_before: 12, vacation_days_after: 11,
      affected_absences: 0,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '24' } });
    await flushDebounce();
    await screen.findByRole('status');

    const submit = screen.getByRole('button', { name: /Hinzufügen/i });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(submit).not.toBeDisabled();
  });

  it('zeigt den Kasten auch, wenn nur der Überstundensaldo sich ändert', async () => {
    mockPreview({
      is_retroactive: false,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 8.5,
      vacation_days_before: 12, vacation_days_after: 12,
      affected_absences: 0,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '24' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText('−4,0 h')).toBeInTheDocument();
  });

  it('bleibt still, wenn sich Saldo und Urlaub nicht unterscheiden', async () => {
    // Die Gegenprobe: bei unverändertem Snapshot steigt die Vorschau
    // serverseitig VOR der Simulation aus und liefert „nachher == vorher".
    // Dieser Fall darf nicht plötzlich einen Warnkasten erzeugen.
    mockPreview({
      is_retroactive: false,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 12.5,
      vacation_days_before: 12, vacation_days_after: 12,
      affected_absences: 0,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '24' } });
    await flushDebounce();

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hinzufügen/i })).not.toBeDisabled();
  });

  it('bleibt still bei Rundungsrauschen unterhalb der angezeigten Genauigkeit', async () => {
    // Kein exakter Float-Vergleich: 12,500000000000002 h ist derselbe Saldo.
    mockPreview({
      is_retroactive: false,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      overtime_before: 12.5, overtime_after: 12.500000000000002,
      vacation_days_before: 12, vacation_days_after: 11.999999999999998,
      affected_absences: 0,
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '24' } });
    await flushDebounce();

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
