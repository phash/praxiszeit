import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { format } from 'date-fns';
import TimeTracking from './TimeTracking';
import { useSystemStore } from '../stores/systemStore';

// ---------------------------------------------------------------------------
// U2 (Audit 2026-07-31): ein noch LAUFENDER Zeiteintrag (ohne Ende) galt als
// bearbeitbar (geprueft wurde nur „ist von heute"). Das Bearbeiten-Formular
// belegte „Bis" mit dem festen Wert '17:00' vor und schickte `end_time` immer
// mit — der laufende Eintrag wurde also stillschweigend auf 17:00 geschlossen.
// Stempelte die Person danach erneut ein, entstand eine zweite, ueberlappende
// Zeile (es gibt keine Ueberschneidungspruefung); wer lange arbeitet, lief in
// die §4-Pausenpruefung und bekam eine verwirrende Meldung.
// ---------------------------------------------------------------------------

const getMock = vi.fn();
const putMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));
// #502: Rolle je Test umschaltbar (Datumsfeld beim Bearbeiten nur fuer Admins).
let mockRole: 'employee' | 'admin' = 'employee';
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({
    user: {
      id: 'u1', role: mockRole, weekly_hours: 40, work_days_per_week: 5,
      exempt_from_arbzg: false,
    },
  }),
}));
vi.mock('../stores/uiStore', () => ({ useUIStore: () => ({ stampVersion: 0 }) }));

const today = format(new Date(), 'yyyy-MM-dd');

const openEntry = {
  id: 'te-open',
  date: today,
  start_time: '08:00:00',
  end_time: null,
  break_minutes: 0,
  net_hours: 0,
  note: '',
  is_editable: true,
  warnings: [],
  is_sunday_or_holiday: false,
  is_night_work: false,
};

const closedEntry = {
  ...openEntry,
  id: 'te-closed',
  end_time: '16:00:00',
  break_minutes: 30,
  net_hours: 7.5,
};

function mockEntries(entries: unknown[]) {
  getMock.mockImplementation((url: string) => {
    if (url.includes('/settings')) return Promise.resolve({ data: {} });
    if (url.includes('/time-entries')) return Promise.resolve({ data: entries });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TimeTracking />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockRole = 'employee';
  getMock.mockReset();
  putMock.mockReset();
  postMock.mockReset();
  deleteMock.mockReset();
  putMock.mockResolvedValue({ status: 200, data: { ...openEntry, warnings: [] } });
});

describe('<TimeTracking /> laufender Eintrag (U2, Audit 2026-07-31)', () => {
  it('belegt „Bis" beim Bearbeiten eines laufenden Eintrags NICHT mit 17:00 vor', async () => {
    mockEntries([openEntry]);
    renderPage();

    const editBtn = await screen.findByLabelText(/bearbeiten/i);
    fireEvent.click(editBtn);

    const end = screen.getByLabelText('Bis') as HTMLInputElement;
    expect(end.value).toBe('');
    expect(end.required).toBe(false);
  });

  it('schickt `end_time` nicht mit, wenn der Eintrag noch laeuft', async () => {
    mockEntries([openEntry]);
    renderPage();

    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    fireEvent.change(screen.getByLabelText('Notiz'), { target: { value: 'Nachtrag' } });
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);

    await waitFor(() => expect(putMock).toHaveBeenCalled());
    const [url, payload] = putMock.mock.calls[0];
    expect(url).toBe('/time-entries/te-open');
    expect(payload).not.toHaveProperty('end_time');
    expect(payload).toMatchObject({ note: 'Nachtrag', start_time: '08:00' });
  });

  it('Kontrolltest: ein geschlossener Eintrag wird unveraendert mit `end_time` gespeichert', async () => {
    mockEntries([closedEntry]);
    renderPage();

    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    const end = screen.getByLabelText('Bis') as HTMLInputElement;
    expect(end.value).toBe('16:00');
    expect(end.required).toBe(true);

    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(putMock).toHaveBeenCalled());
    expect(putMock.mock.calls[0][1]).toMatchObject({
      start_time: '08:00', end_time: '16:00', break_minutes: 30,
    });
  });
});

// ---------------------------------------------------------------------------
// #491 F4 (Review-Nachzug): auch die Direkteingabe „+ Neuer Eintrag" fragt an
// einem gesetzlichen Feiertag unter der Woche (KV-Dienst an Christi
// Himmelfahrt) nach dem §10-Ausnahmegrund — bisher nur an Sonntagen. Gleiche
// Regel wie im Antragsformular und im Monatsjournal.
// ---------------------------------------------------------------------------

const ASCENSION = '2026-05-14'; // Donnerstag, Christi Himmelfahrt
const SUNDAY = '2026-05-17';
const THURSDAY_BEFORE = '2026-05-07';
const REASON = /Ausnahmegrund/;

function mockEntriesAndHolidays(entries: unknown[]) {
  getMock.mockImplementation((url: string) => {
    if (url.includes('/settings')) return Promise.resolve({ data: {} });
    if (url.includes('/time-entries')) return Promise.resolve({ data: entries });
    if (url.includes('/holidays')) {
      return Promise.resolve({ data: [{ date: ASCENSION, name: 'Christi Himmelfahrt' }] });
    }
    return Promise.resolve({ data: [] });
  });
}

async function openNewEntryWithDate(date: string) {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
  fireEvent.change(screen.getByLabelText('Datum'), { target: { value: date } });
}

describe('<TimeTracking /> §10-Ausnahmegrund bei der Direkteingabe (#491 F4)', () => {
  it('zeigt das Feld an einem gesetzlichen Feiertag unter der Woche', async () => {
    mockEntriesAndHolidays([]);
    await openNewEntryWithDate(ASCENSION);
    expect(await screen.findByLabelText(REASON)).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/holidays?year=2026');
  });

  it('zeigt das Feld weiterhin an einem Sonntag', async () => {
    mockEntriesAndHolidays([]);
    await openNewEntryWithDate(SUNDAY);
    expect(await screen.findByLabelText(REASON)).toBeInTheDocument();
  });

  it('zeigt das Feld an einem normalen Werktag nicht', async () => {
    mockEntriesAndHolidays([]);
    await openNewEntryWithDate(THURSDAY_BEFORE);
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/holidays?year=2026'));
    expect(screen.queryByLabelText(REASON)).not.toBeInTheDocument();
  });

  it('fragt die Feiertage erst ab, wenn das Formular offen ist', async () => {
    mockEntriesAndHolidays([]);
    renderPage();
    await screen.findByRole('button', { name: /Neuer Eintrag/ });
    expect(getMock.mock.calls.some(([url]) => String(url).includes('/holidays'))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// #499: Mandanten-Schalter für „Pflicht-Pause war nicht möglich". Aus → die
// Checkbox erscheint gar nicht erst; der §4-Hinweis bleibt eine harte Sperre.
// ---------------------------------------------------------------------------
describe('<TimeTracking /> Pflicht-Pause-Ausnahme (#499)', () => {
  async function editWithoutBreak() {
    mockEntries([closedEntry]); // 08:00–16:00
    renderPage();
    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    fireEvent.change(screen.getByLabelText('Pause (Min.)'), { target: { value: '0' } });
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
  }

  it('bietet die Checkbox an, solange die Ausnahme erlaubt ist (Default)', async () => {
    useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
    await editWithoutBreak();
    expect(await screen.findByText('Pflicht-Pause war nicht möglich')).toBeInTheDocument();
    expect(putMock).not.toHaveBeenCalled();
  });

  it('blendet die Checkbox aus und nennt den Grund, wenn die Praxis sie abgeschaltet hat', async () => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', break_exception_allowed: false },
      isLoaded: true,
    });
    await editWithoutBreak();
    expect(await screen.findByText(/mind\. 30 Min\. Pause/)).toBeInTheDocument();
    expect(screen.getByText(/in dieser Praxis abgeschaltet/)).toBeInTheDocument();
    expect(screen.queryByText('Pflicht-Pause war nicht möglich')).not.toBeInTheDocument();
    expect(putMock).not.toHaveBeenCalled();
  });

  it('schickt eine vorhandene Begründung nicht mit, wenn die Ausnahme abgeschaltet ist', async () => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', break_exception_allowed: false },
      isLoaded: true,
    });
    mockEntries([{ ...closedEntry, break_waiver_reason: 'Altfall' }]);
    renderPage();
    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(putMock).toHaveBeenCalled());
    expect(putMock.mock.calls[0][1]).not.toHaveProperty('break_waiver_reason');
  });
});

// ---------------------------------------------------------------------------
// #502: Mitarbeitende verschieben einen Eintrag nicht ueber das Datumsfeld des
// Bearbeiten-Formulars auf einen anderen Tag — der Server lehnt das mit 403 ab
// (Einträge vergangener Tage nur per Änderungsantrag). Das Feld ist beim
// Bearbeiten deshalb gesperrt und sagt, warum; Admins behalten es.
// ---------------------------------------------------------------------------
describe('<TimeTracking /> Datum beim Bearbeiten (#502)', () => {
  // #502-Review: der Hinweis muss einen Weg nennen, den es fuer DIESEN Eintrag
  // gibt. Gesperrt ist das Feld nur bei heutigen (bearbeitbaren) Eintraegen —
  // deren Zeile bietet nur Bearbeiten/Loeschen, der Zeilen-Knopf
  // „Änderungsantrag" erscheint erst auf gesperrten Zeilen. Der tatsaechliche
  // Weg: Eintrag loeschen + oben ueber „Antrag" den vergangenen Tag beantragen.
  const HINT = /Eintrag löschen und oben über „Antrag“/;

  it('sperrt das Datumsfeld beim Bearbeiten fuer Mitarbeitende und nennt den Weg', async () => {
    mockEntries([closedEntry]);
    renderPage();
    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));

    const dateInput = screen.getByLabelText('Datum') as HTMLInputElement;
    expect(dateInput.disabled).toBe(true);
    expect(dateInput.value).toBe(today);
    const hint = screen.getByText(HINT);
    expect(dateInput.getAttribute('aria-describedby')).toBe(hint.id);
    // Der genannte Weg existiert: Knopf „Antrag" oben, Loeschen in der Zeile —
    // und KEIN Zeilen-Änderungsantrag, auf den ein anderer Wortlaut verwiese.
    expect(screen.getByTitle('Antrag für vergangenen Tag stellen')).toBeInTheDocument();
    expect(screen.getByLabelText(/Eintrag vom .* löschen/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Änderungsantrag für/)).not.toBeInTheDocument();
  });

  it('beschriftet den genannten Knopf „Antrag" auf jeder Breite', async () => {
    // #502-Review: der Hinweis verweist auf den Knopf über seine Beschriftung.
    // Unter 640 px stand dort bis dahin nur das Symbol (`hidden sm:inline`) —
    // wer am Handy einen Knopf „Antrag" suchte, fand keinen. jsdom wendet kein
    // CSS an, deshalb prüft der Test die Klassen zwischen Text und Knopf.
    mockEntries([]);
    renderPage();
    const button = await screen.findByRole('button', { name: 'Antrag' });
    const label = within(button).getByText('Antrag');
    for (let el: HTMLElement | null = label; el && el !== button.parentElement; el = el.parentElement) {
      expect(el.className).not.toMatch(/(^|\s)hidden(\s|$)/);
    }
  });

  it('schickt beim Speichern weiterhin das heutige Datum mit', async () => {
    mockEntries([closedEntry]);
    renderPage();
    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(putMock).toHaveBeenCalled());
    expect(putMock.mock.calls[0][1]).toMatchObject({ date: today });
  });

  it('laesst das Datumsfeld beim NEUEN Eintrag offen', async () => {
    mockEntries([]);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    expect((screen.getByLabelText('Datum') as HTMLInputElement).disabled).toBe(false);
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it('laesst Admins das Datum beim Bearbeiten aendern', async () => {
    mockRole = 'admin';
    mockEntries([closedEntry]);
    renderPage();
    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    expect((screen.getByLabelText('Datum') as HTMLInputElement).disabled).toBe(false);
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });
});
