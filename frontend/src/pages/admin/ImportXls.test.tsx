import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ImportXls from './ImportXls';

// Spec 2026-10-08, 7.4: die Vorschau zeigt das Netto des Servers (nach nicht
// angerechneter Lücke und Auto-Pause) statt es im Browser nachzurechnen.
// P19: „nicht angerechnet" ist Lücke + Hülle (not_credited_minutes vom Server),
// nie uncredited_minutes allein.

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
});

async function analyze(entry: Record<string, unknown>, summary: Record<string, unknown> = {}) {
  getMock.mockResolvedValue({
    data: [{ id: 'u1', first_name: 'Jane', last_name: 'Doe', username: 'jd', is_active: true }],
  });
  postMock.mockResolvedValue({
    data: {
      total: 1, conflicts: 0, arbzg_warnings: 0,
      ...summary,
      entries: [{
        date: '2026-06-01', break_minutes: 0, note: null, has_conflict: false,
        arbzg_warnings: [], raw_start_time: null, raw_end_time: null,
        ...entry,
      }],
    },
  });
  const { container } = render(<ImportXls />);
  const select = screen.getByRole('combobox');
  fireEvent.focus(select);
  await screen.findByRole('option', { name: 'Jane Doe (jd)' });
  fireEvent.change(select, { target: { value: 'u1' } });
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['x'], 'zeit.xls')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Datei analysieren →' }));
}

describe('<ImportXls /> Vorschau-Netto (Spec 7.4)', () => {
  it('zeigt net_hours vom Server und die nicht angerechnete Lücke', async () => {
    await analyze({
      start_time: '08:00:00', end_time: '18:00:00',
      uncredited_minutes: 150, not_credited_minutes: 150, net_hours: 7.5,
    });
    expect(await screen.findByText('7:30')).toBeInTheDocument();
    expect(screen.getByText('2:30 h nicht angerechnet')).toBeInTheDocument();
  });

  it('weist auch die von der Hülle gekappte Anwesenheit aus (P19)', async () => {
    // Altfenster 08:00–17:00, gestempelt 07:00–17:00: angerechnet ab 07:45,
    // keine Lücke — 0:45 h nicht angerechnet, obwohl uncredited_minutes 0 ist.
    await analyze({
      start_time: '07:45:00', end_time: '17:00:00', raw_start_time: '07:00:00', break_minutes: 45,
      uncredited_minutes: 0, not_credited_minutes: 45, net_hours: 8.5,
    });
    expect(await screen.findByText('8:30')).toBeInTheDocument();
    expect(screen.getByText('0:45 h nicht angerechnet')).toBeInTheDocument();
  });

  it('zeigt ohne Kappung keine Zeile „nicht angerechnet"', async () => {
    await analyze({
      start_time: '08:00:00', end_time: '16:30:00', break_minutes: 30,
      uncredited_minutes: 0, not_credited_minutes: 0, net_hours: 8,
    });
    expect(await screen.findByText('8:00')).toBeInTheDocument();
    expect(screen.queryByText(/nicht angerechnet/)).not.toBeInTheDocument();
  });
});

// Review Task 12: eine Konfliktzeile (Überschreib-Import) darf ihre Hinweise nicht
// verstecken — der Hinweis aus P3 („Eintrag ist anerkannt …") entsteht NUR auf
// Konfliktzeilen, und die Zusammenfassung „N Hinweise" zählt sie mit.
describe('<ImportXls /> Hinweise auf Konfliktzeilen (Spec P3, 8.3)', () => {
  const P3 = 'Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.';
  const PRESENCE = '§3 ArbZG: Laut Stempel 12:00 h anwesend – mehr als 10 Stunden.';

  it('zeigt neben „Konflikt" die Hinweise der Zeile', async () => {
    await analyze(
      {
        start_time: '06:00:00', end_time: '18:00:00', has_conflict: true,
        arbzg_warnings: [PRESENCE, P3], net_hours: 9,
      },
      { conflicts: 1, arbzg_warnings: 2 },
    );
    expect(await screen.findByText('Konflikt')).toBeInTheDocument();
    const hint = screen.getByTitle(/Laut Stempel 12:00 h anwesend/);
    expect(hint).toHaveTextContent('Hinweis');
    expect(hint).toHaveAttribute('title', `${PRESENCE}\n${P3}`);
  });

  it('zeigt auf einer Konfliktzeile ohne Hinweise kein Hinweis-Kennzeichen', async () => {
    await analyze(
      { start_time: '08:00:00', end_time: '16:30:00', has_conflict: true, net_hours: 8 },
      { conflicts: 1 },
    );
    expect(await screen.findByText('Konflikt')).toBeInTheDocument();
    expect(screen.queryByText('Hinweis')).not.toBeInTheDocument();
  });
});
