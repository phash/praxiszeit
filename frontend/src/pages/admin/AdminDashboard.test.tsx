import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import AdminDashboard from './AdminDashboard';

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
  // authStore.ts pulls these named exports in transitively (pattern from Users.test.tsx).
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

function yearlyRow(id: string, first: string, last: string, remaining: number, warn: boolean) {
  return {
    user_id: id, first_name: first, last_name: last,
    vacation_days: 10, remaining_vacation_days: remaining,
    sick_days: 0, training_days: 0, other_days: 0, overtime_comp_days: 0,
    overtime_year: 0, total_days: 10,
    has_year_end_warning: warn,
  };
}

function mockEndpoints(yearly: unknown[]) {
  getMock.mockImplementation((url: string) => {
    if (url.startsWith('/admin/reports/yearly-absences')) return Promise.resolve({ data: yearly });
    if (url.startsWith('/admin/reports/')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: null });
  });
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  postMock.mockResolvedValue({ data: {} });
  putMock.mockReset();
  putMock.mockResolvedValue({ data: { warnings: [] } });
  deleteMock.mockReset();
  deleteMock.mockResolvedValue({ data: {} });
  // Nur Date faken (Q4 des laufenden Jahres) — echte Timer für findBy/waitFor.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-15T10:00:00'));
});

afterEach(() => {
  vi.useRealTimers();
});

// #501: Die plakative Jahresend-Warnung listete JEDEN Rest > 0 — Teilzeitkräfte
// mit 0,3 / 0,5 Tagen landeten im Banner, obwohl diese Bruchteile ins Folgejahr
// wandern und dort zu ganzen Tagen zusammengelegt werden. Die Entscheidung trifft
// jetzt der Server (has_year_end_warning, ab 1,0 Tagen — dieselbe Regel wie im
// Mitarbeiter-Dashboard), das Frontend filtert nicht mehr selbst.
describe('AdminDashboard Jahresend-Warnung (#501)', () => {
  it('nennt nur Mitarbeitende, für die der Server warnt (ab 1,0 Tagen)', async () => {
    mockEndpoints([
      yearlyRow('u1', 'Annika', 'Geier', 0.5, false),
      yearlyRow('u2', 'Aura', 'Haiser', 1.0, true),
      yearlyRow('u3', 'Nadja', 'Jacob', 3.5, true),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const heading = await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);
    const banner = heading.closest('div')!;
    expect(within(banner).getByText(/Aura Haiser/)).toBeInTheDocument();
    expect(within(banner).getByText(/Nadja Jacob/)).toBeInTheDocument();
    expect(within(banner).queryByText(/Annika Geier/)).not.toBeInTheDocument();
  });

  it('zeigt keinen Banner, wenn nur Bruchteile offen sind', async () => {
    mockEndpoints([
      yearlyRow('u1', 'Annika', 'Geier', 0.5, false),
      yearlyRow('u4', 'Larisa', 'Suciu', 0.3, false),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    // Jahresübersicht ist geladen (Name steht in der Tabelle) …
    expect((await screen.findAllByText(/Larisa/)).length).toBeGreaterThan(0);
    // … aber kein Banner.
    expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument();
  });
});

// Gesamtreview 1.20 B5 (#501): Der Banner nannte hart „bis 31.03.{Jahr+1}" —
// eine individuelle Verfallsfrist (users.vacation_carryover_deadline) kam nie an,
// obwohl das Mitarbeiter-Dashboard sie zeigt. Das Datum liefert jetzt der Server
// je Person (carryover_deadline). Die Resttage standen mit Punkt da („3.5 Tage").
describe('AdminDashboard Jahresend-Warnung: Verfallsdatum und Zahlformat (Gesamtreview B5)', () => {
  const withDeadline = (row: ReturnType<typeof yearlyRow>, deadline: string) => ({
    ...row, carryover_deadline: deadline,
  });

  async function banner() {
    const heading = await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);
    return heading.closest('div')!;
  }

  it('nennt das gemeinsame Verfallsdatum aus den Daten und die Resttage mit Komma', async () => {
    mockEndpoints([
      withDeadline(yearlyRow('u2', 'Aura', 'Haiser', 1.0, true), '2027-03-31'),
      withDeadline(yearlyRow('u3', 'Nadja', 'Jacob', 3.5, true), '2027-03-31'),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const b = await banner();
    expect(within(b).getByText(/die bis 31\.03\.2027 verfallen:/)).toBeInTheDocument();
    expect(within(b).getByText('Aura Haiser: 1 Tag')).toBeInTheDocument();
    expect(within(b).getByText('Nadja Jacob: 3,5 Tage')).toBeInTheDocument();
    expect(within(b).queryByText(/3\.5/)).not.toBeInTheDocument();
  });

  it('nennt eine individuelle Frist statt des 31.03.', async () => {
    mockEndpoints([withDeadline(yearlyRow('u3', 'Nadja', 'Jacob', 3.5, true), '2027-06-30')]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const b = await banner();
    expect(within(b).getByText(/die bis 30\.06\.2027 verfallen:/)).toBeInTheDocument();
    expect(within(b).queryByText(/31\.03\./)).not.toBeInTheDocument();
  });

  it('nennt bei unterschiedlichen Fristen das Datum je Person', async () => {
    mockEndpoints([
      withDeadline(yearlyRow('u2', 'Aura', 'Haiser', 1.0, true), '2027-03-31'),
      withDeadline(yearlyRow('u3', 'Nadja', 'Jacob', 3.5, true), '2027-06-30'),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const b = await banner();
    expect(within(b).getByText(/zum jeweils genannten Datum verfallen:/)).toBeInTheDocument();
    expect(within(b).getByText('Aura Haiser: 1 Tag (bis 31.03.2027)')).toBeInTheDocument();
    expect(within(b).getByText('Nadja Jacob: 3,5 Tage (bis 30.06.2027)')).toBeInTheDocument();
  });
});

// Review F3 (#501): Seit der Banner allein am Server-Flag hängt, darf er beim
// Umschalten des Jahres nicht mit der Liste des VORHERIGEN Jahres stehen bleiben —
// weder solange die neue Anfrage läuft noch wenn sie scheitert. Sonst stünden die
// Namen aus 2026 unter „verfallen bis 31.03.2026" für das gewählte Jahr 2025.
describe('AdminDashboard Jahresend-Warnung beim Jahreswechsel (#501, Review F3)', () => {
  function mockWithYear(onOtherYear: () => Promise<unknown>) {
    getMock.mockImplementation((url: string) => {
      if (url.startsWith('/admin/reports/yearly-absences')) {
        if (url.includes('year=2026')) {
          return Promise.resolve({ data: [yearlyRow('u2', 'Aura', 'Haiser', 3.0, true)] });
        }
        return onOtherYear();
      }
      if (url.startsWith('/admin/reports/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: null });
    });
  }

  it('blendet den Banner aus, solange die Anfrage für das neue Jahr läuft', async () => {
    mockWithYear(() => new Promise(() => {})); // hängt
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);

    fireEvent.change(screen.getByLabelText('Jahr'), { target: { value: '2025' } });

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(expect.stringContaining('yearly-absences?year=2025')),
    );
    expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument();
  });

  it('blendet den Banner aus, wenn die Anfrage für das neue Jahr scheitert', async () => {
    mockWithYear(() => Promise.reject(new Error('422')));
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);

    fireEvent.change(screen.getByLabelText('Jahr'), { target: { value: '202' } });

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(expect.stringMatching(/yearly-absences\?year=202$/)),
    );
    await waitFor(() => expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument());
  });
});

// Spec 13.3 / Review Task 15: „Anerkennen" ändert Ist und Saldo des Monats und über
// get_ytd_summary auch „Überstunden Jahr" der Jahresübersicht. Nach dem Anerkennen
// müssen deshalb dieselben Flächen nachladen wie nach Speichern/Löschen (C-2) —
// und die Kacheln im Detail-Modal, die sonst auf der angeklickten Zeile stehen
// bleiben (detailSummary), dürfen nicht den Wert von vor dem Anerkennen zeigen.
describe('AdminDashboard Anerkennen im Detail-Modal (Spec 13.3)', () => {
  const K7 = {
    id: 'e1', date: '2026-10-05', start_time: '07:45:00', end_time: '18:15:00',
    raw_start_time: '07:00:00', raw_end_time: '19:00:00', break_minutes: 0, note: '',
    uncredited_minutes: 150, not_credited_minutes: 240, auto_closed: false,
  };

  function monthlyRow(actual: number) {
    return {
      user_id: 'u1', first_name: 'Anna', last_name: 'Kern', weekly_hours: 40,
      target_hours: 160, actual_hours: actual, balance: actual - 160, overtime_cumulative: actual - 160,
      vacation_used_hours: 0, vacation_used_days: 0, sick_hours: 0, sick_days: 0,
    };
  }

  function mockCreditFlow() {
    let state: 'offen' | 'anerkannt' | 'geloescht' = 'offen';
    postMock.mockImplementation((url: string) => {
      if (url === '/admin/time-entries/e1/credit-override') state = 'anerkannt';
      return Promise.resolve({ data: { warnings: [] } });
    });
    deleteMock.mockImplementation((url: string) => {
      if (url === '/admin/time-entries/e1') state = 'geloescht';
      return Promise.resolve({ data: {} });
    });
    const monthActual = () => ({ offen: 160, anerkannt: 164, geloescht: 152 })[state];
    getMock.mockImplementation((url: string) => {
      if (url.startsWith('/admin/reports/yearly-absences')) {
        return Promise.resolve({ data: [{ ...yearlyRow('u1', 'Anna', 'Kern', 5, false), overtime_year: monthActual() - 160 }] });
      }
      if (url.startsWith('/admin/reports/monthly')) {
        return Promise.resolve({ data: [monthlyRow(monthActual())] });
      }
      if (url.startsWith('/admin/reports/weekly')) {
        // Wochenzahlen — das Modal zeigt trotzdem die Monatszeile (#329).
        const actual = monthActual() - 120;
        return Promise.resolve({ data: [{ ...monthlyRow(actual), target_hours: 40, balance: actual - 40 }] });
      }
      if (url.startsWith('/admin/users/')) {
        return Promise.resolve({ data: { id: 'u1', username: 'akern', email: null, role: 'employee', vacation_days: 30, track_hours: true } });
      }
      if (url === '/time-entries') {
        if (state === 'geloescht') return Promise.resolve({ data: [] });
        return Promise.resolve({ data: [{ ...K7, net_hours: state === 'anerkannt' ? 12 : 8, credit_override: state === 'anerkannt' }] });
      }
      if (url === '/absences') {
        // Misch-Tag (F1): Anerkennen gleicht die Krank-Gutschrift am selben Tag an.
        return Promise.resolve({ data: [{ id: 'a1', date: '2026-10-05', type: 'sick', hours: state === 'anerkannt' ? 4 : 5.25, note: '' }] });
      }
      return Promise.resolve({ data: [] });
    });
  }

  async function openDetail() {
    mockCreditFlow();
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Details für Kern, Anna anzeigen' }))[0]);
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByRole('button', { name: 'Anerkennen' });
    return dialog;
  }

  async function credit(dialog: HTMLElement) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'Anerkennen' }));
    fireEvent.click(screen.getByRole('button', { name: 'Zeit anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/admin/time-entries/e1/credit-override'));
    // Der Bestätigungsdialog liegt im Portal; der Klick darf das Detail-Modal
    // nicht über dessen Overlay (onClick=closeDetail) schließen.
    expect(dialog).toBeInTheDocument();
  }

  const card = (dialog: HTMLElement, label: string) =>
    within(dialog).getByText(label, { selector: 'p' }).nextElementSibling?.textContent;

  afterEach(() => {
    try { localStorage.removeItem('adminDashboardViewMode'); } catch { /* jsdom */ }
  });

  it('lädt die Jahresübersicht nach („Überstunden Jahr")', async () => {
    const yearlyCalls = () => getMock.mock.calls.filter((c) => String(c[0]).includes('yearly-absences')).length;
    const dialog = await openDetail();
    const before = yearlyCalls();
    await credit(dialog);
    await waitFor(() => expect(yearlyCalls()).toBeGreaterThan(before));
  });

  // Gesamtreview 1.20 (Nachzug Fund 1): Anerkennen ändert auch die Stunden einer
  // Abwesenheit am selben Tag — die Liste im Modal muss nachladen, sonst steht dort
  // weiter „Krank 5:15 h", während das Protokoll daneben schon 4,0 h nennt.
  it('lädt die Abwesenheitsliste nach (angeglichene Gutschrift am Misch-Tag)', async () => {
    const dialog = await openDetail();
    await within(dialog).findByText('5:15 h');
    await credit(dialog);
    await within(dialog).findByText('4:00 h');
    expect(within(dialog).queryByText('5:15 h')).not.toBeInTheDocument();
  });

  it('zeigt Ist und Saldo der Detail-Kacheln nach dem Anerkennen neu (Monatsansicht)', async () => {
    const dialog = await openDetail();
    expect(card(dialog, 'Ist')).toBe('160:00');
    await credit(dialog);
    await waitFor(() => expect(card(dialog, 'Ist')).toBe('164:00'));
    expect(card(dialog, 'Saldo')).toBe('+4:00');
  });

  it('zeigt Ist und Saldo der Detail-Kacheln nach dem Anerkennen neu (Wochenansicht)', async () => {
    localStorage.setItem('adminDashboardViewMode', 'week');
    const dialog = await openDetail();
    await waitFor(() => expect(card(dialog, 'Ist')).toBe('160:00'));
    await credit(dialog);
    await waitFor(() => expect(card(dialog, 'Ist')).toBe('164:00'));
    expect(card(dialog, 'Saldo')).toBe('+4:00');
  });

  // P18, Entschieden 2026-10-11 (Produktinhaber): ein echtes Ende 23:59 ist bei
  // einem automatisch geschlossenen Eintrag eintragbar — der Server wertet jedes
  // Ende außer dem gespeicherten wirksamen als Korrektur. Voraussetzung: das
  // Bearbeiten-Formular legt das WIRKSAME Ende ins Feld, nie das Rohende 23:59
  // (auch über die §4-Rückfrage submitWithBreakWaiver geht derselbe Wert).
  it('Bearbeiten eines automatisch geschlossenen Eintrags: „Bis" = wirksames Ende, PUT schickt 18:15', async () => {
    mockCreditFlow();
    const autoClosed = {
      ...K7, start_time: '08:00:00', raw_start_time: null, raw_end_time: '23:59:00',
      not_credited_minutes: 150, auto_closed: true, net_hours: 7.75, credit_override: false,
    };
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) => (
      url === '/time-entries' ? Promise.resolve({ data: [autoClosed] }) : base(url)
    ));
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Details für Kern, Anna anzeigen' }))[0]);
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Eintrag vom 05.10.2026 bearbeiten' }));
    expect((within(dialog).getByLabelText('Bis (Uhrzeit)') as HTMLInputElement).value).toBe('18:15');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(putMock).toHaveBeenCalledWith(
      '/admin/time-entries/e1', expect.objectContaining({ start_time: '08:00', end_time: '18:15' }),
    ));
  });

  it('Löschen aktualisiert die Detail-Kacheln ebenfalls (gleicher Pfad wie Anerkennen)', async () => {
    const dialog = await openDetail();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Eintrag vom 05.10.2026 löschen' }));
    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/admin/time-entries/e1'));
    await waitFor(() => expect(card(dialog, 'Ist')).toBe('152:00'));
    expect(card(dialog, 'Saldo')).toBe('-8:00');
  });
});

// Gesamtreview PR2 (Fund 6): das Änderungsprotokoll im Detail-Modal zeigt
// dieselben Zeilen wie admin/AuditLog.tsx — mit denselben Quellen-Labels
// (constants/auditSources.ts), nicht nur „(Antrag)".
describe('AdminDashboard Änderungsprotokoll im Detail-Modal: Quellen-Labels', () => {
  function log(id: string, source: string) {
    return {
      id, action: 'update', source, created_at: '2026-10-05T10:00:00',
      changed_by_first_name: 'Ada', changed_by_last_name: 'Admin',
      old_date: '2026-10-05', new_date: '2026-10-05',
      old_start_time: '07:45:00', old_end_time: '18:15:00',
      new_start_time: '07:00:00', new_end_time: '19:00:00',
      old_break_minutes: 0, new_break_minutes: 0, old_note: null, new_note: null,
    };
  }

  it('nennt „Anrechnung anerkannt", „Antrag" und lässt „manual" ohne Zusatz', async () => {
    getMock.mockImplementation((url: string) => {
      if (url.startsWith('/admin/reports/yearly-absences')) {
        return Promise.resolve({ data: [yearlyRow('u1', 'Anna', 'Kern', 5, false)] });
      }
      if (url.startsWith('/admin/reports/monthly')) {
        return Promise.resolve({ data: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Kern', weekly_hours: 40,
          target_hours: 160, actual_hours: 160, balance: 0, overtime_cumulative: 0,
          vacation_used_hours: 0, vacation_used_days: 0, sick_hours: 0, sick_days: 0,
        }] });
      }
      if (url.startsWith('/admin/audit-log')) {
        return Promise.resolve({ data: [
          log('l1', 'credit_override'), log('l2', 'change_request'), log('l3', 'manual'),
        ] });
      }
      if (url.startsWith('/admin/users/')) {
        return Promise.resolve({ data: { id: 'u1', username: 'akern', role: 'employee', vacation_days: 30, track_hours: true } });
      }
      return Promise.resolve({ data: [] });
    });
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Details für Kern, Anna anzeigen' }))[0]);
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Änderungsprotokoll (3)');
    const lines = within(dialog).getAllByText(/\| Ada Admin/).map((el) => el.textContent);
    expect(lines).toEqual([
      '05.10. 10:00 | Ada Admin (Anrechnung anerkannt)',
      '05.10. 10:00 | Ada Admin (Antrag)',
      '05.10. 10:00 | Ada Admin',
    ]);
  });
});

describe('Gesamtreview PR3: Wochenstunden im deutschen Zahlenformat', () => {
  it('Tabelle, Mobilkarte und Detail-Modal zeigen 39,58 statt der rohen JS-Zahl 39.58', async () => {
    // Blöcke leiten Wochenstunden mit zwei Nachkommastellen ab (Spec 4.1) —
    // Benutzerliste, Formular, Dialog und Exporte schreiben sie mit Komma.
    getMock.mockImplementation((url: string) => {
      if (url.startsWith('/admin/reports/monthly')) {
        return Promise.resolve({ data: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Kern', weekly_hours: 39.58,
          target_hours: 160, actual_hours: 160, balance: 0, overtime_cumulative: 0,
          vacation_used_hours: 0, vacation_used_days: 0, sick_hours: 0, sick_days: 0,
        }] });
      }
      if (url.startsWith('/admin/reports/')) return Promise.resolve({ data: [] });
      if (url.startsWith('/admin/users/')) {
        return Promise.resolve({ data: { id: 'u1', username: 'akern', email: null, role: 'employee', vacation_days: 30, track_hours: true } });
      }
      return Promise.resolve({ data: [] });
    });
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    const rows = await screen.findAllByRole('button', { name: 'Details für Kern, Anna anzeigen' });
    expect(screen.getByText('39,58')).toBeInTheDocument(); // Tabelle
    expect(screen.getByText('39,58 Std./Woche')).toBeInTheDocument(); // Mobilkarte
    fireEvent.click(rows[0]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('39,58 Std.')).toBeInTheDocument();
    expect(screen.queryByText(/39\.58/)).not.toBeInTheDocument();
  });
});
