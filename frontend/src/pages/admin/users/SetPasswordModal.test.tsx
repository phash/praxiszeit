import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../../api/client', () => ({ default: { post: vi.fn() } }));
vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import SetPasswordModal from './SetPasswordModal';

describe('SetPasswordModal', () => {
  it('user-09: Klick auf den Hintergrund schließt nicht (getipptes Passwort bleibt)', () => {
    const onClose = vi.fn();
    render(<SetPasswordModal userId="u1" userName="Jane Doe" onClose={onClose} />);
    fireEvent.click(screen.getByTestId('password-backdrop'));
    expect(onClose).not.toHaveBeenCalled();
  });
});
