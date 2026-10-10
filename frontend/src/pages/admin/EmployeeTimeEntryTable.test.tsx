import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import EmployeeTimeEntryTable from './EmployeeTimeEntryTable';

vi.mock('../../api/client', () => ({ default: { post: vi.fn() } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

const K7_ENTRY = {
  id: 'e1', date: '2026-06-01', start_time: '07:45:00', end_time: '18:15:00',
  raw_start_time: '07:00:00', raw_end_time: '19:00:00', break_minutes: 0, net_hours: 8, note: '',
  uncredited_minutes: 150, not_credited_minutes: 240, credit_override: false, auto_closed: false,
};

describe('<EmployeeTimeEntryTable /> (Spec 12.3: Netto-Spalte und RawStampNote)', () => {
  it('zeigt Netto und die Zeile „nicht angerechnet"', () => {
    render(<EmployeeTimeEntryTable entries={[K7_ENTRY]} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole('columnheader', { name: 'Netto' })).toBeInTheDocument();
    const row = screen.getAllByRole('row')[1];
    expect(within(row).getByText('8:00 h')).toBeInTheDocument();
    expect(within(row).getByText(/4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken/)).toBeInTheDocument();
  });
});
