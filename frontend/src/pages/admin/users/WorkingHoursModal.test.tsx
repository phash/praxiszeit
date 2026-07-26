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

function historyResponse(rows: Array<{ id: string; effective_from: string; weekly_hours: number; note?: string }>) {
  return {
    data: rows.map((r) => ({ user_id: 'u1', created_at: '2026-01-01T10:00:00Z', ...r })),
  };
}

function previewResponse(overrides: Partial<{
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
}> = {}) {
  return {
    data: {
      is_retroactive: true,
      period_start: '2026-06-01',
      period_end: '2026-07-26',
      current_daily_target: 8,
      new_daily_target: 6,
      affected_absences: 2,
      blocked_reason: null,
      closed_years: [],
      closed_year_warning: null,
      ...overrides,
    },
  };
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
    await screen.findByText(/Ab 01\.01\.2026 bis 28\.02\.2026: 30 Std\/Woche/);
    expect(screen.getByText(/Ab 01\.03\.2026 bis heute: 40 Std\/Woche/)).toBeInTheDocument();
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
    expect(screen.getByText(/8\.0h → 6\.0h/)).toBeInTheDocument();
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
    expect(screen.getByText(/Aktuell: 40 Std\/Woche/)).toBeInTheDocument();

    // Today's date (not retroactive) — no preview/confirmation needed, keeps
    // this test focused on the post-save refresh.
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByText(/erfolgreich hinzugefügt/);

    // Header must reflect the NEW value — not the stale `currentWeeklyHours` prop.
    await waitFor(() => expect(screen.getByText(/Aktuell: 20 Std\/Woche/)).toBeInTheDocument());
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
