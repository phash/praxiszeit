import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

/** Code-Review 2026-11-11: ops-08 (Race), ops-09 (Personenfilter), ops-10 (Mobilkarte). */
const h = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../../api/client', () => ({ default: { get: h.get } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('../../components/MonthSelector', () => ({
  default: ({ onChange }: { onChange: (v: string) => void }) => (
    <button onClick={() => onChange('2026-09')}>Vormonat</button>
  ),
}));
vi.mock('../../components/SecurityEventsCard', () => ({ default: () => null }));
vi.mock('../../components/AuditIntegrityCard', () => ({ default: () => null }));

import AuditLog from './AuditLog';

const row = (id: string, extra: Record<string, unknown> = {}) => ({
  id, user_id: 'u1', user_first_name: 'Anna', user_last_name: 'Alt', changed_by: 'a', changed_by_first_name: 'Ad', changed_by_last_name: 'Min',
  action: 'update', source: 'manual', created_at: '2026-10-05T10:00:00Z', ...extra,
});

beforeEach(() => { h.get.mockReset(); });

describe('AuditLog', () => {
  it('ops-09: lädt auch ausgeschiedene/ausgeblendete Personen und trennt sie im Filter', async () => {
    h.get.mockImplementation(async (u?: string) => {
      if (u?.startsWith('/admin/users')) {
        return { data: [
          { id: 'u1', first_name: 'Anna', last_name: 'Alt', is_active: true, is_hidden: false },
          { id: 'u2', first_name: 'Bea', last_name: 'Bald', is_active: false, is_hidden: false },
        ] };
      }
      return { data: [] };
    });
    render(<AuditLog />);
    expect(await screen.findByRole('option', { name: 'Bald, Bea (ausgeschieden)' })).toBeInTheDocument();
    const usersCall = h.get.mock.calls.map(c => c[0] as string).find(u => u.startsWith('/admin/users'))!;
    expect(usersCall).toContain('include_inactive=true');
    expect(usersCall).toContain('include_hidden=true');
  });

  it('ops-08: eine späte Antwort des alten Monats überschreibt die neue Liste nicht', async () => {
    let resolveOld: (v: unknown) => void = () => {};
    h.get.mockImplementation((u?: string) => {
      if (u?.startsWith('/admin/users')) return Promise.resolve({ data: [] });
      if (u?.includes('month=2026-09')) return Promise.resolve({ data: [row('neu', { user_last_name: 'SEPTEMBER' })] });
      return new Promise(r => { resolveOld = r; });
    });
    render(<AuditLog />);
    fireEvent.click(await screen.findByText('Vormonat'));
    await waitFor(() => expect(screen.getAllByText(/SEPTEMBER/).length).toBeGreaterThan(0));
    await act(async () => { resolveOld({ data: [row('alt', { user_last_name: 'OKTOBER' })] }); });
    expect(screen.queryByText(/OKTOBER/)).toBeNull();
  });

  it('ops-10: die Mobilkarte zeigt die Pause (wie die Tabelle)', async () => {
    h.get.mockImplementation(async (u?: string) => (u?.startsWith("/admin/users") ? { data: [] } : {
      data: [row('r1', { old_break_minutes: 30, new_break_minutes: 45, old_date: '2026-10-01', new_date: '2026-10-01' })],
    }));
    const { container } = render(<AuditLog />);
    await waitFor(() => expect(container.querySelector('.lg\\:hidden')).not.toBeNull());
    await waitFor(() => {
      const mobile = container.querySelector('.lg\\:hidden')!;
      expect(mobile.textContent).toMatch(/30/);
      expect(mobile.textContent).toMatch(/45/);
    });
  });
});
