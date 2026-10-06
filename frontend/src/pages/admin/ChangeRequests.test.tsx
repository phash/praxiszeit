import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
