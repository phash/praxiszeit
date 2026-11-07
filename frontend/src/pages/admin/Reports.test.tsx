import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import Reports from './Reports';

// Spec 2026-10-08, 8.1 / P22: neben dem angerechneten 24-Wochen-Durchschnitt
// steht die Anwesenheit laut Stempel — die senkt keine spätere Neuberechnung.

const getMock = vi.fn();
vi.mock('../../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));
vi.mock('../../utils/downloadBlob', () => ({ downloadBlob: vi.fn() }));
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
    expect(within(table).getByText('Anwesenheit laut Stempel (Ø / Werktag)')).toBeInTheDocument();
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
    expect(within(table).getByText('keine Werktage im Zeitraum')).toBeInTheDocument();
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

// Gesamtreview 1.20 (Fund 22): die Karte nennt den ausgewerteten Zeitraum und
// die Zahl der nicht konformen Personen (wie die Nachbarkarten „Jahr: …"),
// erklärt eine leere Liste und fragt ohne Stichtag nicht an.
describe('<Reports /> 24-Wochen-Durchschnitt: Zeitraum und Leerzustand (Fund 22)', () => {
  const employee = (over: Record<string, unknown> = {}) => ({
    user_id: 'u1', first_name: 'Anna', last_name: 'Meier', total_hours: 1000,
    scheduled_work_days: 110, average_daily_hours: 9.09, days_over_8h: 40, compliant: false,
    presence_hours: 1000, presence_average: 9.09, presence_weeks: [],
    ...over,
  });

  it('zeigt den Zeitraum der Antwort und die Zahl der nicht konformen Personen', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-10-29', window_end: '2026-04-15', non_compliant_count: 1,
        employees: [employee()],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(screen.getByText('29.10.2025 – 15.04.2026')).toBeInTheDocument();
    expect(screen.getByText('⚠ 1 Mitarbeitende nicht konform')).toBeInTheDocument();
  });

  it('ohne nicht konforme Personen kein Warnhinweis', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-10-29', window_end: '2026-04-15', non_compliant_count: 0,
        employees: [employee({ compliant: true, average_daily_hours: 7.5 })],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    await screen.findByText('29.10.2025 – 15.04.2026');
    expect(screen.queryByText(/nicht konform/)).not.toBeInTheDocument();
  });

  it('erklärt eine leere Liste statt eines leeren Tabellenkopfs', async () => {
    getMock.mockResolvedValue({
      data: { window_start: '2025-10-29', window_end: '2026-04-15', non_compliant_count: 0, employees: [] },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    expect(await screen.findByText(/Keine Mitarbeitenden zu prüfen/)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: '24-Wochen-Durchschnitt' })).not.toBeInTheDocument();
    expect(screen.getByText('29.10.2025 – 15.04.2026')).toBeInTheDocument();
  });

  it('sperrt „Prüfen" ohne Stichtag', () => {
    render(<Reports />);
    fireEvent.change(screen.getByLabelText('Stichtag'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' })).toBeDisabled();
  });

  it('ein neuer Stichtag verwirft das alte Ergebnis (es gehörte zu einem anderen Zeitraum)', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-10-29', window_end: '2026-04-15', non_compliant_count: 1,
        employees: [employee()],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    fireEvent.change(screen.getByLabelText('Stichtag'), { target: { value: '2026-06-30' } });
    expect(screen.queryByRole('table', { name: '24-Wochen-Durchschnitt' })).not.toBeInTheDocument();
    expect(screen.queryByText('29.10.2025 – 15.04.2026')).not.toBeInTheDocument();
  });
});

// Audit 2026-11-07 (#539): Ersatzruhetag, Nachtarbeit je Monat, §3/§4-Auswertung,
// ausgeblendete Mitarbeitende.
function card(heading: string): HTMLElement {
  return screen.getByRole('heading', { name: heading }).closest('.bg-white') as HTMLElement;
}

describe('<Reports /> ArbZG-Auswertungen (Audit 2026-11-07)', () => {
  it('Ersatzruhetage: Verstöße mit Datum, laufende Fristen getrennt (A1-01)', async () => {
    getMock.mockResolvedValue({
      data: {
        year: 2026, total_violations: 1, total_open: 1, non_compliant_count: 1, hidden_with_data_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Meier', sunday_holiday_days_worked: 3,
          violations: [{ date: '2026-10-04', type: 'sunday', window_weeks: 2, deadline: '2026-10-18' }],
          violation_count: 1,
          open: [{ date: '2026-11-01', type: 'sunday', window_weeks: 2, deadline: '2026-11-15' }],
          open_count: 1, compliant: false,
        }],
      },
    });
    render(<Reports />);
    const c = card('Ersatzruhetage §11 ArbZG');
    expect(within(c).getByText(/sonst gearbeitet hätte/)).toBeInTheDocument();
    fireEvent.click(within(c).getByRole('button', { name: /Prüfen/ }));
    expect(await within(c).findByText('04.10.2026 (So)')).toBeInTheDocument();
    expect(within(c).getByText('01.11.2026 bis 15.11.2026')).toBeInTheDocument();
    expect(within(c).getByText('Frist läuft')).toBeInTheDocument();
  });

  it('Nachtarbeit: Monatsdurchschnitt und fehlendes Kennzeichen (A1-14)', async () => {
    getMock.mockResolvedValue({
      data: {
        year: 2026, nachtarbeitnehmer_threshold: 48, nachtarbeitnehmer_count: 1, hidden_with_data_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Nina', last_name: 'Nacht', night_work_days: 50,
          is_nachtarbeitnehmer: true, nachtarbeitnehmer_threshold: 48, by_month: [],
          flag_missing: true, monthly_violation_count: 1,
          monthly: [{ month: 9, workdays: 6, total_hours: 50, average_daily_hours: 8.33,
            presence_hours: 50, presence_average: 8.33, compliant: false }],
        }],
      },
    });
    render(<Reports />);
    const c = card('Nachtarbeit §6 ArbZG');
    fireEvent.click(within(c).getByRole('button', { name: /Auswerten/ }));
    const table = await within(c).findByRole('table', { name: 'Monatsdurchschnitt Nachtarbeitnehmer' });
    expect(within(table).getByText('September')).toBeInTheDocument();
    expect(within(table).getAllByText('8:20')).toHaveLength(2);
    expect(within(table).getByText('✗ Verstoß')).toBeInTheDocument();
    expect(within(c).getByText(/Kennzeichen „Nachtarbeitnehmer“ beim Benutzer noch nicht gesetzt/)).toBeInTheDocument();
  });

  it('§3/§4: Tage über 10 h, Wochen über 48 h und Pausenausnahmen mit Begründung (A1-08)', async () => {
    getMock.mockResolvedValue({
      data: {
        year: 2026, month: 10, total_days_over_10h: 1, total_weeks_over_48h: 1, total_break_exceptions: 1,
        hidden_with_data_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Meier',
          days_over_10h: [{ date: '2026-10-05', presence_hours: 12, credited_hours: 7.5, auto_closed: false }],
          weeks_over_48h: [{ iso_week: '2026-W41', presence_hours: 56 }],
          break_exceptions: [{ date: '2026-10-13', start_time: '07:00', end_time: '14:00', break_minutes: 0,
            reason: 'Notfall, keine Pause möglich' }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.change(screen.getByLabelText('Monat (optional)', { selector: '#limits-month' }), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Höchstarbeitszeit und Pausenausnahmen prüfen' }));
    const c = card('Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG');
    fireEvent.click(await within(c).findByText(/Anna Meier – 1 Tag\(e\) > 10 h/));
    expect(within(c).getByText('12:00 h')).toBeInTheDocument();
    expect(within(c).getByText('7:30 h')).toBeInTheDocument();
    expect(within(c).getByText(/KW 41\/2026: 56:00 h/)).toBeInTheDocument();
    expect(within(c).getByText('Notfall, keine Pause möglich')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/admin/reports/arbzg-limits?year=' + new Date().getFullYear() + '&month=10');
  });

  it('ausgeblendete Mitarbeitende: Hinweis und Schalter für die Auswertungen (A2-6)', async () => {
    getMock.mockResolvedValue({
      data: { window_start: '2025-10-29', window_end: '2026-04-15', non_compliant_count: 0, employees: [],
        hidden_with_data_count: 2 },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    expect(await screen.findByText(/2 ausgeblendete Mitarbeitende mit Einträgen/)).toBeInTheDocument();
    fireEvent.click(document.getElementById('report-hidden') as HTMLElement);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    expect(getMock).toHaveBeenLastCalledWith(expect.stringMatching(/24-week-average\?end_date=.*&include_hidden=true$/));
  });

  it('Exporte: Ausgeblendete nur auf Wunsch (A2-6)', async () => {
    getMock.mockResolvedValue({ data: new Blob(['x']) });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: 'Excel (.xlsx)' }));
    expect(getMock).toHaveBeenLastCalledWith(expect.not.stringContaining('include_hidden'), expect.anything());
    fireEvent.click(document.getElementById('export-hidden-month') as HTMLElement);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Excel (.xlsx)' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Excel (.xlsx)' }));
    expect(getMock).toHaveBeenLastCalledWith(expect.stringContaining('&include_hidden=true'), expect.anything());
  });
});
