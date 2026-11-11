import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VacationRequestEditModal from './VacationRequestEditModal';

const patchMock = vi.fn();
vi.mock('../api/client', () => ({ default: { patch: (...a: unknown[]) => patchMock(...a) } }));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));

const half = { id: 'r1', date: '2099-03-02', hours: 8, absence_type: 'vacation', half_day: true };

beforeEach(() => { patchMock.mockReset(); patchMock.mockResolvedValue({}); });

// abw-06 (Review 2026-11-11): Halbtag im Bearbeiten-Dialog, Stundenfeld nur bei Überstundenausgleich.
describe('<VacationRequestEditModal /> Halbtag und Stunden (abw-06)', () => {
  it('zeigt „Halber Tag“ vorbelegt und sendet das Abwählen', async () => {
    render(<VacationRequestEditModal request={half} mode="self" onClose={() => {}} onSaved={() => {}} />);
    const box = screen.getByLabelText(/Halber Tag/) as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(patchMock).toHaveBeenCalled());
    expect(patchMock.mock.calls[0][1]).toEqual({ half_day: false });
  });

  it('Umbau auf einen Zeitraum schickt half_day=false mit (kein 400 vom Server)', async () => {
    render(<VacationRequestEditModal request={half} mode="self" onClose={() => {}} onSaved={() => {}} />);
    fireEvent.click(screen.getByLabelText('Zeitraum (mehrere Tage)'));
    const [, bis] = Array.from(document.querySelectorAll('input[type="date"]'));
    fireEvent.change(bis, { target: { value: '2099-03-04' } });
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(patchMock).toHaveBeenCalled());
    expect(patchMock.mock.calls[0][1]).toMatchObject({ end_date: '2099-03-04', half_day: false });
  });

  it('Stundenfeld nur beim Überstundenausgleich, sonst Hinweis auf das Tagessoll', () => {
    render(<VacationRequestEditModal request={half} mode="self" onClose={() => {}} onSaved={() => {}} />);
    expect(screen.queryByText(/^Stunden/)).toBeNull();
    expect(screen.getByText(/Tagessoll des jeweiligen Tages/)).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Urlaub'), { target: { value: 'overtime' } });
    expect(screen.getByText(/^Stunden/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Halber Tag/)).toBeNull();
  });
});
