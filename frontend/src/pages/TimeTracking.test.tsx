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

describe('<TimeTracking /> RawStampNote (Spec 13.1)', () => {
  it('Tabelle und Mobilkarte nutzen dieselbe Komponente', async () => {
    mockEntries([{
      ...closedEntry, start_time: '07:45:00', raw_start_time: '07:37:00', not_credited_minutes: 8,
    }]);
    renderPage();
    expect(await screen.findAllByText('gestempelt 07:37 · angerechnet ab 07:45')).toHaveLength(2);
  });

  // Die alte Inline-Kopie der Mobilkarte kannte nur die Hüllen-Zeilen — die
  // Lückenzeile beweist, dass auch die Karte die Komponente nutzt.
  it('Lückenzeile in Tabelle UND Mobilkarte', async () => {
    mockEntries([{
      ...closedEntry, start_time: '08:00:00', end_time: '18:00:00', break_minutes: 0, net_hours: 7.5,
      uncredited_minutes: 150, not_credited_minutes: 150,
    }]);
    renderPage();
    expect(await screen.findAllByText(
      'gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet',
    )).toHaveLength(2);
  });
});

describe('<TimeTracking /> Anrechnung beantragen und anerkannte Einträge (Spec P21, P3)', () => {
  const past = {
    ...closedEntry, id: 'te-past', date: '2026-06-01', is_editable: false,
    start_time: '07:45:00', end_time: '18:15:00', raw_start_time: '07:00:00', raw_end_time: '19:00:00',
    break_minutes: 0, net_hours: 8, uncredited_minutes: 150, not_credited_minutes: 240,
    credit_override: false, auto_closed: false,
  };

  it('öffnet an einem vergangenen Eintrag den Antrag mit den Rohstempeln', async () => {
    mockEntries([past]);
    renderPage();
    const [button] = await screen.findAllByRole('button', { name: 'Anrechnung beantragen' });
    fireEvent.click(button);
    expect(await screen.findByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:00');
  });

  it('heutige Einträge bieten die Aktion nicht an (Anträge nur für vergangene Tage)', async () => {
    mockEntries([{ ...past, date: today, is_editable: true }]);
    renderPage();
    await screen.findAllByText(/4:00 h nicht angerechnet/);
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
  });

  // Spec 6.2/13.1: die Aktion hängt an der eigenen Ansicht, nicht an der Rolle.
  // Die Lückentexte der Mitarbeiterpfade (clock_out, create_time_entry) weisen
  // auch Admins, die selbst Zeit erfassen, auf „Zeiterfassung → Eintrag →
  // „Anrechnung beantragen"" hin — wie das Monatsjournal (isAdminView=false).
  it('Admins sehen die Aktion an eigenen vergangenen Einträgen (Spec 6.2, 13.1)', async () => {
    mockRole = 'admin';
    mockEntries([{ ...past, is_editable: true }]);
    renderPage();
    const [button] = await screen.findAllByRole('button', { name: 'Anrechnung beantragen' });
    fireEvent.click(button);
    expect(await screen.findByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
  });

  it('Admins: an heutigen Einträgen auch dort keine Aktion', async () => {
    mockRole = 'admin';
    mockEntries([{ ...past, date: today, is_editable: true }]);
    renderPage();
    await screen.findAllByText(/4:00 h nicht angerechnet/);
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
  });

  it('anerkannter Eintrag eines vergangenen Tages: kein direktes Bearbeiten, nur Antrag', async () => {
    mockEntries([{ ...closedEntry, date: '2026-06-01', is_editable: false, credit_override: true }]);
    renderPage();
    await screen.findAllByLabelText(/Änderungsantrag für/);
    expect(screen.queryByLabelText(/bearbeiten/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Löschantrag für/)).toBeInTheDocument();
    // Mobilkarte: auch dort kein „Bearbeiten", sondern „Ändern" per Antrag.
    expect(screen.queryByRole('button', { name: /bearbeiten/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ändern/ })).toBeInTheDocument();
  });

  // P3 + Antragsregeln: direktes PUT/DELETE → 409, Änderungs- und Löschantrag
  // für heute → 400 (Anträge nur für vergangene Tage). Keine Knöpfe anbieten,
  // die garantiert scheitern — nur der Hinweis.
  it('anerkannter Eintrag von heute: weder Bearbeiten noch Anträge, sondern Hinweis', async () => {
    mockEntries([{ ...closedEntry, credit_override: true }]);
    renderPage();
    expect(await screen.findAllByText(
      'Anerkannter Eintrag – Änderung ab morgen per Änderungsantrag oder über die Verwaltung',
    )).toHaveLength(2);
    expect(screen.queryByLabelText(/bearbeiten/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/löschen/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Änderungsantrag für/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Löschantrag für/)).not.toBeInTheDocument();
    // Mobilkarte: weder „Bearbeiten"/„Löschen" noch „Ändern".
    expect(screen.queryByRole('button', { name: /Bearbeiten|Löschen|Ändern/ })).not.toBeInTheDocument();
  });

  it('Kontrolltest: Admins bearbeiten einen anerkannten Eintrag weiter direkt (P3)', async () => {
    mockRole = 'admin';
    mockEntries([{ ...closedEntry, credit_override: true }]);
    renderPage();
    expect(await screen.findByLabelText(/bearbeiten/i)).toBeInTheDocument();
  });
});

describe('<TimeTracking /> Blöcke von heute (Spec 8.4, 14)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function mockWithBlocks(entries: unknown[]) {
    getMock.mockImplementation((url: string) => {
      if (url === '/time-entries/clock-status') {
        return Promise.resolve({ data: { is_clocked_in: false, blocks_today: BLOCKS, grace_minutes: 15 } });
      }
      if (url.includes('/settings')) return Promise.resolve({ data: {} });
      if (url.includes('/time-entries')) return Promise.resolve({ data: entries });
      return Promise.resolve({ data: [] });
    });
  }

  it('belegt Von/Bis neuer Einträge aus den heutigen Blöcken vor', async () => {
    mockWithBlocks([]);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    await waitFor(() => expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('08:00'));
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('18:00');
  });

  it('verlangt keine Pause und setzt keine automatische Pause, wenn die Lücke §4 deckt (E45)', async () => {
    mockWithBlocks([]);
    postMock.mockResolvedValue({ status: 201, data: { ...closedEntry, warnings: [] } });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    await waitFor(() => expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('18:00'));
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ start_time: '08:00', end_time: '18:00', break_minutes: 0 });
  });

  // Spec 8.2 + E80: bestehende Einträge des Tages gehen mit IHREM Puffer in die
  // §4-Vorprüfung ein. Ihre Lückensegmente zählen als Pause und der gespeicherte
  // `uncredited_minutes` als Abzug — weicht Σ Segmente vom gespeicherten Wert ab,
  // zählt er nur als Abzug (strenge Richtung), wie `break_block_for_entry`.
  // Der Tag 08:00–18:00 hat bei Puffer 15 genau ein Segment: 12:15–14:45 = 150 Min.
  const dayEntry = {
    ...closedEntry, id: 'te-day', start_time: '08:00:00', end_time: '18:00:00',
    break_minutes: 0, uncredited_minutes: 150, clamp_grace_minutes: 15,
  };

  async function submitShortEntryAfter(existing: Record<string, unknown>) {
    useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
    mockWithBlocks([existing]);
    postMock.mockResolvedValue({ status: 201, data: { ...closedEntry, warnings: [] } });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    await waitFor(() => expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('18:00'));
    fireEvent.change(screen.getByLabelText('Von'), { target: { value: '18:00' } });
    fireEvent.change(screen.getByLabelText('Bis'), { target: { value: '18:10' } });
    fireEvent.change(screen.getByLabelText('Pause (Min.)'), { target: { value: '0' } });
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
  }

  it('wertet das Lückensegment eines bestehenden Eintrags als Pause und den gespeicherten Wert als Abzug', async () => {
    // Brutto 600 − 150 + 10 = 460 Min > 6 h, Pause 150 aus dem Segment → kein Hinweis.
    await submitShortEntryAfter(dayEntry);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ start_time: '18:00', end_time: '18:10', break_minutes: 0 });
    expect(screen.queryByText(/ArbZG §4/)).not.toBeInTheDocument();
  });

  it('rechnet streng, wenn Σ Segmente vom gespeicherten Wert abweicht (keine Pausensegmente, Abzug = gespeichert)', async () => {
    // Brutto 600 − 120 + 10 = 490 Min > 6 h, keine Pause → §4-Hinweis (die >9-h-
    // Meldung käme, wenn der gespeicherte Abzug fehlte: 610 Min).
    await submitShortEntryAfter({ ...dayEntry, uncredited_minutes: 120 });
    expect(
      await screen.findByText('Bei >6h Arbeitszeit sind mind. 30 Min. Pause erforderlich (ArbZG §4)'),
    ).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('nimmt den Puffer des Eintrags, nicht den aus /clock-status (E80)', async () => {
    // Puffer 0 → Segment 12:00–15:00 = 180 = gespeichert → Pause 180, kein Hinweis.
    // Mit dem Puffer 15 aus /clock-status wären es 150 ≠ 180 → streng → Hinweis.
    await submitShortEntryAfter({ ...dayEntry, uncredited_minutes: 180, clamp_grace_minutes: 0 });
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ start_time: '18:00', end_time: '18:10', break_minutes: 0 });
    expect(screen.queryByText(/ArbZG §4/)).not.toBeInTheDocument();
  });
});
