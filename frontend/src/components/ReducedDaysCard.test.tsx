import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReducedDaysCard from './ReducedDaysCard';

const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: vi.fn(),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
const toastMock = vi.hoisted(() => ({
  error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn(),
}));
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toastMock }));

const year = new Date().getFullYear();
const row = { id: 'r1', date: `${year}-02-16`, label: 'Rosenmontag', max_hours: 4, created_at: '', warning: null };

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  deleteMock.mockReset();
  Object.values(toastMock).forEach((fn) => fn.mockReset());
  getMock.mockResolvedValue({ data: [row] });
});

function fillAdd(date: string, label: string, hours: string) {
  fireEvent.change(screen.getByLabelText('Datum'), { target: { value: date } });
  fireEvent.change(screen.getByLabelText('Bezeichnung'), { target: { value: label } });
  fireEvent.change(screen.getByLabelText('Höchstens (Stunden)'), { target: { value: hours } });
  fireEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
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

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/admin/reduced-days/r1'));
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
});
