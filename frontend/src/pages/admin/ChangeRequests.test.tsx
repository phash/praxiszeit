import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AdminChangeRequests from './ChangeRequests';

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => toast }));

const pendingCr = {
  id: 'cr1',
  user_id: 'u1',
  user_first_name: 'Anna',
  user_last_name: 'Meier',
  request_type: 'create',
  status: 'pending',
  entry_kind: 'time_entry',
  proposed_date: '2026-06-07',
  proposed_start_time: '09:00:00',
  proposed_end_time: '13:00:00',
  proposed_break_minutes: 0,
  reason: 'Dienst nachgetragen',
  created_at: '2026-06-08T08:00:00Z',
};

function mockApi(requests: unknown[]) {
  getMock.mockImplementation((url: string) =>
    url.startsWith('/admin/change-requests')
      ? Promise.resolve({ data: requests })
      : Promise.resolve({ data: [] }),
  );
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
});

describe('<AdminChangeRequests /> §10-Ausnahmegrund (#485)', () => {
  it('zeigt den mitgebrachten Ausnahmegrund beim beantragten Eintrag', async () => {
    mockApi([{ ...pendingCr, proposed_sunday_exception_reason: 'KV-Notdienst' }]);
    render(<AdminChangeRequests />);
    expect(await screen.findByText('§10-Ausnahmegrund: KV-Notdienst')).toBeInTheDocument();
  });

  it('zeigt keine §10-Zeile ohne Grund', async () => {
    mockApi([pendingCr]);
    render(<AdminChangeRequests />);
    await screen.findByText('Dienst nachgetragen');
    expect(screen.queryByText(/§10-Ausnahmegrund/)).toBeNull();
  });
});

describe('<AdminChangeRequests /> Sammel-Genehmigung (#486)', () => {
  it('zeigt die Warnungen jedes genehmigten Antrags mit dem Namen der Person', async () => {
    mockApi([pendingCr]);
    postMock.mockResolvedValue({
      data: {
        succeeded: 1, failed: 0,
        items: [{
          request_id: 'cr1', status: 'approved',
          warnings: ['WORK_WINDOW_CLAMPED: Die eingetragene Zeit wurde gekappt (Beginn 07:00 → 07:45).'],
        }],
      },
    });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByLabelText('Antrag von Anna Meier auswählen'));
    fireEvent.click(screen.getByText(/1 genehmigen/));

    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(
      expect.stringMatching(/^Anna Meier: .*Beginn 07:00 → 07:45/),
      undefined,
    ));
    // Der alte Pauschalhinweis "zeigt keine ArbZG-Warnungen" stimmt nicht mehr.
    expect(toast.info).not.toHaveBeenCalled();
  });
});

describe('<AdminChangeRequests /> Sammel-Genehmigung mit Anrechnungsanträgen (Gesamtreview PR2, Fund 4)', () => {
  const creditPending = {
    ...pendingCr, id: 'cr9', request_type: 'update', time_entry_id: 'te9',
    request_credit_override: true, entry_not_credited_minutes: 240,
  };

  it('nennt die Anträge, die anerkannt würden, und fragt vorher nach', async () => {
    mockApi([pendingCr, creditPending]);
    postMock.mockResolvedValue({ data: { succeeded: 2, failed: 0, items: [] } });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByText('Alle 2 auswählen'));
    fireEvent.click(screen.getByRole('button', { name: '2 genehmigen, davon 1 mit Anerkennen' }));
    expect(await screen.findByText(/dauerhaft an/)).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Alle genehmigen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/admin/change-requests/bulk-review', {
      request_ids: ['cr1', 'cr9'], action: 'approve', rejection_reason: undefined,
    }));
  });

  it('Kontrolltest: ohne Anrechnungsantrag ohne Rückfrage', async () => {
    mockApi([pendingCr]);
    postMock.mockResolvedValue({ data: { succeeded: 1, failed: 0, items: [] } });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByLabelText('Antrag von Anna Meier auswählen'));
    fireEvent.click(screen.getByRole('button', { name: '1 genehmigen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
  });
});

describe('<AdminChangeRequests /> Anrechnung beantragen (Spec P21, P3)', () => {
  const creditCr = {
    ...pendingCr, id: 'cr2', request_type: 'update', time_entry_id: 'te1',
    original_date: '2026-06-01', original_start_time: '07:45:00', original_end_time: '18:15:00',
    original_break_minutes: 0, proposed_date: '2026-06-01', proposed_start_time: '07:00:00',
    proposed_end_time: '19:00:00', request_credit_override: true, original_uncredited_minutes: 150,
    entry_credit_override: false, entry_not_credited_minutes: 240,
  };

  it('kennzeichnet den Antrag und genehmigt mit Anerkennen (Antragswert)', async () => {
    mockApi([creditCr]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    expect(await screen.findByText('Anrechnung beantragt')).toBeInTheDocument();
    expect(screen.getByText('Nicht angerechnet (Lücke): 2:30 h')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Genehmigen und anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve' }));
  });

  it('erlaubt, ohne Anerkennen zu genehmigen', async () => {
    mockApi([creditCr]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ohne Anerkennen genehmigen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve', grant_credit_override: false }));
  });

  it('bietet „Genehmigen und anerkennen" auch für gewöhnliche Änderungen mit nicht angerechneter Zeit', async () => {
    mockApi([{ ...creditCr, request_credit_override: false }]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    expect(await screen.findByRole('button', { name: 'Genehmigen' })).toBeInTheDocument();
    expect(screen.queryByText('Anrechnung beantragt')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Genehmigen und anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve', grant_credit_override: true }));
  });

  it('Kontrolltest: „Genehmigen" sendet bei gewöhnlichen Anträgen nur die Aktion', async () => {
    mockApi([{ ...creditCr, request_credit_override: false }]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByRole('button', { name: 'Genehmigen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve' }));
  });

  it('ohne nicht angerechnete Zeit gibt es kein „Genehmigen und anerkennen"', async () => {
    mockApi([{ ...creditCr, request_credit_override: false, entry_not_credited_minutes: 0, original_uncredited_minutes: 0 }]);
    render(<AdminChangeRequests />);
    await screen.findByRole('button', { name: 'Genehmigen' });
    expect(screen.queryByRole('button', { name: 'Genehmigen und anerkennen' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Nicht angerechnet \(Lücke\)/)).not.toBeInTheDocument();
  });

  // P18: der Server lehnt Anerkennen ab, solange der Antrag zu einem
  // automatisch geschlossenen Eintrag kein tatsächliches Ende mitbringt
  // (credit_override_service.lacks_actual_end) — die Prüfung bietet es dann
  // nicht an, statt mit 400 zu scheitern.
  it('automatisch geschlossener Zieleintrag ohne tatsächliches Ende: kein „Genehmigen und anerkennen"', async () => {
    mockApi([{
      ...creditCr, request_credit_override: false, entry_auto_closed: true,
      original_start_time: '08:00:00', proposed_start_time: '08:00:00', proposed_end_time: '18:15:00',
    }]);
    render(<AdminChangeRequests />);
    await screen.findByRole('button', { name: 'Genehmigen' });
    expect(screen.queryByRole('button', { name: 'Genehmigen und anerkennen' })).not.toBeInTheDocument();
  });

  it('automatisch geschlossener Zieleintrag mit tatsächlichem Ende: „Genehmigen und anerkennen" bleibt', async () => {
    mockApi([{
      ...creditCr, request_credit_override: false, entry_auto_closed: true,
      original_start_time: '08:00:00', proposed_start_time: '08:00:00', proposed_end_time: '17:30:00',
    }]);
    render(<AdminChangeRequests />);
    expect(await screen.findByRole('button', { name: 'Genehmigen und anerkennen' })).toBeInTheDocument();
  });

  // Gesamtreview PR2 (Fund 2): „Genehmigen und anerkennen" rechnet die
  // vorgeschlagenen Zeiten dauerhaft an (P11) — die Prüfung zeigt deshalb die
  // Stempel des Eintrags und hebt Abweichungen hervor.
  describe('Stempel des Eintrags (Fund 2)', () => {
    const stamped = { ...creditCr, entry_raw_start_time: '07:00:00', entry_raw_end_time: '19:00:00' };

    it('nennt gestempelte Spanne und die aktuell nicht angerechnete Zeit', async () => {
      mockApi([stamped]);
      render(<AdminChangeRequests />);
      expect(await screen.findByText('gestempelt 07:00–19:00 · nicht angerechnet aktuell 4:00 h')).toBeInTheDocument();
      expect(screen.queryByText(/weicht von den Stempeln ab/)).not.toBeInTheDocument();
    });

    it('hebt vorgeschlagene Zeiten hervor, die nicht den Stempeln entsprechen', async () => {
      mockApi([{ ...stamped, proposed_start_time: '06:00:00', proposed_end_time: '20:00:00' }]);
      render(<AdminChangeRequests />);
      const hint = await screen.findByText('Zeiten weichen von den Stempeln ab (gestempelt 07:00–19:00)');
      expect(hint.className).toMatch(/text-red-700/);
    });

    it('nennt die nicht angerechnete Zeit auch, wenn nur die Hülle kappt (Lücke 0)', async () => {
      mockApi([{
        ...stamped, original_uncredited_minutes: 0, entry_not_credited_minutes: 45,
        original_start_time: '07:45:00', original_end_time: '16:00:00',
        entry_raw_end_time: '16:00:00', proposed_end_time: '16:00:00',
      }]);
      render(<AdminChangeRequests />);
      expect(await screen.findByText('gestempelt 07:00–16:00 · nicht angerechnet aktuell 0:45 h')).toBeInTheDocument();
      expect(screen.queryByText(/Nicht angerechnet \(Lücke\)/)).not.toBeInTheDocument();
    });

    it('automatisch geschlossen: kein Stempel-Ende, verglichen wird nur der Beginn (P18)', async () => {
      mockApi([{
        ...stamped, entry_auto_closed: true, entry_raw_start_time: '08:00:00', entry_raw_end_time: null,
        entry_not_credited_minutes: 150, proposed_start_time: '08:00:00', proposed_end_time: '17:30:00',
      }]);
      render(<AdminChangeRequests />);
      expect(await screen.findByText(
        'gestempelt ab 08:00, nicht ausgestempelt (automatisch geschlossen) · nicht angerechnet aktuell 2:30 h',
      )).toBeInTheDocument();
      expect(screen.queryByText(/weicht|weichen/)).not.toBeInTheDocument();
    });

    it('nicht an erledigten Anträgen (der Eintrag hat sich seither geändert)', async () => {
      mockApi([{ ...stamped, status: 'approved' }]);
      render(<AdminChangeRequests />);
      await screen.findByText('Anrechnung beantragt');
      expect(screen.queryByText(/^gestempelt /)).not.toBeInTheDocument();
    });
  });

  it('zeigt bei einem anerkannten Zieleintrag den Hinweis aus P3', async () => {
    mockApi([{ ...creditCr, request_credit_override: false, entry_credit_override: true, entry_not_credited_minutes: 0 }]);
    render(<AdminChangeRequests />);
    expect(await screen.findByText('Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Genehmigen und anerkennen' })).not.toBeInTheDocument();
  });

  // P3 meint die Antragsprüfung: der Hinweis hängt am AKTUELLEN Zustand des
  // Eintrags (entry_credit_override) und wäre an erledigten Anträgen eine
  // Zusage für Zeiten, die längst übernommen bzw. nie übernommen wurden.
  it.each(['approved', 'rejected'])('zeigt den Hinweis aus P3 nicht an erledigten Anträgen (%s)', async (status) => {
    mockApi([{ ...creditCr, status, entry_credit_override: true, entry_not_credited_minutes: 0 }]);
    render(<AdminChangeRequests />);
    expect(await screen.findByText('Anrechnung beantragt')).toBeInTheDocument();
    expect(screen.queryByText('Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.')).not.toBeInTheDocument();
  });
});
