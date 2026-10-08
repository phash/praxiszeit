import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import AdminDashboard from './AdminDashboard';

const getMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(),
    delete: vi.fn(),
  },
  // authStore.ts pulls these named exports in transitively (pattern from Users.test.tsx).
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

function yearlyRow(id: string, first: string, last: string, remaining: number, warn: boolean) {
  return {
    user_id: id, first_name: first, last_name: last,
    vacation_days: 10, remaining_vacation_days: remaining,
    sick_days: 0, training_days: 0, other_days: 0, overtime_comp_days: 0,
    overtime_year: 0, total_days: 10,
    has_year_end_warning: warn,
  };
}

function mockEndpoints(yearly: unknown[]) {
  getMock.mockImplementation((url: string) => {
    if (url.startsWith('/admin/reports/yearly-absences')) return Promise.resolve({ data: yearly });
    if (url.startsWith('/admin/reports/')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: null });
  });
}

beforeEach(() => {
  getMock.mockReset();
  // Nur Date faken (Q4 des laufenden Jahres) — echte Timer für findBy/waitFor.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-15T10:00:00'));
});

afterEach(() => {
  vi.useRealTimers();
});

// #501: Die plakative Jahresend-Warnung listete JEDEN Rest > 0 — Teilzeitkräfte
// mit 0,3 / 0,5 Tagen landeten im Banner, obwohl diese Bruchteile ins Folgejahr
// wandern und dort zu ganzen Tagen zusammengelegt werden. Die Entscheidung trifft
// jetzt der Server (has_year_end_warning, ab 1,0 Tagen — dieselbe Regel wie im
// Mitarbeiter-Dashboard), das Frontend filtert nicht mehr selbst.
describe('AdminDashboard Jahresend-Warnung (#501)', () => {
  it('nennt nur Mitarbeitende, für die der Server warnt (ab 1,0 Tagen)', async () => {
    mockEndpoints([
      yearlyRow('u1', 'Annika', 'Geier', 0.5, false),
      yearlyRow('u2', 'Aura', 'Haiser', 1.0, true),
      yearlyRow('u3', 'Nadja', 'Jacob', 3.5, true),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const heading = await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);
    const banner = heading.closest('div')!;
    expect(within(banner).getByText(/Aura Haiser/)).toBeInTheDocument();
    expect(within(banner).getByText(/Nadja Jacob/)).toBeInTheDocument();
    expect(within(banner).queryByText(/Annika Geier/)).not.toBeInTheDocument();
  });

  it('zeigt keinen Banner, wenn nur Bruchteile offen sind', async () => {
    mockEndpoints([
      yearlyRow('u1', 'Annika', 'Geier', 0.5, false),
      yearlyRow('u4', 'Larisa', 'Suciu', 0.3, false),
    ]);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    // Jahresübersicht ist geladen (Name steht in der Tabelle) …
    expect((await screen.findAllByText(/Larisa/)).length).toBeGreaterThan(0);
    // … aber kein Banner.
    expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument();
  });
});
