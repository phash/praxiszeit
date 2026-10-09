import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
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

// Review F3 (#501): Seit der Banner allein am Server-Flag hängt, darf er beim
// Umschalten des Jahres nicht mit der Liste des VORHERIGEN Jahres stehen bleiben —
// weder solange die neue Anfrage läuft noch wenn sie scheitert. Sonst stünden die
// Namen aus 2026 unter „verfallen bis 31.03.2026" für das gewählte Jahr 2025.
describe('AdminDashboard Jahresend-Warnung beim Jahreswechsel (#501, Review F3)', () => {
  function mockWithYear(onOtherYear: () => Promise<unknown>) {
    getMock.mockImplementation((url: string) => {
      if (url.startsWith('/admin/reports/yearly-absences')) {
        if (url.includes('year=2026')) {
          return Promise.resolve({ data: [yearlyRow('u2', 'Aura', 'Haiser', 3.0, true)] });
        }
        return onOtherYear();
      }
      if (url.startsWith('/admin/reports/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: null });
    });
  }

  it('blendet den Banner aus, solange die Anfrage für das neue Jahr läuft', async () => {
    mockWithYear(() => new Promise(() => {})); // hängt
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);

    fireEvent.change(screen.getByLabelText('Jahr'), { target: { value: '2025' } });

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(expect.stringContaining('yearly-absences?year=2025')),
    );
    expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument();
  });

  it('blendet den Banner aus, wenn die Anfrage für das neue Jahr scheitert', async () => {
    mockWithYear(() => Promise.reject(new Error('422')));
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    await screen.findByText(/Jahresend-Warnung: Offene Urlaubstage/);

    fireEvent.change(screen.getByLabelText('Jahr'), { target: { value: '202' } });

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(expect.stringMatching(/yearly-absences\?year=202$/)),
    );
    await waitFor(() => expect(screen.queryByText(/Jahresend-Warnung/)).not.toBeInTheDocument());
  });
});
