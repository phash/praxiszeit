import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AutoClosedEntriesCard from './AutoClosedEntriesCard';

const getMock = vi.fn();
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));

beforeEach(() => getMock.mockReset());

describe('<AutoClosedEntriesCard /> (#540 A1-04)', () => {
  it('nennt jeden Fall mit den §3/§4-Befunden', async () => {
    getMock.mockResolvedValue({
      data: [{
        id: 'e1', user_id: 'u1', user_name: 'Maria Muster', date: '2026-11-05', start_time: '08:00:00',
        end_time: '23:59:00', net_hours: 15.98, pending_change_request: true,
        findings: ['Tagesarbeitszeit 15:59 h über der Höchstgrenze von 10 h (§ 3 ArbZG)', 'Pflicht-Pause fehlt (§ 4 ArbZG)'],
      }],
    });
    render(<AutoClosedEntriesCard />);
    expect(await screen.findByText(/Ende fehlt \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('Maria Muster')).toBeInTheDocument();
    expect(screen.getByText(/05\.11\.2026 ab 08:00, angerechnet bis 23:59/)).toBeInTheDocument();
    expect(screen.getByText(/§ 3 ArbZG.*§ 4 ArbZG/)).toBeInTheDocument();
    expect(screen.getByText('Antrag gestellt')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/admin/time-entries/auto-closed');
  });

  it('erscheint ohne Fälle nicht', async () => {
    getMock.mockResolvedValue({ data: [] });
    const { container } = render(<AutoClosedEntriesCard />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });
});
