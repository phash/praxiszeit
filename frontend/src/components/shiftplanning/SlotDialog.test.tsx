import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    note: '',
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

describe('SlotDialog Hinweisfeld (#443)', () => {
  it('lädt einen vorhandenen Hinweis und gibt ihn beim Speichern weiter', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <SlotDialog
        isOpen
        mode="edit"
        workstations={[{ id: 'w1', name: 'Tresen', location_id: null, location_name: null, color: null, sort_order: 0 }]}
        employees={[]}
        initial={{
          workstation_id: 'w1',
          weekday: 0,
          start_time: '08:00',
          end_time: '12:00',
          min_staff: 1,
          userIds: [],
          note: 'Einarbeitung Azubi',
        }}
        onSubmit={onSubmit}
        onClose={() => {}}
      />,
    );

    const field = screen.getByLabelText(/Hinweis/i) as HTMLTextAreaElement;
    expect(field.value).toBe('Einarbeitung Azubi');

    fireEvent.change(field, { target: { value: 'Nur Notfall' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ note: 'Nur Notfall' });
  });

  it('sendet einen leeren Hinweis als null', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <SlotDialog
        isOpen
        mode="create"
        workstations={[{ id: 'w1', name: 'Tresen', location_id: null, location_name: null, color: null, sort_order: 0 }]}
        employees={[]}
        initial={{
          workstation_id: 'w1', weekday: 0, start_time: '08:00', end_time: '12:00',
          min_staff: 1, userIds: [], note: '',
        }}
        onSubmit={onSubmit}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ note: null });
  });
});
