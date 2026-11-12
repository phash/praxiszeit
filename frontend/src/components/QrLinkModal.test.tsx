import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const trap = vi.hoisted(() => ({ options: undefined as undefined | { escapeDeactivates?: boolean; onDeactivate?: () => void } }));
vi.mock('./DialogFocusTrap', () => ({
  default: ({ children, focusTrapOptions }: { children: React.ReactNode; focusTrapOptions: typeof trap.options }) => {
    trap.options = focusTrapOptions;
    return <>{children}</>;
  },
}));

import QrLinkModal from './QrLinkModal';

describe('QrLinkModal (ui-21)', () => {
  it('liegt in einer Fokusfalle mit Escape → onClose', () => {
    const onClose = vi.fn();
    render(<QrLinkModal open onClose={onClose} url="https://example.invalid" />);
    expect(screen.getByRole('dialog', { name: 'Auf dem Smartphone öffnen' })).toBeInTheDocument();
    expect(trap.options?.escapeDeactivates).toBe(true);
    trap.options?.onDeactivate?.();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('hört nicht mehr auf Escape am window (würde überlagerte Dialoge mitschließen)', () => {
    const onClose = vi.fn();
    render(<QrLinkModal open onClose={onClose} url="https://example.invalid" />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
