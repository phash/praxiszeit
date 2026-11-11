import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../api/client', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: [] }) },
}));
vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import CarryoverModal from './CarryoverModal';

describe('CarryoverModal', () => {
  it('ist ein benannter, modaler Dialog (P5.2)', async () => {
    render(<CarryoverModal userId="u1" userName="Maria Muster" onClose={() => {}} onSaved={() => {}} />);
    expect(
      await screen.findByRole('dialog', { name: 'Vorjahresübernahme: Maria Muster' }),
    ).toHaveAttribute('aria-modal', 'true');
  });

  it('user-16/05: Felder sind benannt, Schließen hat einen Namen, Minuswerte sind tippbar', async () => {
    render(<CarryoverModal userId="u1" userName="Maria Muster" onClose={() => {}} onSaved={() => {}} />);
    await screen.findByRole('dialog');
    expect(screen.getByRole('button', { name: 'Dialog schließen' })).toBeInTheDocument();
    expect(screen.getByLabelText('Jahr')).toBeInTheDocument();
    const ot = screen.getByLabelText(/Überstunden aus Vorjahr/) as HTMLInputElement;
    expect(screen.getByLabelText(/Resturlaub aus Vorjahr/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.clear(ot);
    await user.type(ot, '-3.5');
    expect(ot.value).toBe('-3.5');
  });
});
