import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AdminAbsences from './AdminAbsences';

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: vi.fn(),
  },
}));
vi.mock('../../api/absenceReasons', () => ({ myReasons: () => Promise.resolve([]) }));
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
  getMock.mockReset();
  postMock.mockReset();
  putMock.mockReset();
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
});
