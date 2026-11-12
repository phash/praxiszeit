import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Reports from './Reports';

// Code-Review 2026-11-11, calc-06/10/11.
const getMock = vi.fn();
const toastError = vi.fn();
vi.mock('../../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));
vi.mock('../../utils/downloadBlob', () => ({ downloadBlob: vi.fn() }));
const toastApi = { error: (...a: unknown[]) => toastError(...a), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => toastApi }));

beforeEach(() => {
  getMock.mockReset();
  toastError.mockReset();
});

const limitsReport = {
  year: 2025, month: null, hidden_with_data_count: 0, employees: [],
  total_days_over_10h: 3, total_weeks_over_48h: 0, total_break_exceptions: 0, total_break_shortfalls: 0,
};

describe('<Reports /> Fehlermeldung der Exporte (calc-11)', () => {
  it('zeigt den Detailtext aus der Blob-Fehlerantwort', async () => {
    const body = new Blob([JSON.stringify({ detail: 'Monat liegt in der Zukunft' })], { type: 'application/json' });
    getMock.mockRejectedValue({ response: { status: 400, data: body } });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: 'Excel (.xlsx)' }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Monat liegt in der Zukunft'));
  });

  it('meldet das Rate-Limit (429) gesondert', async () => {
    getMock.mockRejectedValue({ response: { status: 429, data: new Blob(['{}']) } });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: 'Excel (.xlsx)' }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith(expect.stringMatching(/^Zu viele Versuche/)));
  });
});

describe('<Reports /> Jahresfelder und Ergebnisstand der ArbZG-Auswertungen (calc-10)', () => {
  it('ein geleertes Jahresfeld sperrt „Prüfen“ statt year=NaN zu senden', () => {
    render(<Reports />);
    const input = document.getElementById('limits-year') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');
    expect(screen.getByRole('button', { name: 'Höchstarbeitszeit und Pausenausnahmen prüfen' })).toBeDisabled();
  });

  it('verwirft das Ergebnis, wenn das Jahr geändert wird', async () => {
    getMock.mockResolvedValue({ data: limitsReport });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: 'Höchstarbeitszeit und Pausenausnahmen prüfen' }));
    expect(await screen.findByText(/Tage > 10 h/)).toBeInTheDocument();
    fireEvent.change(document.getElementById('limits-year') as HTMLInputElement, { target: { value: '2024' } });
    expect(screen.queryByText(/Tage > 10 h/)).not.toBeInTheDocument();
  });

  it('verwirft das Ergebnis beim Umschalten von „Ausgeblendete einbeziehen“', async () => {
    getMock.mockResolvedValue({ data: limitsReport });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: 'Höchstarbeitszeit und Pausenausnahmen prüfen' }));
    expect(await screen.findByText(/Tage > 10 h/)).toBeInTheDocument();
    fireEvent.click(document.getElementById('report-hidden') as HTMLElement);
    expect(screen.queryByText(/Tage > 10 h/)).not.toBeInTheDocument();
  });

  it('Ruhezeit: leere oder unzulässige Mindestruhezeit sperrt „Prüfen“ (calc-06)', () => {
    render(<Reports />);
    const section = screen.getByRole('heading', { name: 'Ruhezeitprüfung' }).closest('div')!.parentElement!;
    const min = within(section).getByLabelText('Mindestruhezeit (h)') as HTMLInputElement;
    const btn = within(section).getByRole('button', { name: 'Prüfen' });
    expect(btn).not.toBeDisabled();
    fireEvent.change(min, { target: { value: '' } });
    expect(btn).toBeDisabled();
    fireEvent.change(min, { target: { value: '0' } });
    expect(btn).toBeDisabled();
    fireEvent.change(min, { target: { value: '12' } });
    expect(btn).not.toBeDisabled();
  });
});

describe('<Reports /> Sonntagsauswertung im Teiljahr (calc-05)', () => {
  it('kennzeichnet Teiljahre mit Beschäftigungszeitraum und anteiliger Pflicht', async () => {
    getMock.mockResolvedValue({
      data: {
        year: 2026, total_sundays_in_year: 52, min_free_sundays: 15, non_compliant_count: 1,
        hidden_with_data_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Neu', last_name: 'Eintritt', sundays_worked: 4, free_sundays: 0,
          total_sundays_in_year: 4, partial_year: true, min_free_sundays: 2, compliant: false,
        }],
      },
    });
    render(<Reports />);
    const section = screen.getByRole('heading', { name: /Sonntagsarbeit/ }).closest('div')!.parentElement!;
    fireEvent.click(within(section).getByRole('button', { name: 'Prüfen' }));
    expect(await screen.findByText(/Teiljahr: 4 Sonntage im Beschäftigungszeitraum, Pflicht ≥ 2 frei/)).toBeInTheDocument();
  });
});
