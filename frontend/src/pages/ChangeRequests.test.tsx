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

// Review 2026-11-11 (antrag-10/11/20)
describe('<ChangeRequests /> Review 2026-11-11', () => {
  const absenceCr = {
    id: 'cr2', request_type: 'create', status: 'pending', entry_kind: 'absence',
    proposed_date: '2026-06-01', proposed_absence_type: 'training',
    proposed_start_time: '09:00:00', proposed_end_time: '12:00:00',
    reason: 'Fortbildung', created_at: '2026-06-02T08:00:00Z',
  };

  it('zeigt bei fehlenden Stunden keine leere „Stunden: h“-Zeile (antrag-10)', async () => {
    mockRequests([absenceCr]);
    render(<ChangeRequests />);
    await screen.findByText('Fortbildung');
    expect(screen.queryByText(/Stunden:/)).toBeNull();
  });

  it('zeigt Abwesenheitsstunden als H:MM (antrag-10)', async () => {
    mockRequests([{ ...absenceCr, proposed_absence_hours: 7.6 }]);
    render(<ChangeRequests />);
    expect(await screen.findByText('7:36 h')).toBeInTheDocument();
  });

  it('stürzt ohne Datum nicht ab (antrag-10)', async () => {
    mockRequests([{ ...absenceCr, proposed_date: undefined }]);
    render(<ChangeRequests />);
    expect(await screen.findByText('Fortbildung')).toBeInTheDocument();
  });

  it('zeigt bei einem Ladefehler eine Fehlermeldung statt der leeren Liste (antrag-11)', async () => {
    getMock.mockRejectedValue(new Error('offline'));
    render(<ChangeRequests />);
    expect(await screen.findByRole('alert')).toHaveTextContent('konnten nicht geladen werden');
    expect(screen.queryByText('Keine Änderungsanträge')).toBeNull();
    expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeInTheDocument();
  });

  it('siezt im Leerzustand (antrag-20)', async () => {
    mockRequests([]);
    render(<ChangeRequests />);
    expect(await screen.findByText(/stellen Sie über den Button/)).toBeInTheDocument();
  });
});
