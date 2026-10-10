import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChangeRequests from './ChangeRequests';

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    delete: vi.fn(),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

// Gesamtreview PR2 (Fund 5): „Meine Anträge" kennzeichnet einen Antrag
// „Anrechnung beantragen" wie die Admin-Prüfung — und nach der Genehmigung,
// ob die Anrechnung gewährt wurde (Genehmigt ≠ anerkannt, P21).
const creditCr = {
  id: 'cr1', request_type: 'update', status: 'pending', entry_kind: 'time_entry',
  time_entry_id: 'te1', proposed_date: '2026-06-01', proposed_start_time: '07:00:00',
  proposed_end_time: '19:00:00', proposed_break_minutes: 0, original_date: '2026-06-01',
  original_start_time: '07:45:00', original_end_time: '18:15:00', original_break_minutes: 0,
  reason: 'Patientin in der Mittagspause versorgt', created_at: '2026-06-02T08:00:00Z',
  request_credit_override: true, entry_credit_override: false,
};

function mockRequests(requests: unknown[]) {
  getMock.mockResolvedValue({ data: requests });
}

beforeEach(() => {
  getMock.mockReset();
});

describe('<ChangeRequests /> Anrechnung beantragt (Fund 5)', () => {
  it('kennzeichnet den offenen Antrag', async () => {
    mockRequests([creditCr]);
    render(<ChangeRequests />);
    expect(await screen.findByText('Anrechnung beantragt')).toBeInTheDocument();
    expect(screen.queryByText('anerkannt')).not.toBeInTheDocument();
  });

  it('genehmigt und anerkannt', async () => {
    mockRequests([{ ...creditCr, status: 'approved', entry_credit_override: true }]);
    render(<ChangeRequests />);
    expect(await screen.findByText('Anrechnung beantragt')).toBeInTheDocument();
    expect(screen.getByText('anerkannt')).toBeInTheDocument();
  });

  it('genehmigt ohne Anerkennen — die Zeit bleibt gekappt', async () => {
    mockRequests([{ ...creditCr, status: 'approved' }]);
    render(<ChangeRequests />);
    expect(await screen.findByText('ohne Anerkennen genehmigt')).toBeInTheDocument();
  });

  it('ohne Zieleintrag (inzwischen gelöscht) kein Urteil über die Anrechnung', async () => {
    mockRequests([{ ...creditCr, status: 'approved', time_entry_id: null }]);
    render(<ChangeRequests />);
    await screen.findByText('Anrechnung beantragt');
    expect(screen.queryByText('ohne Anerkennen genehmigt')).not.toBeInTheDocument();
    expect(screen.queryByText('anerkannt')).not.toBeInTheDocument();
  });

  it('Kontrolltest: gewöhnliche Änderung ohne Kennzeichen', async () => {
    mockRequests([{ ...creditCr, request_credit_override: false, status: 'approved' }]);
    render(<ChangeRequests />);
    await screen.findByText('Patientin in der Mittagspause versorgt');
    expect(screen.queryByText('Anrechnung beantragt')).not.toBeInTheDocument();
    expect(screen.queryByText('ohne Anerkennen genehmigt')).not.toBeInTheDocument();
  });
});
