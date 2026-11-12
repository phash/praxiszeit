import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { format } from 'date-fns';
import AdminAbsences from './AdminAbsences';

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
}));
let reasonsData: unknown[] = [];
vi.mock('../../api/absenceReasons', () => ({ myReasons: () => Promise.resolve(reasonsData) }));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => toast }));

const closure = {
  id: 'c1',
  name: 'Weihnachten',
  start_date: '2026-12-21',
  end_date: '2026-12-31',
  counts_as_vacation: true,
  affected_employees: 3,
};
const STALE =
  'Jahresabschluss 2026 bereits erfolgt — Carryover 2027 ist nun veraltet, bitte Jahresabschluss erneut ausführen.';

beforeEach(() => {
  reasonsData = [];
  getMock.mockReset();
  postMock.mockReset();
  putMock.mockReset();
  deleteMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
  getMock.mockImplementation((url: string) =>
    url === '/company-closures'
      ? Promise.resolve({ data: [closure] })
      : Promise.resolve({ data: [] }),
  );
});

async function openClosuresTab() {
  render(<AdminAbsences />);
  fireEvent.click(screen.getByRole('button', { name: 'Betriebsferien' }));
  return screen.findByLabelText('Betriebsferien bearbeiten');
}

// Gesamtreview 1.20 B5 (Nachzug): Anlegen und Ändern einer Schließung, die
// Buchungen in einem Jahr mit Jahresabschluss ändert, antworten mit
// `warning` (veralteter Übertrag) — wie das Löschen. Die Seite muss sie zeigen.
describe('<AdminAbsences /> Betriebsferien: Jahresabschluss-Warnung', () => {
  it('zeigt die Warnung nach dem Speichern einer geänderten Schließung', async () => {
    putMock.mockResolvedValue({ data: { ...closure, warning: STALE } });
    fireEvent.click(await openClosuresTab());
    fireEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/company-closures/c1', expect.any(Object)));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(STALE));
    expect(toast.success).toHaveBeenCalled();
  });

  it('zeigt die Warnung nach dem Anlegen einer Schließung', async () => {
    postMock.mockResolvedValue({ data: { ...closure, id: 'c2', warning: STALE } });
    await openClosuresTab();
    fireEvent.click(screen.getByRole('button', { name: 'Betriebsferien erstellen' }));
    fireEvent.change(screen.getByPlaceholderText('z.B. Betriebsferien Sommer 2026'), {
      target: { value: 'Nachtrag' },
    });
    const [, bis] = Array.from(document.querySelectorAll('form input[type="date"]'));
    fireEvent.change(bis, { target: { value: '2026-12-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Betriebsferien erstellen & Urlaub eintragen' }));
    // abw-04: Anlegen verlangt die ausdrückliche Bestätigung.
    fireEvent.click(await screen.findByRole('button', { name: 'Anlegen' }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(STALE));
  });

  it('bleibt ohne Warnung still', async () => {
    putMock.mockResolvedValue({ data: { ...closure, warning: null } });
    fireEvent.click(await openClosuresTab());
    fireEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.warning).not.toHaveBeenCalled();
  });
});

// P3 (Handbuch-Grafik): Voll-Tag-Typen buchen das Tagessoll laut Vertrag (Server);
// das Formular darf keine erfundene Zahl (8) vorbelegen. Nur OVERTIME behält Stunden.
describe('<AdminAbsences /> Stundenfeld im Formular', () => {
  async function openForm() {
    getMock.mockImplementation((url: string) => {
      if (url === '/admin/users')
        return Promise.resolve({
          data: [{ id: 'u1', first_name: 'Anna', last_name: 'Test', is_active: true }],
        });
      return Promise.resolve({ data: [] });
    });
    render(<AdminAbsences />);
    const select = await screen.findByTestId('absence-employee-filter');
    await screen.findByRole('option', { name: 'Anna Test' });
    fireEvent.change(select, { target: { value: 'u1' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Abwesenheit eintragen' }));
    return screen.findByLabelText(/^Stunden/);
  }

  it('Urlaub: Feld gesperrt, leer, Hinweis auf Tagessoll', async () => {
    const hours = (await openForm()) as HTMLInputElement;
    expect(hours).toBeDisabled();
    expect(hours.value).not.toBe('8');
    expect(hours.value).toBe('');
    expect(screen.getByText(/Tagessoll laut Vertrag/)).toBeInTheDocument();
  });

  it('Überstundenausgleich: Feld editierbar, Wert wird gesendet', async () => {
    postMock.mockResolvedValue({ data: {} });
    const hours = (await openForm()) as HTMLInputElement;
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'overtime' } });
    expect(hours).not.toBeDisabled();
    expect(hours.value).toBe('');
    fireEvent.change(hours, { target: { value: '3.5' } });
    fireEvent.click(screen.getByRole('button', { name: "Speichern" }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ type: 'overtime', hours: 3.5, user_id: 'u1' });
  });

  it('Urlaub: sendet weiterhin einen gültigen Stundenwert (Server ignoriert ihn)', async () => {
    postMock.mockResolvedValue({ data: {} });
    await openForm();
    fireEvent.click(screen.getByRole('button', { name: "Speichern" }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ type: 'vacation' });
    expect(postMock.mock.calls[0][1].hours).toBeGreaterThan(0);
  });

  const reason = (id: string, base_behavior: string) => ({
    id, name: `Grund ${id}`, color: null, base_behavior, is_active: true, sort_order: 0, tracks_child_sick_limit: false,
  });

  it('eigener Grund Überstundenabbau: Feld editierbar, Wert wird gesendet, kein Halbtag', async () => {
    reasonsData = [reason('r1', 'overtime_comp')];
    postMock.mockResolvedValue({ data: {} });
    const hours = (await openForm()) as HTMLInputElement;
    await screen.findByRole('option', { name: 'Grund r1' });
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'reason:r1' } });
    expect(hours).not.toBeDisabled();
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
    fireEvent.change(hours, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ reason_id: 'r1', hours: 2, half_day: false });
  });

  it('eigener Grund „bezahlt frei" nach Überstundenausgleich: Feld wieder gesperrt, Halbtag da', async () => {
    reasonsData = [reason('r2', 'paid_free')];
    const hours = (await openForm()) as HTMLInputElement;
    await screen.findByRole('option', { name: 'Grund r2' });
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'overtime' } });
    expect(hours).not.toBeDisabled();
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
    fireEvent.change(screen.getByDisplayValue('Überstundenausgleich'), { target: { value: 'reason:r2' } });
    expect(hours).toBeDisabled();
    expect(hours.value).toBe('');
    expect(screen.getByLabelText(/Halber Tag/)).toBeInTheDocument();
  });

  it('Hinweis beim Überstundenausgleich nennt den Tagesplan-Fall', async () => {
    await openForm();
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'overtime' } });
    expect(screen.getByText(/bei Tagesplan wird das Tagessoll des Tages gebucht/)).toBeInTheDocument();
  });
});

// Code-Review 2026-11-11 (Slice abw)
describe('<AdminAbsences /> Review abw', () => {
  const cur = format(new Date(), 'yyyy-MM');
  const prevMonthLast = format(new Date(new Date().getFullYear(), new Date().getMonth(), 0), 'yyyy-MM-dd');

  async function openEmployee(rows: unknown[]) {
    getMock.mockImplementation((url: string) => {
      if (url === '/admin/users')
        return Promise.resolve({ data: [{ id: 'u1', first_name: 'Anna', last_name: 'Test', is_active: true }] });
      if (url.startsWith('/absences?')) return Promise.resolve({ data: rows });
      return Promise.resolve({ data: [] });
    });
    render(<AdminAbsences />);
    const select = await screen.findByTestId('absence-employee-filter');
    await screen.findByRole('option', { name: 'Anna Test' });
    fireEvent.change(select, { target: { value: 'u1' } });
  }

  const row = (id: string, date: string, end_date: string, note: string) => ({
    id, date, end_date, type: 'vacation', hours: 8, note,
  });

  it('abw-01: Tage des Vormonats erscheinen nicht im Folgemonat (Einzeltage mit Spannen-Ende)', async () => {
    await openEmployee([
      row('a1', prevMonthLast, `${cur}-03`, 'VORMONAT'),
      row('a2', `${cur}-02`, `${cur}-03`, 'DIESMONAT'),
    ]);
    expect(await screen.findByText('DIESMONAT')).toBeInTheDocument();
    expect(screen.queryByText('VORMONAT')).toBeNull();
  });

  it('abw-08: zeigt je Zeile das konkrete Datum mit Wochentag, nie die Spanne', async () => {
    await openEmployee([row('a2', `${cur}-02`, `${cur}-06`, 'X')]);
    const cell = await screen.findByText(/\d{2}\.\d{2}\.\d{4}/);
    expect(cell.textContent).toMatch(/^[A-Za-zäöüÄÖÜ]+, 02\.\d{2}\.\d{4}$/);
    expect(cell.textContent).not.toContain('–');
  });

  it('abw-08: zeigt den Namen des eigenen Abwesenheitsgrunds statt „Sonstiges“', async () => {
    reasonsData = [{ id: 'r1', name: 'Reha', color: null, base_behavior: 'paid_free', is_active: true, sort_order: 0, tracks_child_sick_limit: false }];
    await openEmployee([{ ...row('a2', `${cur}-02`, `${cur}-02`, 'X'), type: 'other', reason_id: 'r1' }]);
    expect(await screen.findByText('Reha', { selector: 'span' })).toBeInTheDocument();
  });

  it('abw-09: Löschfehler zeigt den Grund des Servers', async () => {
    deleteMock.mockRejectedValue({ response: { status: 409, data: { detail: 'Betriebsferien-Tage löscht nur die Verwaltung.' } } });
    await openEmployee([row('a2', `${cur}-02`, `${cur}-02`, 'X')]);
    fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Löschen' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Betriebsferien-Tage löscht nur die Verwaltung.'));
  });

  it('abw-05: Löschen in abgeschlossenem Jahr zeigt die Warnung des Servers', async () => {
    deleteMock.mockResolvedValue({ data: { warning: STALE } });
    await openEmployee([row('a2', `${cur}-02`, `${cur}-02`, 'X')]);
    fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Löschen' }));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(STALE));
  });

  it('abw-04: Betriebsferien anlegen sendet erst nach der Bestätigung', async () => {
    postMock.mockResolvedValue({ data: {} });
    render(<AdminAbsences />);
    fireEvent.click(screen.getByRole('button', { name: 'Betriebsferien' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Betriebsferien erstellen' }));
    fireEvent.change(screen.getByPlaceholderText('z.B. Betriebsferien Sommer 2026'), { target: { value: 'Nachtrag' } });
    const [, bis] = Array.from(document.querySelectorAll('form input[type="date"]'));
    fireEvent.change(bis, { target: { value: '2026-12-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Betriebsferien erstellen & Urlaub eintragen' }));
    expect(await screen.findByText(/gestempelten Zeiteinträge/)).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Anlegen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
  });
});
