import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider } from '../../../contexts/ToastContext';
import WorkingHoursModal from './WorkingHoursModal';
import type { WorkingHoursChangePreview } from './workingHoursTypes';
import type { WeekBlocks } from '../../../types/workBlocks';
import { JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT } from './workingHoursTexts';

// Same pattern as UserForm.test.tsx: mock the API client, expose the mocks so
// each test can configure GET (list vs. preview), POST and DELETE responses.
const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
const deletePreviewMock = vi.fn();
// Spec 11.1: die Vorschau ist seit PR3 ein POST mit JSON-Body. Die Bestandstests
// prüfen weiterhin `getMock`-Aufrufe mit `params` — der Body wird dafür als
// `params` durchgereicht; `transport` hält fest, was WIRKLICH gesendet wurde.
const transport: { method: string; url: string; body?: unknown }[] = [];
vi.mock('../../../api/client', () => ({
  default: {
    get: (url: string, config?: unknown) => {
      transport.push({ method: 'get', url });
      return getMock(url, config);
    },
    post: (url: string, body?: unknown) => {
      transport.push({ method: 'post', url, body });
      if (String(url).includes('/delete-preview')) return deletePreviewMock(url, body);
      if (String(url).includes('/preview')) return getMock(url, { params: body });
      return postMock(url, body);
    },
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
  blocks?: WeekBlocks | null;
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

type PreviewOverrides = Partial<WorkingHoursChangePreview>;

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
  transport.length = 0;
  deletePreviewMock.mockReset().mockResolvedValue(previewResponse({
    is_retroactive: false, affected_absences: 0, is_shortening: false, reset_body: null,
  }));
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
    expect(screen.getByRole('button', { name: /Speichern/i })).not.toBeDisabled();
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

    const submit = screen.getByRole('button', { name: /Speichern/i });
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
    expect(screen.getByText(/Mo 8:00 h → 6:00 h/)).toBeInTheDocument();
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

    const submit = screen.getByRole('button', { name: /Speichern/i });
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

    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
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
    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('Fund A: die Kasten-Überschrift nennt bei blocked_reason weder "Rückwirkende Änderung" noch "Betrifft bereits gebuchte Abwesenheiten"', async () => {
    // Abschluss-Review #431, Fund A: die Überschrift wurde bisher allein über
    // `isRetroactive`/`affectsBookedAbsences` gewählt — beide sind hier FALSE
    // (Zukunftsdatum, `affected_absences` vom Backend im blockierten Fall
    // garantiert 0), der Kasten erscheint aber ausschließlich wegen
    // `blocked_reason`. Ohne den Fix fiel die Überschrift auf "Ändert
    // Überstunden oder Urlaubsverbrauch" — falsch, weil nichts gespeichert
    // wird (der POST würde ohnehin 400 zurückgeben).
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          is_retroactive: false,
          affected_absences: 0,
          overtime_before: 12.5, overtime_after: 12.5,
          vacation_days_before: 10, vacation_days_after: 10,
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

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Änderung nicht möglich/)).toBeInTheDocument();
    expect(within(box).queryByText(/Rückwirkende Änderung/)).not.toBeInTheDocument();
    expect(within(box).queryByText(/Betrifft bereits gebuchte Abwesenheiten/)).not.toBeInTheDocument();
    expect(within(box).queryByText(/Ändert Überstunden oder Urlaubsverbrauch/)).not.toBeInTheDocument();
    expect(within(box).getByText(/existiert bereits eine Änderung/)).toBeInTheDocument();
  });

  it('Fund A: blocked_reason gewinnt die Überschrift auch dann, wenn das Datum zusätzlich rückwirkend ist', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({
          is_retroactive: true,
          affected_absences: 0,
          overtime_before: 12.5, overtime_after: 12.5,
          vacation_days_before: 10, vacation_days_after: 10,
          blocked_reason: 'Für dieses Datum existiert bereits eine Änderung.',
        }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Änderung nicht möglich/)).toBeInTheDocument();
    expect(within(box).queryByText(/Rückwirkende Änderung/)).not.toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(await screen.findByText(/Gespeichert\. 3 Abwesenheiten angepasst\./)).toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
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
    // Ab heute ohne Befund — kein Haken nötig, der Test bleibt beim Nachziehen
    // nach dem Speichern.
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) {
        return Promise.resolve(previewResponse({ is_retroactive: false, affected_absences: 0 }));
      }
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

    // Today's date (not retroactive) and a preview without findings — no
    // confirmation needed, keeps this test focused on the post-save refresh.
    // Review Task 18b: Speichern wartet auf die Vorschau zur neuen Eingabe.
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByText(/Gespeichert/);

    // Header must reflect the NEW value — not the stale `currentWeeklyHours` prop.
    await waitFor(() => expect(screen.getByText(/Aktuell: 20,0 Std\/Woche/)).toBeInTheDocument());
    // The input must also be prefilled with the new value, not reset to 40.
    expect((screen.getByLabelText('Wochenstunden') as HTMLInputElement).value).toBe('20');
  });
});

describe('Fund 4 (Release-Review 1.17.0): Vorschau-Fehler wird sichtbar gemacht', () => {
  // Vorher: `.catch(() => setPreview(null))` ohne jede Rückmeldung → ein
  // sichtbar leerer amber Kasten neben einem gesperrten „Speichern"-Button.
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
    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
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

  it('Fund C: erlaubt Viertelstunden (step 0,25) bei den Tagesfeldern UND dem Wochenstunden-Feld', async () => {
    // Abschluss-Review #431: dieser Dialog ist seit diesem Branch der EINZIGE
    // Weg, die Tagesstunden eines bestehenden Mitarbeiters zu ändern.
    // step="0.5" ließ die native HTML-Validierung 8,25 als Schrittfehler
    // abweisen — das Anlege-Formular (`f-hours-*`) erlaubt 0,25 längst,
    // Numeric(4,2) trägt es, und Handbuch/In-App-Hilfe versprechen es.
    renderModal({ currentUseDailySchedule: true });
    expect(await screen.findByLabelText('Montag')).toHaveAttribute('step', '0.25');
    expect(screen.getByLabelText('Freitag')).toHaveAttribute('step', '0.25');

    fireEvent.click(screen.getByRole('radio', { name: /Gleichmäßig/ }));
    expect(screen.getByLabelText('Wochenstunden')).toHaveAttribute('step', '0.25');
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
    await flushDebounce(); // Review Task 18b: Speichern wartet auf die Vorschau
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
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
    await flushDebounce(); // Review Task 18b: Speichern wartet auf die Vorschau
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
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
    expect(screen.getByText(/−47:30/)).toBeInTheDocument();
    // Tagessoll je Wochentag statt eines Skalars; Tage ohne Soll auf beiden
    // Seiten bleiben weg.
    expect(screen.getByText(/Mo 8:00 h → 6:00 h/)).toBeInTheDocument();
    expect(screen.getByText(/Di 5:00 h → 5:00 h/)).toBeInTheDocument();
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

  it('sperrt Speichern, solange der eingegebene Stand dem gültigen entspricht', async () => {
    mockPreview({ is_retroactive: false, affected_absences: 0 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    const submit = screen.getByRole('button', { name: /Speichern/i });
    expect(submit).toBeDisabled();
    // Ein gesperrter Button ohne Begründung ist genau der Fund-4-Fehler.
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();
    // Review Task 18b: frei erst, wenn die Vorschau zur neuen Eingabe da ist.
    await flushDebounce();
    await waitFor(() => expect(submit).not.toBeDisabled());
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
    expect(within(box).getByText('12 Tage')).toBeInTheDocument();
    expect(within(box).getByText('11 Tage')).toBeInTheDocument();
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

    const submit = screen.getByRole('button', { name: /Speichern/i });
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
    expect(within(box).getByText('−4:00 h')).toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: /Speichern/i })).not.toBeDisabled();
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

const day = (blocks: [string, string][], pause: number | null = 0) => ({
  blocks: blocks.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const NONE = { blocks: [], pause_minutes: 0 };
// Spec 12.1: Anna Beispiel — Mo 08–12 + 15–18, Di 08–12, Do 08–12.
const ANNA_BLOCKS: WeekBlocks = [day([['08:00', '12:00'], ['15:00', '18:00']]), day([['08:00', '12:00']]), NONE,
  day([['08:00', '12:00']]), NONE];
const ANNA_ROW = {
  id: 'c-anna', effective_from: '2026-03-01', weekly_hours: 15, use_daily_schedule: true,
  hours_monday: 7, hours_tuesday: 4, hours_wednesday: 0, hours_thursday: 4, hours_friday: 0,
  work_days_per_week: 3, blocks: ANNA_BLOCKS,
};
const ANNA_PROPS = {
  currentWeeklyHours: 15, currentUseDailySchedule: true, currentDayHours: [7, 4, 0, 4, 0],
  currentWorkDays: 3, currentBlocks: ANNA_BLOCKS,
};
// Spec 4.4: Altzeile aus Migration 073 — Pausen NULL, Altwerte unverändert.
const LEGACY_DAY = (blocks: [string, string][]) => day(blocks, null);
const LEGACY_BLOCKS: WeekBlocks = [LEGACY_DAY([['07:37', '16:30']]), LEGACY_DAY([]), LEGACY_DAY([]), LEGACY_DAY([]),
  LEGACY_DAY([['07:30', '23:59']])];
const LEGACY_ROW = { id: 'c-legacy', effective_from: '2026-01-01', weekly_hours: 40, blocks: LEGACY_BLOCKS };

function mockHistory(rows: Array<HistoryRow>, overrides: PreviewOverrides = {}) {
  getMock.mockImplementation((url: string) => {
    if (String(url).includes('/preview')) return Promise.resolve(previewResponse(overrides));
    return Promise.resolve(historyResponse(rows));
  });
}
const QUIET: PreviewOverrides = { is_retroactive: false, affected_absences: 0, period_start: '2026-07-26', period_end: '2026-07-26' };
const previewPosts = () => transport.filter((t) => t.method === 'post' && t.url.endsWith('/working-hours-changes/preview'));

describe('Spec 2026-10-08 (PR3): Block-Modus und POST-Vorschau', () => {
  it('öffnet mit heute gültigen Blöcken im Block-Modus und meldet „nichts zu speichern"', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.getByRole('heading', { name: 'Arbeitszeit & Wochenstunden' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' })).toBeChecked();
    expect(screen.getByLabelText('Mo Block 2 bis')).toHaveValue('18:00');
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
  });

  it('Review Focus 5: 7:55 h bleibt nach dem Speichern als 7,92 h ohne Scheinunterschied', async () => {
    const blocks: WeekBlocks = [day([['07:30', '12:00'], ['13:00', '16:25']]), NONE, NONE, NONE, NONE];
    mockHistory([{
      id: 'c1', effective_from: '2026-03-01', weekly_hours: 7.92, use_daily_schedule: true,
      hours_monday: 7.92, hours_tuesday: 0, hours_wednesday: 0, hours_thursday: 0, hours_friday: 0,
      work_days_per_week: 1, blocks,
    }], QUIET);
    renderModal({
      currentWeeklyHours: 7.92, currentUseDailySchedule: true, currentDayHours: [7.92, 0, 0, 0, 0],
      currentWorkDays: 1, currentBlocks: blocks,
    });
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.getByTestId('wh-blocks-day-0')).toHaveTextContent('Tagessoll 7:55 h');
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
  });

  it('Vorschau und Speichern senden nur die Blöcke — per POST mit JSON-Body, nie als Query', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '17:00' } });
    await flushDebounce();

    await waitFor(() => {
      const body = previewPosts().at(-1)?.body as Record<string, unknown>;
      expect(body.effective_from).toBe('2026-07-26');
      expect((body.blocks as WeekBlocks)[0].blocks[1]).toEqual({ start: '15:00', end: '17:00' });
      for (const key of ['weekly_hours', 'use_daily_schedule', 'work_days_per_week', 'hours_monday']) {
        expect(body).not.toHaveProperty(key);
      }
    });
    expect(transport.some((t) => t.method === 'get' && t.url.includes('/preview'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const [url, body] = postMock.mock.calls.at(-1)!;
    expect(url).toBe('/admin/users/u1/working-hours-changes');
    expect(body).toMatchObject({ effective_from: '2026-07-26', note: '' });
    expect((body as { blocks: WeekBlocks }).blocks[0].blocks[1].end).toBe('17:00');
    expect(body).not.toHaveProperty('weekly_hours');
  });

  it('stabiler Effekt-Schlüssel: eine Vorschau je Eingabepause, Notiz und gleicher Wert lösen keine aus', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    await flushDebounce();
    expect(previewPosts()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Notiz (optional)'), { target: { value: 'Umstellung' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    await flushDebounce();
    expect(previewPosts()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '14:30' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '17:30' } });
    await flushDebounce();
    expect(previewPosts()).toHaveLength(2);
  });

  it('Review Focus 1: unfertige Eingabe → blocked_reason aus der Vorschau, Speichern gesperrt, kein Haken', async () => {
    mockHistory([ANNA_ROW], { ...QUIET, blocked_reason: 'Mo, Block 3: Uhrzeit im Format HH:MM angeben.' });
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText('Mo, Block 3: Uhrzeit im Format HH:MM angeben.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 3: Uhrzeit im Format HH:MM angeben.');
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('Bestätigung Pflicht bei affected_time_entries > 0 — Wirkungsdatum heute', async () => {
    mockPreview({ ...QUIET, affected_time_entries: 2 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Betrifft bereits erfasste Zeiteinträge/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(submit).not.toBeDisabled();
  });

  it('Bestätigung Pflicht bei affected_time_entries > 0 — Wirkungsdatum in der Vergangenheit', async () => {
    mockPreview({ affected_absences: 0, affected_time_entries: 3 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '45' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Rückwirkende Änderung/)).toBeInTheDocument();
    expect(within(box).getByText(/Zeiteinträge: 3 neu berechnet/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled();
  });

  it('kein Haken, wenn Einträge und Abwesenheiten 0 sind und Saldo/Urlaub gleich bleiben (Datum heute)', async () => {
    mockPreview({ ...QUIET, affected_time_entries: 0 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled();
  });

  it('Rechtshinweise stehen fest unter dem Editor, Plan-Hinweise kommen aus der Vorschau', async () => {
    const notice = 'Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig.';
    mockHistory([ANNA_ROW], { ...QUIET, block_break_notices: [notice] });
    renderModal(ANNA_PROPS);
    expect(await screen.findByText(LEGAL_HINT)).toBeInTheDocument();
    expect(screen.getByText(JARBSCHG_HINT)).toBeInTheDocument();
    await flushDebounce();
    const list = await screen.findByRole('list', { name: 'Hinweise zum Plan' });
    expect(within(list).getByText(notice)).toBeInTheDocument();
  });

  it('Moduswechsel weg von Blöcken nennt das Ende der Blöcke (P24)', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.queryByText(/Die Arbeitszeit-Blöcke enden/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /Gleichmäßig/ }));
    expect(screen.getByText('Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab 26.07.2026 wird nicht mehr gekappt.'))
      .toBeInTheDocument();
  });

  it('track_hours=false: kein Block-Modus, Blöcke „ohne Wirkung", jede Änderung beendet sie (P24)', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal({ ...ANNA_PROPS, trackHours: false });
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
    // Kopfzeile + Verlaufszeile
    expect(screen.getAllByText(/^Arbeitszeit-Blöcke gespeichert, ohne Wirkung \(keine Stundenzählung\): Mo 08:00/))
      .toHaveLength(2);
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Montag'), { target: { value: '8' } });
    expect(screen.getByText(/Die Arbeitszeit-Blöcke enden mit dieser Änderung/)).toBeInTheDocument();
    await flushDebounce();
    expect(previewPosts().at(-1)?.body).not.toHaveProperty('blocks');
  });

  it('Altfenster: Kasten mit Werten, „Fenster entfernen" sendet remove_legacy_window', async () => {
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    const box = screen.getByRole('group', { name: LEGACY_BOX_TITLE });
    expect(within(box).getByText('Mo 07:37–16:30 / Fr 07:30–23:59')).toBeInTheDocument();
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();

    fireEvent.click(within(box).getByRole('button', { name: 'Fenster entfernen' }));
    expect(within(box).getByRole('button', { name: 'Fenster behalten' })).toBeInTheDocument();
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();
    await flushDebounce();
    expect(previewPosts().at(-1)?.body).toMatchObject({ remove_legacy_window: true, use_daily_schedule: false });
  });

  it('Review Focus 4: „In Arbeitszeit-Blöcke umwandeln" zeigt Altwerte unverändert, verlangt Raster und Pause', async () => {
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    fireEvent.click(screen.getByRole('button', { name: 'In Arbeitszeit-Blöcke umwandeln' }));

    expect(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' })).toBeChecked();
    expect(screen.getByLabelText('Mo Block 1 von')).toHaveValue('07:37');
    expect(screen.getByLabelText('Fr Block 1 bis')).toHaveValue('23:59');
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).');
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '07:35' } });
    fireEvent.change(screen.getByLabelText('Fr Block 1 bis'), { target: { value: '16:00' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Mo: Pause angeben (0, wenn keine).');
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('Fr Pause innerhalb der Blöcke (Min)'), { target: { value: '0' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await flushDebounce();
    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  it('Verlauf zeigt die Blöcke jeder Zeile, Altzeilen als Altbestand', async () => {
    mockHistory([LEGACY_ROW, ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    expect(await screen.findByText(`${LEGACY_BOX_TITLE}: Mo 07:37–16:30 / Fr 07:30–23:59`)).toBeInTheDocument();
    expect(screen.getAllByText('Arbeitszeit-Blöcke: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00'))
      .toHaveLength(2); // Kopfzeile + Verlaufszeile
  });

  it('Toast nach dem Speichern nennt Einträge, Übersprungene und Abwesenheiten (12.1)', async () => {
    mockPreview(QUIET);
    postMock.mockResolvedValue({ data: {
      id: 'c-x', adjusted_time_entries: 3, skipped_time_entries: 1, adjusted_absences: 1, warning: null,
    } });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    expect(await screen.findByText('Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen, 1 Abwesenheit angepasst.'))
      .toBeInTheDocument();
  });
});

describe('Review Task 18b', () => {
  it('track_hours=false: „Fenster entfernen" lässt sich speichern und sendet remove_legacy_window', async () => {
    // Ohne Stundenzählung blendet der Vergleich Blöcke aus (P24) — das
    // ausdrücklich entfernte Altfenster IST aber eine Änderung (der Server
    // vergleicht Blöcke immer, `admin_users._comparable_snapshot`).
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS, trackHours: false });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    const box = screen.getByRole('group', { name: LEGACY_BOX_TITLE });
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();

    fireEvent.click(within(box).getByRole('button', { name: 'Fenster entfernen' }));
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();
    await flushDebounce();
    const submit = screen.getByRole('button', { name: /Speichern/ });
    await waitFor(() => expect(submit).not.toBeDisabled());
    expect(previewPosts().at(-1)?.body).toMatchObject({ remove_legacy_window: true });

    fireEvent.click(submit);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls.at(-1)![1]).toMatchObject({ remove_legacy_window: true });
  });

  it('track_hours=false: der Altfenster-Kasten behauptet keine Kappung', async () => {
    // `work_window_service`: ohne Stundenzählung kappt nichts (track_hours_off).
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS, trackHours: false });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    const box = screen.getByRole('group', { name: LEGACY_BOX_TITLE });
    expect(box).not.toHaveTextContent(/kappt die erfasste Zeit/);
    expect(box).toHaveTextContent('ohne Wirkung (keine Stundenzählung)');

    fireEvent.click(within(box).getByRole('button', { name: 'Fenster entfernen' }));
    expect(box).toHaveTextContent('Das Fenster wird ab 26.07.2026 entfernt.');
    expect(box).not.toHaveTextContent(/nicht mehr gekappt/);
  });

  it('mit Stundenzählung bleiben die Kappungs-Texte des Altfensters', async () => {
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    const box = screen.getByRole('group', { name: LEGACY_BOX_TITLE });
    expect(box).toHaveTextContent('Bleibt mit dieser Änderung bestehen: kappt die erfasste Zeit, ändert das Tagessoll nicht.');
    fireEvent.click(within(box).getByRole('button', { name: 'Fenster entfernen' }));
    expect(box).toHaveTextContent('Das Fenster wird ab 26.07.2026 entfernt; danach wird nicht mehr gekappt.');
  });

  it('Wirkungsdatum heute, nur Zeiteinträge betroffen: kein Satz über umgeschriebene Abwesenheiten', async () => {
    mockPreview({ ...QUIET, affected_time_entries: 2, affected_absences: 0 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Betrifft bereits erfasste Zeiteinträge/)).toBeInTheDocument();
    expect(screen.queryByText(/Abwesenheiten werden trotzdem umgeschrieben/)).not.toBeInTheDocument();
  });

  it('blocked_reason ab heute: kein Satz über umgeschriebene Abwesenheiten', async () => {
    mockPreview({ ...QUIET, blocked_reason: 'Eine Stundenänderung für den 26.07.2026 existiert bereits' });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    await screen.findByText('Eine Stundenänderung für den 26.07.2026 existiert bereits');
    expect(screen.queryByText(/Abwesenheiten werden trotzdem umgeschrieben/)).not.toBeInTheDocument();
  });

  it('Speichern ist gesperrt, solange die Vorschau zur neuen Eingabe noch lädt (Enter direkt nach der Eingabe)', async () => {
    // Spec 9.4/12.1: der Haken ist Pflicht, sobald `affected_time_entries > 0`
    // — auch bei Wirkungsdatum heute. Die alte Vorschau (ohne Befund) darf ihn
    // nicht umgehen, solange die neue noch unterwegs ist.
    getMock.mockImplementation((url: string, cfg?: { params?: Record<string, unknown> }) => {
      if (String(url).includes('/preview')) {
        const changed = cfg?.params?.weekly_hours === 20;
        return Promise.resolve(previewResponse({ ...QUIET, ...(changed ? { affected_time_entries: 2 } : {}) }));
      }
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    await flushDebounce();

    const input = screen.getByLabelText('Wochenstunden');
    fireEvent.change(input, { target: { value: '20' } });
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    fireEvent.submit(input.closest('form')!);
    await flushDebounce(50);
    expect(postMock).not.toHaveBeenCalled();

    await flushDebounce();
    fireEvent.click(await screen.findByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
  });

  it('fällt die Vorschau aus, bleibt ein Speichern ab heute möglich', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/preview')) return Promise.reject({ response: { data: { detail: 'Netzwerkfehler' } } });
      return Promise.resolve(historyResponse([]));
    });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await waitFor(() => expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled());
  });
});
