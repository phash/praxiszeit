import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SlotDialog from './SlotDialog';

// getQualifications is fired on mount; stub it so the dialog renders in isolation.
vi.mock('../../api/shiftPlanning', async (importActual) => {
  const actual = await importActual<typeof import('../../api/shiftPlanning')>();
  return { ...actual, getQualifications: vi.fn().mockResolvedValue([]) };
});

const baseProps = {
  isOpen: true,
  mode: 'create' as const,
  workstations: [{ id: 'ws1', name: 'Tresen', color: '#FF8800', location_id: null, location_name: null }],
  employees: [],
  initial: {
    workstation_id: 'ws1',
    weekday: 1,
    start_time: '08:00',
    end_time: '12:00',
    min_staff: 1,
    userIds: [] as string[],
  },
  onSubmit: vi.fn(),
  onClose: vi.fn(),
};

describe('SlotDialog weekday restriction (#371)', () => {
  it('offers only the enabled weekdays in the Wochentag select', () => {
    render(<SlotDialog {...baseProps} weekdays={[1, 2, 3]} />);
    const select = screen.getByLabelText('Wochentag') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toEqual(['Dienstag', 'Mittwoch', 'Donnerstag']);
  });

  it('falls back to all seven weekdays when no config is passed', () => {
    render(<SlotDialog {...baseProps} />);
    const select = screen.getByLabelText('Wochentag') as HTMLSelectElement;
    expect(select.options.length).toBe(7);
  });
});
