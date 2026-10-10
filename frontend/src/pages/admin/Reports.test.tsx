import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Reports from './Reports';

// Spec 2026-10-08, 8.1 / P22: neben dem angerechneten 24-Wochen-Durchschnitt
// steht die Anwesenheit laut Stempel — die senkt keine spätere Neuberechnung.

const getMock = vi.fn();
vi.mock('../../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  getMock.mockReset();
});

describe('<Reports /> 24-Wochen-Durchschnitt (Spec 8.1, P22)', () => {
  it('zeigt angerechnete Zeit und Anwesenheit laut Stempel nebeneinander', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-05', non_compliant_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Meier', total_hours: 15.5,
          scheduled_work_days: 2, average_daily_hours: 7.75, days_over_8h: 0, compliant: true,
          presence_hours: 22, presence_average: 11,
          presence_weeks: [{ iso_week: '2026-W23', presence_hours: 22 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('Anwesenheit laut Stempel (Ø / Tag)')).toBeInTheDocument();
    expect(within(table).getByText('7:45')).toBeInTheDocument();
    expect(within(table).getByText('11:00')).toBeInTheDocument();
    expect(within(table).getByText('22:00')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/admin\/reports\/24-week-average\?end_date=\d{4}-\d{2}-\d{2}$/),
    );
    expect(within(table).getByText('Wochen > 48 h laut Stempel')).toBeInTheDocument();
    expect(within(table).getByText('–')).toBeInTheDocument();
  });

  it('nennt Wochen mit mehr als 48 h laut Stempel (Spec 8.1/11.1 „je Woche")', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-12', non_compliant_count: 0,
        employees: [{
          user_id: 'u2', first_name: 'Bea', last_name: 'Kurz', total_hours: 67.5,
          scheduled_work_days: 10, average_daily_hours: 6.75, days_over_8h: 0, compliant: true,
          presence_hours: 90, presence_average: 9,
          presence_weeks: [{ iso_week: '2026-W23', presence_hours: 50 }, { iso_week: '2026-W24', presence_hours: 40 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('1 (2026-W23: 50:00 h)')).toBeInTheDocument();
  });
});
