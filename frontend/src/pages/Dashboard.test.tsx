import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from './Dashboard';

// Backlog item (Audit 2026-07-31): vacation-day counts were rendered with
// `.toFixed(1)` (English decimal point, "26.5 Tage") right next to hour
// values formatted with the German comma elsewhere in the app. Fix reuses
// the existing `deHoursExact` helper (utils/formatters.ts) instead of
// inventing a second formatting rule.

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  // authStore.ts pulls these named exports in transitively — never invoked
  // in this test, but the mock module must expose them so the import
  // itself doesn't blow up (pattern from Users.test.tsx).
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

const VACATION_ACCOUNT = {
  year: 2026,
  budget_hours: 0,
  budget_days: 27.5,
  used_hours: 0,
  used_days: 3.5,
  remaining_hours: 0,
  remaining_days: 26.5,
};

function mockDashboardEndpoints() {
  getMock.mockImplementation((url: string) => {
    if (url === '/dashboard') {
      return Promise.resolve({ data: { year: 2026, month: 7, target_hours: 0, actual_hours: 0, balance: 0 } });
    }
    if (url === '/dashboard/overtime') {
      return Promise.resolve({ data: { current_balance: 0, history: [] } });
    }
    if (url === '/dashboard/vacation') {
      return Promise.resolve({ data: VACATION_ACCOUNT });
    }
    if (url === '/absences/team/upcoming') {
      return Promise.resolve({ data: [] });
    }
    if (url === '/absences') {
      return Promise.resolve({ data: [] });
    }
    if (url === '/absences/next-vacation') {
      return Promise.resolve({ data: null });
    }
    if (url === '/dashboard/ytd-overtime') {
      return Promise.resolve({ data: { year: 2026, target_hours: 0, actual_hours: 0, overtime: 0, carryover_hours: 0 } });
    }
    if (url === '/dashboard/missing-bookings') {
      return Promise.resolve({ data: { entries: [] } });
    }
    if (url === '/time-entries/clock-status') {
      return Promise.resolve({ data: { is_clocked_in: false } });
    }
    if (url.startsWith('/time-entries')) {
      return Promise.resolve({ data: [] });
    }
    return Promise.resolve({ data: null });
  });
}

beforeEach(() => {
  getMock.mockReset();
  mockDashboardEndpoints();
  // Deliberately no useAuthStore.setState() here: the persist middleware's
  // setItem() crashes in this sandbox's Node/jsdom combination whenever
  // *anything* writes to the store (pre-existing, unrelated environment gap —
  // see the ~20 known authStore/ImpersonationBanner failures). Dashboard only
  // READS the store (never writes), and its default `user: null` is exactly
  // the state this test wants, so no write is needed.
});

describe('Dashboard vacation-day formatting (Audit 2026-07-31 backlog item)', () => {
  it('renders the vacation account with a German decimal comma, not an English dot', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Dashboard />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('Urlaubskonto')).toBeInTheDocument());

    expect(await screen.findByText('26,5 Tage')).toBeInTheDocument();
    expect(screen.getByText('3,5 Tage')).toBeInTheDocument();
    expect(screen.getByText('27,5 Tage')).toBeInTheDocument();

    // The old `.toFixed(1)` output must be gone.
    expect(screen.queryByText('26.5 Tage')).not.toBeInTheDocument();
    expect(screen.queryByText('3.5 Tage')).not.toBeInTheDocument();
    expect(screen.queryByText('27.5 Tage')).not.toBeInTheDocument();
  });
});
