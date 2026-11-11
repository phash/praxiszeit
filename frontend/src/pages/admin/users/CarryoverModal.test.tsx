import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
});
