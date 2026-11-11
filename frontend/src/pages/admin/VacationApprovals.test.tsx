import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VacationApprovals from './VacationApprovals';

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => toast }));

const base = {
  user_id: 'u1',
  user_first_name: 'Julia',
  user_last_name: 'Wagner',
  hours: 8,
  absence_type: 'vacation',
  status: 'pending',
  created_at: '2026-10-01T08:00:00Z',
};

function mockApi(requests: unknown[]) {
  getMock.mockImplementation((url: string) =>
    url.startsWith('/admin/vacation-requests')
      ? Promise.resolve({ data: requests })
      : Promise.resolve({ data: [] }),
  );
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
});

describe('<VacationApprovals /> Arbeitstage (#496)', () => {
  it('zeigt die vom Server gezählten Tage, Bruchteile mit Komma', async () => {
    mockApi([
      { ...base, id: 'vr1', date: '2026-11-02', end_date: '2026-11-06', days: 4 },
      { ...base, id: 'vr2', date: '2026-11-09', days: 0.5 },
      { ...base, id: 'vr3', date: '2026-11-10', days: 1 },
    ]);
    render(<VacationApprovals />);
    expect(await screen.findByText('4 Tage')).toBeInTheDocument();
    expect(screen.getByText('0,5 Tage')).toBeInTheDocument();
    expect(screen.getByText('1 Tag')).toBeInTheDocument();
    expect(screen.queryByText('0.5 Tage')).toBeNull();
  });
});

describe('<VacationApprovals /> Schalter Genehmigungspflicht (P1.4)', () => {
  it('trägt die sichtbare Überschrift als zugänglichen Namen', async () => {
    // Der Schalter war ein reiner Knopf mit role="switch" ohne Namen —
    // Bildschirmleser lasen nur „Schalter, aus".
    mockApi([]);
    render(<VacationApprovals />);
    expect(
      await screen.findByRole('switch', { name: 'Abwesenheitsanträge genehmigungspflichtig' }),
    ).toBeInTheDocument();
  });
});

describe('<VacationApprovals /> Ladezustand (abw-13)', () => {
  it('Genehmigen zeigt „Wird gebucht…“ und sperrt den Knopf, bis die Antwort da ist', async () => {
    mockApi([{ ...base, id: 'vr1', date: '2099-11-02', days: 1 }]);
    let release: (v: unknown) => void = () => {};
    postMock.mockReturnValue(new Promise((r) => { release = r; }));
    render(<VacationApprovals />);
    fireEvent.click(await screen.findByRole('button', { name: 'Genehmigen' }));
    const busy = await screen.findByRole('button', { name: 'Wird gebucht…' });
    expect(busy).toBeDisabled();
    release({ data: {} });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Antrag genehmigt'));
  });
});
