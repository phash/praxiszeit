import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { getQualifications, setUserQualifications, toastError } = vi.hoisted(() => ({
  getQualifications: vi.fn(),
  setUserQualifications: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('../../api/shiftPlanning', () => ({ getQualifications, setUserQualifications }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: toastError, info: vi.fn(), warning: vi.fn(), showToast: vi.fn() }),
}));

import QualificationMatrix from './QualificationMatrix';

const ws = (id: string, name: string) => ({
  id, name, location_id: null, location_name: null, color: null, sort_order: 0,
});
const matrix = {
  users: [{ id: 'u1', first_name: 'Anna', last_name: 'Azubi' }],
  workstations: [ws('ws1', 'Tresen'), ws('ws2', 'Labor')],
  qualifications: [{ user_id: 'u1', workstation_id: 'ws1' }],
};

beforeEach(() => {
  getQualifications.mockReset().mockResolvedValue(matrix);
  setUserQualifications.mockReset().mockResolvedValue({ user_id: 'u1', workstation_ids: ['ws1', 'ws2'] });
  toastError.mockReset();
});

describe('QualificationMatrix', () => {
  it('renders existing qualifications as checked', async () => {
    render(<QualificationMatrix />);
    await screen.findByText('Anna Azubi');
    expect((screen.getByLabelText('Anna Azubi – Tresen') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Anna Azubi – Labor') as HTMLInputElement).checked).toBe(false);
  });

  it('toggling a cell saves that employee row with the new set', async () => {
    render(<QualificationMatrix />);
    fireEvent.click(await screen.findByLabelText('Anna Azubi – Labor'));
    await waitFor(() => expect(setUserQualifications).toHaveBeenCalled());
    const [userId, wsIds] = setUserQualifications.mock.calls[0];
    expect(userId).toBe('u1');
    expect([...wsIds].sort()).toEqual(['ws1', 'ws2']);
  });

  it('shows a retry panel when loading fails, then recovers', async () => {
    getQualifications.mockReset().mockRejectedValueOnce(new Error('net'));
    render(<QualificationMatrix />);
    const retry = await screen.findByText('Erneut laden');
    expect(toastError).toHaveBeenCalled();
    getQualifications.mockResolvedValueOnce(matrix);
    fireEvent.click(retry);
    await screen.findByText('Anna Azubi'); // recovered, not the misleading empty state
  });

  it('reverts + toasts when saving fails', async () => {
    setUserQualifications.mockRejectedValueOnce(new Error('boom'));
    render(<QualificationMatrix />);
    const labor = await screen.findByLabelText('Anna Azubi – Labor');
    fireEvent.click(labor);
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect((labor as HTMLInputElement).checked).toBe(false); // reverted
  });
});
