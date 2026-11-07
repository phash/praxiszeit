import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PasswordConfirmDialog from './PasswordConfirmDialog';

describe('PasswordConfirmDialog (S1-02/S1-09)', () => {
  it('schickt das eingegebene Passwort und sperrt den Knopf ohne Eingabe', async () => {
    const onSubmit = vi.fn().mockResolvedValue(true);
    render(
      <PasswordConfirmDialog
        isOpen
        title="Sicherung herunterladen"
        message="Bitte bestätigen"
        confirmLabel="Herunterladen"
        onSubmit={onSubmit}
        onCancel={() => {}}
      />,
    );
    const button = screen.getByRole('button', { name: 'Herunterladen' });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ihr Passwort'), { target: { value: 'Geheim2026!' } });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('Geheim2026!'));
  });

  it('rendert nichts, solange er geschlossen ist', () => {
    const { container } = render(
      <PasswordConfirmDialog isOpen={false} title="t" message="m" confirmLabel="ok"
        onSubmit={vi.fn()} onCancel={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
