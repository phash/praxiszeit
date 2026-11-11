import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * Handbuch-Fund P5.2: Die Dialoge der Schichtplanung (Slot, Automatisch füllen,
 * Plan-Einstellungen, Plan duplizieren) trugen kein role="dialog" — Screenreader
 * und Locator `getByRole('dialog')` fanden sie nicht. Jeder Dialog hat jetzt
 * role + aria-modal + aria-labelledby auf seine Überschrift.
 */
vi.mock('../../api/client', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: [] }) },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('../../api/shiftPlanning', async (importActual) => {
  const actual = await importActual<typeof import('../../api/shiftPlanning')>();
  const plan = {
    id: 'p1',
    name: 'Wochenplan',
    description: null,
    is_active: true,
    active_from_date: null,
    active_until_date: null,
    active_today: true,
    visible_to_employees: false,
    slots: [],
    validation: { is_valid: true, understaffed_slot_ids: [] },
  };
  return {
    ...actual,
    listLocations: vi.fn().mockResolvedValue([]),
    listWorkstations: vi.fn().mockResolvedValue([
      { id: 'ws1', name: 'Tresen', color: '#FF8800', location_id: null, location_name: null },
    ]),
    listPlans: vi.fn().mockResolvedValue([{ ...plan, slot_count: 0, is_valid: true }]),
    getPlan: vi.fn().mockResolvedValue(plan),
    getQualifications: vi.fn().mockResolvedValue([]),
  };
});

import AdminShiftPlanning from './ShiftPlanning';

describe('Schichtplanung: Dialoge sind benannte Dialoge (P5.2)', () => {
  beforeEach(async () => {
    render(<AdminShiftPlanning />);
    await screen.findByRole('heading', { name: 'Wochenplan' });
  });

  it.each([
    ['Slot', 'Neuer Zeitslot'],
    ['Automatisch füllen', 'Automatisch füllen'],
    ['Bearbeiten', 'Plan-Einstellungen'],
    ['Duplizieren', 'Schichtplan duplizieren'],
  ])('Knopf „%s“ öffnet den Dialog „%s“', async (button, title) => {
    fireEvent.click(screen.getByRole('button', { name: button, exact: true }));
    const dialog = await waitFor(() => screen.getByRole('dialog', { name: title }));
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });
});
