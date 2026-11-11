import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import GenerateDialog from './GenerateDialog';

describe('GenerateDialog', () => {
  it('ist ein benannter, modaler Dialog (P5.2)', () => {
    render(<GenerateDialog planId="p1" onGenerated={() => {}} onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Automatisch füllen' })).toHaveAttribute('aria-modal', 'true');
  });
});
