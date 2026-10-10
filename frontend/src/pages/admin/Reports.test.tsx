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
    // Gesamtreview PR2 (Fund 8): „KW 23/2026" wie WeekSelector/Dashboard, nicht ISO „2026-W23";
    // das Fenster kann einen Jahreswechsel enthalten, deshalb mit Jahr.
    expect(within(table).getByText('1 (KW 23/2026: 50:00 h)')).toBeInTheDocument();
    // Acht Spalten: auf Telefonbreite scrollt die Tabelle, nicht die Seite.
    expect(table.parentElement?.className).toMatch(/overflow-x-auto/);
  });

  it('KW ohne führende Null, über den Jahreswechsel mit dem jeweiligen Jahr (Fund 8)', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-12', non_compliant_count: 0,
        employees: [{
          user_id: 'u5', first_name: 'Eva', last_name: 'Wechsel', total_hours: 67.5,
          scheduled_work_days: 10, average_daily_hours: 6.75, days_over_8h: 0, compliant: true,
          presence_hours: 100, presence_average: 9,
          presence_weeks: [{ iso_week: '2025-W52', presence_hours: 49 }, { iso_week: '2026-W05', presence_hours: 51 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('2 (KW 52/2025: 49:00 h, KW 5/2026: 51:00 h)')).toBeInTheDocument();
  });

  it('urteilt ohne Soll-Arbeitstage nicht (z. B. track_hours=False)', async () => {
    // Ohne Soll-Arbeitstag gibt es keinen Nenner: das Backend liefert dann
    // Ø 0 und compliant=true — ein Urteil ohne Grundlage.
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-05', non_compliant_count: 0,
        employees: [{
          user_id: 'u3', first_name: 'Cem', last_name: 'Leitend', total_hours: 100,
          scheduled_work_days: 0, average_daily_hours: 0, days_over_8h: 10, compliant: true,
          presence_hours: 100, presence_average: 0,
          presence_weeks: [{ iso_week: '2026-W23', presence_hours: 50 }, { iso_week: '2026-W24', presence_hours: 50 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('keine Soll-Arbeitstage')).toBeInTheDocument();
    expect(within(table).queryByText('✓ Konform')).not.toBeInTheDocument();
    expect(within(table).queryByText('0:00')).not.toBeInTheDocument();
    expect(within(table).getAllByText('–')).toHaveLength(2);
    // Gesamtwerte und Wochen > 48 h bleiben stehen
    expect(within(table).getAllByText('100:00')).toHaveLength(2);
    expect(within(table).getByText('2 (KW 23/2026: 50:00 h, KW 24/2026: 50:00 h)')).toBeInTheDocument();
  });

  it('hebt Ø laut Stempel über 8 h hervor, auch wenn die angerechnete Zeit konform ist (P22, Pflicht 4)', async () => {
    // Nach einer Neukappung sinkt der angerechnete Ø unter 8 h und der Status wird
    // grün — der Verstoß laut Stempel darf dabei nicht optisch verschwinden.
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-05', non_compliant_count: 0,
        employees: [
          {
            user_id: 'u4', first_name: 'Dora', last_name: 'Lang', total_hours: 790,
            scheduled_work_days: 100, average_daily_hours: 7.9, days_over_8h: 0, compliant: true,
            presence_hours: 860, presence_average: 8.6, presence_weeks: [],
          },
          {
            user_id: 'u5', first_name: 'Emil', last_name: 'Grenze', total_hours: 780,
            scheduled_work_days: 100, average_daily_hours: 7.8, days_over_8h: 0, compliant: true,
            presence_hours: 800, presence_average: 8, presence_weeks: [],
          },
        ],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    const rowOver = within(table).getByText('Dora Lang').closest('tr') as HTMLElement;
    expect(within(rowOver).getByText('8:36')).toHaveClass('text-red-700');
    // Der Status bleibt der angerechnete Hybridwert (Spec 8.1), trägt aber den Zusatz.
    expect(within(rowOver).getByText('✓ Konform')).toBeInTheDocument();
    expect(within(rowOver).getByText('laut Stempel Ø > 8 h')).toBeInTheDocument();
    // Genau 8 h liegt nicht über der Grenze.
    const rowAt = within(table).getByText('Emil Grenze').closest('tr') as HTMLElement;
    expect(within(rowAt).getByText('8:00')).not.toHaveClass('text-red-700');
    expect(within(rowAt).queryByText('laut Stempel Ø > 8 h')).not.toBeInTheDocument();
  });

  it('bindet die gesetzliche Grenze an die tatsächliche Arbeitszeit (Spec 8.3/19)', () => {
    render(<Reports />);
    // Eine Neukappung senkt die angerechnete Zeit — der Hinweis darf nicht nahelegen,
    // dass ein Verstoß damit erledigt ist.
    expect(screen.queryByText(/angerechnete Arbeitszeit im Durchschnitt/)).not.toBeInTheDocument();
    expect(screen.getByText(/die Grenze gilt für die tatsächliche Arbeitszeit/)).toBeInTheDocument();
  });
});
