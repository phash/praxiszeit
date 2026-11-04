import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import ReducedDaysCard from './ReducedDaysCard';

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
const toastMock = vi.hoisted(() => ({
  error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn(),
}));
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toastMock }));

const year = new Date().getFullYear();
const row = { id: 'r1', date: `${year}-02-16`, label: 'Rosenmontag', max_hours: 4, created_at: '', warning: null };
const row2 = { id: 'r2', date: `${year}-05-15`, label: 'Brückentag', max_hours: 3, created_at: '', warning: null };

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  putMock.mockReset();
  deleteMock.mockReset();
  Object.values(toastMock).forEach((fn) => fn.mockReset());
  getMock.mockResolvedValue({ data: [row] });
});

function fillAdd(date: string, label: string, hours: string, click = true) {
  fireEvent.change(screen.getByLabelText('Datum'), { target: { value: date } });
  fireEvent.change(screen.getByLabelText('Bezeichnung'), { target: { value: label } });
  fireEvent.change(screen.getByLabelText('Höchstens (Stunden)'), { target: { value: hours } });
  if (click) fireEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
}

function confirmDelete() {
  const dialog = screen.getByRole('alertdialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));
}

describe('<ReducedDaysCard />', () => {
  it('lists, adds and deletes reduced days', async () => {
    postMock.mockResolvedValue({ data: { ...row, id: 'r2' } });
    deleteMock.mockResolvedValue({ status: 204, data: '' });
    render(<ReducedDaysCard />);
    expect(await screen.findByText('Rosenmontag')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(`/admin/reduced-days?year=${year}`);
    expect(screen.getByText('Verkürzte Tage')).toBeInTheDocument();

    fillAdd(`${year}-03-01`, 'Brückentag', '3.5');
    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/admin/reduced-days', {
        date: `${year}-03-01`, label: 'Brückentag', max_hours: 3.5,
      }),
    );
    // F043: nach dem Hinzufügen wird die Liste neu geladen, mit Erfolgsmeldung.
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
    expect(toastMock.success).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    // F096: erst nach Rückfrage.
    expect(deleteMock).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Betroffene Betriebsferien werden neu gebucht');
    confirmDelete();
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/admin/reduced-days/r1'));
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(3));
    expect(toastMock.success).toHaveBeenCalledWith('Verkürzter Tag gelöscht.');
  });

  it('F096: cancelling the confirmation deletes nothing', async () => {
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Abbrechen' }));
    expect(deleteMock).not.toHaveBeenCalled();
  });

  it('shows the server error for 24.12.', async () => {
    const detail = 'Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.';
    postMock.mockRejectedValue({ response: { status: 400, data: { detail } } });
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fillAdd(`${year}-12-24`, 'Heiligabend', '4');
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(detail));
  });

  it('shows the closed-year warning', async () => {
    const warning = 'Jahresabschluss bereits erfolgt.';
    postMock.mockResolvedValue({ data: { ...row, id: 'r2', warning } });
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fillAdd(`${year}-03-01`, 'Brückentag', '4');
    await waitFor(() => expect(toastMock.warning).toHaveBeenCalledWith(warning));
  });

  it('F043: edits a row via PUT and shows its warning', async () => {
    const warning = 'Jahresabschluss bereits erfolgt.';
    putMock.mockResolvedValue({ data: { ...row, label: 'Fasching', max_hours: 4.5, warning } });
    render(<ReducedDaysCard />);
    fireEvent.click(await screen.findByText('Rosenmontag'));
    fireEvent.change(screen.getByLabelText('Bezeichnung 16.02.' + year), { target: { value: 'Fasching' } });
    fireEvent.change(screen.getByLabelText('Höchstens (Stunden) 16.02.' + year), { target: { value: '4.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith('/admin/reduced-days/r1', {
        date: `${year}-02-16`, label: 'Fasching', max_hours: 4.5,
      }),
    );
    await waitFor(() => expect(toastMock.warning).toHaveBeenCalledWith(warning));
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
  });

  it('F043: the delete warning is shown', async () => {
    const warning = 'Jahresabschluss bereits erfolgt.';
    deleteMock.mockResolvedValue({ status: 200, data: { warning } });
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    confirmDelete();
    await waitFor(() => expect(toastMock.warning).toHaveBeenCalledWith(warning));
  });

  it('F094: empty or invalid hours block Hinzufügen and row Speichern, with the server wording', async () => {
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fillAdd(`${year}-03-01`, 'Brückentag', '', false);
    expect(screen.getByRole('button', { name: 'Hinzufügen' })).toBeDisabled();
    expect(screen.getByText(/zwischen 0,25 und 12 liegen/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Höchstens (Stunden)'), { target: { value: '4.3' } });
    expect(screen.getByRole('button', { name: 'Hinzufügen' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Höchstens (Stunden)'), { target: { value: '4.5' } });
    expect(screen.getByRole('button', { name: 'Hinzufügen' })).toBeEnabled();

    fireEvent.change(screen.getByLabelText('Höchstens (Stunden) 16.02.' + year), { target: { value: '0' } });
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled();
    expect(postMock).not.toHaveBeenCalled();
    expect(putMock).not.toHaveBeenCalled();
  });

  it('F095: the label button opens the editor on Space and Enter', async () => {
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    const btn = screen.getByRole('button', { name: `Bezeichnung 16.02.${year} bearbeiten: Rosenmontag` });
    fireEvent.keyDown(btn, { key: ' ' });
    expect(screen.getByLabelText('Bezeichnung 16.02.' + year)).toHaveValue('Rosenmontag');
  });

  it('F093: a late response of the previous year does not overwrite the new one', async () => {
    let resolveOld: (v: unknown) => void = () => {};
    getMock.mockReset();
    getMock.mockImplementation((url: string) => {
      if (url === `/admin/reduced-days?year=${year}`) return new Promise((r) => { resolveOld = r; });
      return Promise.resolve({ data: [{ ...row2, date: `${year + 1}-05-15`, label: 'Neues Jahr' }] });
    });
    render(<ReducedDaysCard />);
    fireEvent.change(screen.getByLabelText('Jahr'), { target: { value: String(year + 1) } });
    expect(await screen.findByText('Neues Jahr')).toBeInTheDocument();
    resolveOld({ data: [row] });
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText('Rosenmontag')).not.toBeInTheDocument();
    expect(screen.getByText('Neues Jahr')).toBeInTheDocument();
  });

  it('F097: adding a day of another year switches to that year', async () => {
    postMock.mockResolvedValue({ data: { ...row, id: 'r3' } });
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fillAdd(`${year + 1}-02-08`, 'Rosenmontag', '4');
    await waitFor(() => expect(getMock).toHaveBeenCalledWith(`/admin/reduced-days?year=${year + 1}`));
    expect(screen.getByLabelText('Jahr')).toHaveValue(String(year + 1));
  });

  it('F097: saving one row keeps the unsaved draft of another row', async () => {
    getMock.mockResolvedValue({ data: [row, row2] });
    putMock.mockResolvedValue({ data: { ...row, max_hours: 5 } });
    render(<ReducedDaysCard />);
    await screen.findByText('Rosenmontag');
    fireEvent.change(screen.getByLabelText('Höchstens (Stunden) 15.05.' + year), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Höchstens (Stunden) 16.02.' + year), { target: { value: '5' } });
    const saveButtons = screen.getAllByRole('button', { name: 'Speichern' });
    fireEvent.click(saveButtons[0]);
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Speichern' })).toHaveLength(1));
    expect(screen.getByLabelText('Höchstens (Stunden) 15.05.' + year)).toHaveValue(2);
  });

  it('F132: a load error is shown', async () => {
    getMock.mockReset().mockRejectedValue({ response: { status: 500, data: { detail: 'kaputt' } } });
    render(<ReducedDaysCard />);
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('kaputt'));
  });
});
