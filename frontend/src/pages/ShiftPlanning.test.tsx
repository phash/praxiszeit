import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/shiftPlanning', async () => {
  const actual = await vi.importActual<typeof import('../api/shiftPlanning')>('../api/shiftPlanning');
  return { ...actual, listPlans: vi.fn(), getPlan: vi.fn(), downloadPlanPdf: vi.fn() };
});
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('../stores/systemStore', () => ({
  useSystemStore: (sel: (s: unknown) => unknown) =>
    sel({ getShiftPlanningWeekdays: () => [0, 1, 2, 3, 4] }),
}));

import * as api from '../api/shiftPlanning';
import ShiftPlanning from './ShiftPlanning';

const summary = (over: Record<string, unknown> = {}) => ({
  id: 'p1', name: 'Aktueller Plan', description: null, is_active: true,
  active_from_date: null, active_until_date: null, active_today: true,
  visible_to_employees: false, slot_count: 1, is_valid: true, ...over,
});

const detail = (over: Record<string, unknown> = {}) => ({
  ...summary(), slots: [],
  validation: { is_valid: true, understaffed_slot_ids: [] }, ...over,
});

describe('Mitarbeiteransicht Schichtplan', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zeigt einen freigegebenen Zukunftsplan, der heute NICHT gilt', async () => {
    const future = summary({
      id: 'p2', name: 'Ab September', is_active: false, active_today: false,
      visible_to_employees: true, active_from_date: '2026-09-01',
    });
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([future]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail(future));

    render(<ShiftPlanning />);

    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p2'));
    expect(screen.getByText('Ab September')).toBeInTheDocument();
  });

  it('bietet eine Auswahl, sobald mehr als ein Plan sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary(),
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getByRole('option', { name: /Ab September/ })).toBeInTheDocument();
  });

  it('wählt den heute geltenden Plan vor', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
      summary({ id: 'p1', name: 'Aktueller Plan', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p1'));
  });

  it('lädt nur den gewählten Plan, nicht alle', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary(), summary({ id: 'p2', name: 'Zweiter', active_today: true }),
      summary({ id: 'p3', name: 'Dritter', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalled());
    expect((api.getPlan as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
  });

  it('zeigt den leeren Zustand, wenn nichts sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<ShiftPlanning />);
    await waitFor(() => expect(screen.getByText(/Kein Schichtplan/i)).toBeInTheDocument());
    expect(api.getPlan).not.toHaveBeenCalled();
  });
});
