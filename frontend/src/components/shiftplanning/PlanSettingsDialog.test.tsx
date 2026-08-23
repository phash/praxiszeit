import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/shiftPlanning', () => ({ updatePlan: vi.fn() }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import * as api from '../../api/shiftPlanning';
import PlanSettingsDialog from './PlanSettingsDialog';
import type { PlanDetail } from '../../api/shiftPlanning';

const plan: PlanDetail = {
  id: 'p1',
  name: 'Herbstplan',
  description: null,
  is_active: false,
  active_from_date: '2026-09-01',
  active_until_date: null,
  active_today: false,
  visible_to_employees: false,
  slots: [],
  validation: { is_valid: true, understaffed_slot_ids: [] },
};

describe('PlanSettingsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.updatePlan as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('spiegelt den aktuellen Freigabe-Zustand', () => {
    render(
      <PlanSettingsDialog isOpen plan={{ ...plan, visible_to_employees: true }} onSaved={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByLabelText(/Für Mitarbeitende sichtbar/i)).toBeChecked();
  });

  it('sendet die eingeschaltete Freigabe mit', async () => {
    render(<PlanSettingsDialog isOpen plan={plan} onSaved={() => {}} onClose={() => {}} />);

    fireEvent.click(screen.getByLabelText(/Für Mitarbeitende sichtbar/i));
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(api.updatePlan).toHaveBeenCalled());
    expect((api.updatePlan as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({
      visible_to_employees: true,
    });
  });

  it('sendet die Freigabe auch dann mit, wenn sie unverändert aus bleibt', async () => {
    render(<PlanSettingsDialog isOpen plan={plan} onSaved={() => {}} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(api.updatePlan).toHaveBeenCalled());
    expect((api.updatePlan as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({
      visible_to_employees: false,
    });
  });
});
