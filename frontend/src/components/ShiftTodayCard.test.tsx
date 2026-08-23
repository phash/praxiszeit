import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/shiftPlanning', async () => {
  const actual = await vi.importActual<typeof import('../api/shiftPlanning')>('../api/shiftPlanning');
  return { ...actual, getMyToday: vi.fn() };
});
vi.mock('../stores/systemStore', () => ({
  useSystemStore: (sel: (s: unknown) => unknown) => sel({ isShiftPlanningEnabled: () => true }),
}));

import * as api from '../api/shiftPlanning';
import ShiftTodayCard from './ShiftTodayCard';
import type { MyTodayEntry } from '../api/shiftPlanning';

const entry = (over: Partial<MyTodayEntry> = {}): MyTodayEntry => ({
  plan_id: 'p1',
  plan_name: 'Normalzustand',
  workstation_name: 'Tresen',
  location_name: 'Hauptstelle',
  start_time: '08:00',
  end_time: '12:00',
  note: null,
  ...over,
});

describe('ShiftTodayCard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zeigt den Hinweis, wenn einer gesetzt ist (#453)', async () => {
    (api.getMyToday as ReturnType<typeof vi.fn>).mockResolvedValue({
      date: '2026-08-23',
      weekday: 6,
      entries: [entry({ note: 'Heute Telefon mitübernehmen' })],
    });

    render(<ShiftTodayCard />);

    await waitFor(() => expect(screen.getByText('Tresen')).toBeInTheDocument());
    expect(screen.getByText(/» Heute Telefon mitübernehmen/)).toBeInTheDocument();
  });

  it('zeigt keine Hinweiszeile, wenn keiner gesetzt ist', async () => {
    (api.getMyToday as ReturnType<typeof vi.fn>).mockResolvedValue({
      date: '2026-08-23',
      weekday: 6,
      entries: [entry()],
    });

    render(<ShiftTodayCard />);

    await waitFor(() => expect(screen.getByText('Tresen')).toBeInTheDocument());
    expect(screen.queryByText(/»/)).not.toBeInTheDocument();
  });
});
