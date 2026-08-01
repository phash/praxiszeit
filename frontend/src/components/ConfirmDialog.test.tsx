import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ConfirmDialog from './ConfirmDialog';

const renderDialog = (overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const props = {
    isOpen: true,
    title: 'Eintrag löschen',
    message: 'Sicher? Dies kann nicht rückgängig gemacht werden.',
    onConfirm,
    onCancel,
    ...overrides,
  };
  render(<ConfirmDialog {...props} />);
  return { onConfirm, onCancel };
};

describe('ConfirmDialog', () => {
  it('renders nothing when isOpen=false', () => {
    renderDialog({ isOpen: false });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('renders title and message inside an accessible alertdialog', () => {
    renderDialog();
    const dialog = screen.getByRole('alertdialog');
    // The aria-modal/labelledby/describedby plumbing is the contract that
    // makes this dialog usable for screen readers — assert the actual
    // attributes, not just visible text.
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-dialog-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'confirm-dialog-desc');
    expect(screen.getByRole('heading', { name: 'Eintrag löschen' })).toBeInTheDocument();
    expect(screen.getByText(/Dies kann nicht rückgängig gemacht werden/)).toBeInTheDocument();
  });

  it('uses default labels "Bestätigen" and "Abbrechen" when none are given', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Abbrechen' })).toBeInTheDocument();
  });

  it('respects custom button labels', () => {
    renderDialog({ confirmLabel: 'Löschen', cancelLabel: 'Behalten' });
    expect(screen.getByRole('button', { name: 'Löschen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Behalten' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Bestätigen' })).not.toBeInTheDocument();
  });

  it('calls onConfirm exactly once when the confirm button is clicked', async () => {
    const user = userEvent.setup();
    const { onConfirm, onCancel } = renderDialog({ confirmLabel: 'Löschen' });
    await user.click(screen.getByRole('button', { name: 'Löschen' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('calls onCancel when the cancel button is clicked', async () => {
    const user = userEvent.setup();
    const { onConfirm, onCancel } = renderDialog();
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('calls onCancel when the backdrop is clicked', async () => {
    // The backdrop is the click-outside dismiss surface — clicking it must
    // trigger onCancel, otherwise users can't dismiss via the standard
    // modal-dismiss gesture.
    const user = userEvent.setup();
    const { onCancel } = renderDialog();
    const backdrop = document.querySelector('[aria-hidden="true"].absolute.inset-0');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop as Element);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('autofocuses the cancel button so danger actions never confirm by Enter', () => {
    // Defensive default for destructive ops: the SAFE button gets focus, so
    // a pressed Enter cancels rather than approves the deletion.
    renderDialog({ variant: 'danger' });
    expect(screen.getByRole('button', { name: 'Abbrechen' })).toHaveFocus();
  });

  it.each([
    ['danger', 'bg-red-600'],
    ['warning', 'bg-yellow-600'],
    ['info', 'bg-blue-600'],
  ] as const)('applies the %s variant button colour (%s)', (variant, expectedClass) => {
    renderDialog({ variant, confirmLabel: 'OK' });
    const confirmBtn = screen.getByRole('button', { name: 'OK' });
    expect(confirmBtn.className).toContain(expectedClass);
  });

  // U5 (Audit 2026-07-31): callers such as Users.tsx (anonymize/purge),
  // AdminDashboard.tsx (year-closing) and ErrorMonitoring.tsx build
  // multi-line messages with \n / \n\n + "•" bullets. Plain <p> collapses all
  // whitespace, so the trailing sentence ("... kann nicht rückgängig gemacht
  // werden.") used to glue itself onto the last bullet. `whitespace-pre-line`
  // must be present so the browser actually renders the line breaks.
  it('preserves line breaks in a multi-line message (whitespace-pre-line)', () => {
    const message =
      'Soll Max Mustermann gemäß DSGVO Art. 17 anonymisiert werden?\n\nDabei werden:\n• Name, Benutzername und E-Mail-Adresse unwiderruflich gelöscht\n• Abwesenheiten (Urlaub, Krankheit) gelöscht\n• Zeiteinträge bleiben für ArbZG §16 (2 Jahre) erhalten\n\nDieser Vorgang kann nicht rückgängig gemacht werden.';
    renderDialog({ message });
    const desc = document.getElementById('confirm-dialog-desc');
    expect(desc).not.toBeNull();
    expect(desc!.className).toContain('whitespace-pre-line');
    // The raw text (including the newlines) must reach the DOM unmodified —
    // whitespace-pre-line only changes how the browser RENDERS it, not what
    // ends up in textContent.
    expect(desc!.textContent).toBe(message);
  });
});
