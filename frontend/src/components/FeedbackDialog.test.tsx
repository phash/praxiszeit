import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// apiClient.post + toast spies, hoisted so the vi.mock factories can use them.
const { post, toastSuccess, toastError } = vi.hoisted(() => ({
  post: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('../api/client', () => ({ default: { post } }));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({
    success: toastSuccess,
    error: toastError,
    info: vi.fn(),
    warning: vi.fn(),
    showToast: vi.fn(),
  }),
}));

import FeedbackDialog from './FeedbackDialog';

beforeEach(() => {
  post.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

function renderDialog() {
  const onClose = vi.fn();
  render(<FeedbackDialog onClose={onClose} />);
  return { onClose };
}

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/Titel/i), 'Es hakt');
  await user.type(screen.getByLabelText(/Beschreibung/i), 'Beim Stempeln passiert X');
}

describe('FeedbackDialog', () => {
  it('renders an accessible dialog with title, description, severity and version hint', () => {
    renderDialog();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByLabelText(/Titel/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Beschreibung/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Schweregrad/i)).toBeInTheDocument();
    // Transparenz: zeigt, dass die Version mitgeschickt wird.
    expect(screen.getByText(/Version/i)).toBeInTheDocument();
  });

  it('disables submit until title AND description are filled', async () => {
    const user = userEvent.setup();
    renderDialog();
    const submit = screen.getByRole('button', { name: /senden/i });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Titel/i), 'nur Titel');
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Beschreibung/i), 'jetzt auch Text');
    expect(submit).toBeEnabled();
  });

  it('posts title/description/severity and shows success toast + closes on 200', async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({ data: { status: 'received', id: 'bug-1' } });
    const { onClose } = renderDialog();
    await fillValid(user);
    await user.selectOptions(screen.getByLabelText(/Schweregrad/i), 'high');
    await user.click(screen.getByRole('button', { name: /senden/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith('/feedback/report', {
      title: 'Es hakt',
      description: 'Beim Stempeln passiert X',
      severity: 'high',
    });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it('defaults severity to medium', async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({ data: { status: 'received' } });
    renderDialog();
    await fillValid(user);
    await user.click(screen.getByRole('button', { name: /senden/i }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toMatchObject({ severity: 'medium' });
  });

  it('shows an error toast and stays open when the request fails', async () => {
    const user = userEvent.setup();
    post.mockRejectedValue({ response: { status: 409, data: { detail: 'Lizenz inaktiv' } } });
    const { onClose } = renderDialog();
    await fillValid(user);
    await user.click(screen.getByRole('button', { name: /senden/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('enforces the 200-char title limit via maxLength', () => {
    renderDialog();
    expect(screen.getByLabelText(/Titel/i)).toHaveAttribute('maxLength', '200');
  });

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDialog();
    await user.click(screen.getByRole('button', { name: /abbrechen/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
