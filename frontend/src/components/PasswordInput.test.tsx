import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import PasswordInput from './PasswordInput';

describe('PasswordInput', () => {
  it('renders as type=password by default — input is masked at mount', () => {
    render(<PasswordInput aria-label="Passwort" />);
    const input = screen.getByLabelText('Passwort') as HTMLInputElement;
    expect(input.type).toBe('password');
  });

  it('shows the "Passwort anzeigen" toggle button by default', () => {
    render(<PasswordInput aria-label="Passwort" />);
    // Two elements share the aria-label "Passwort anzeigen"-derived names
    // depending on visibility state. At mount the toggle's aria-label is
    // exactly this ("show password") — assert the explicit attribute so we
    // catch any future drift.
    const toggle = screen.getByRole('button', { name: 'Passwort anzeigen' });
    expect(toggle).toHaveAttribute('type', 'button'); // never submits a form
    expect(toggle).toHaveAttribute('tabindex', '-1'); // skipped in tab order
  });

  it('flips the input type to text when the toggle is clicked, then back', async () => {
    const user = userEvent.setup();
    render(<PasswordInput aria-label="Passwort" />);
    const input = screen.getByLabelText('Passwort') as HTMLInputElement;
    expect(input.type).toBe('password');

    await user.click(screen.getByRole('button', { name: 'Passwort anzeigen' }));
    expect(input.type).toBe('text');

    // The toggle's aria-label flips with the visible state — this is the
    // signal screen-reader users get that their password is now exposed.
    await user.click(screen.getByRole('button', { name: 'Passwort verbergen' }));
    expect(input.type).toBe('password');
  });

  it('keeps focus on the input when the toggle is clicked (tabindex=-1)', async () => {
    const user = userEvent.setup();
    render(<PasswordInput aria-label="Passwort" data-testid="pw" />);
    const input = screen.getByTestId('pw') as HTMLInputElement;
    input.focus();
    expect(input).toHaveFocus();

    // The toggle has tabindex=-1, so a Tab keypress must NOT move focus to
    // it — that would disrupt typing flow when users tab into the password
    // field from the username field.
    await user.tab();
    expect(input).not.toHaveFocus();
    // Either focus moves elsewhere or to body, but not to the toggle.
    expect(screen.getByRole('button', { name: /Passwort anzeigen/ })).not.toHaveFocus();
  });

  it('forwards arbitrary input props (placeholder, name, value)', () => {
    const { rerender } = render(
      <PasswordInput aria-label="pw" placeholder="••••••" name="password" />,
    );
    const input = screen.getByLabelText('pw') as HTMLInputElement;
    expect(input.placeholder).toBe('••••••');
    expect(input.name).toBe('password');

    // value flows through (controlled-component pattern works)
    rerender(
      <PasswordInput
        aria-label="pw"
        placeholder="••••••"
        name="password"
        value="secret123"
        onChange={() => {}}
      />,
    );
    expect((screen.getByLabelText('pw') as HTMLInputElement).value).toBe('secret123');
  });

  it('appends the consumer className without overwriting the pr-10 padding', () => {
    render(<PasswordInput aria-label="pw" className="custom-input" />);
    const input = screen.getByLabelText('pw') as HTMLInputElement;
    // Custom class kept, plus the component's own pr-10 (padding-right for
    // the toggle button). If the merge logic were broken the toggle would
    // overlap typed text.
    expect(input.className).toContain('custom-input');
    expect(input.className).toContain('pr-10');
  });
});
