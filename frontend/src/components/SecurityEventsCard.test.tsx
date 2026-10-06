import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import SecurityEventsCard from './SecurityEventsCard';

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...args: unknown[]) => getMock(...args) },
}));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));

beforeEach(() => {
  getMock.mockReset();
  toast.error.mockReset();
});

describe('<SecurityEventsCard /> (#489)', () => {
  it('zeigt Vorgang, betroffenes Konto und handelnde Person', async () => {
    getMock.mockResolvedValue({
      data: [{
        id: 'e1', created_at: '2026-10-06T15:12:00Z', event: 'user_deactivated',
        subject_user_id: 'u1', subject_name: 'Anna Meier',
        actor: 'user:u2', actor_name: 'Bernd Admin', detail: 'Konto deaktiviert (Rolle Admin)',
      }],
    });
    render(<SecurityEventsCard />);
    expect((await screen.findAllByText('Konto deaktiviert')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Anna Meier').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bernd Admin').length).toBeGreaterThan(0);
    expect(getMock).toHaveBeenCalledWith('/admin/security-events');
  });

  it('beschriftet Kommandozeilen-Vorgaenge verstaendlich', async () => {
    getMock.mockResolvedValue({
      data: [{
        id: 'e2', created_at: '2026-10-06T15:12:00Z', event: 'user_reactivated_cli',
        subject_user_id: 'u1', subject_name: 'Anna Meier',
        actor: 'cli:root@srv', actor_name: 'Kommandozeile (root@srv)', detail: null,
      }],
    });
    render(<SecurityEventsCard />);
    expect((await screen.findAllByText('Konto per Kommandozeile reaktiviert')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Kommandozeile (root@srv)').length).toBeGreaterThan(0);
  });

  it('sagt es, wenn noch nichts protokolliert ist', async () => {
    getMock.mockResolvedValue({ data: [] });
    render(<SecurityEventsCard />);
    expect(await screen.findByText('Noch keine Konto-Vorgänge protokolliert.')).toBeInTheDocument();
  });
});
