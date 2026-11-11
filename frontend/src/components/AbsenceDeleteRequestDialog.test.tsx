import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// P1.1: Mitarbeitende löschen Abwesenheiten vergangener Tage nicht direkt
// (Server 409 PAST_DAY_ABSENCE_DETAIL), sondern beantragen die Löschung.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('../api/client', () => ({ default: { post } }));

import AbsenceDeleteRequestDialog from './AbsenceDeleteRequestDialog';

const ABSENCE = { id: 'a1', date: '2026-06-03', type: 'sick', hours: 8 };

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: {} });
});

function renderDialog() {
  const onSuccess = vi.fn();
  const onClose = vi.fn();
  render(<AbsenceDeleteRequestDialog absence={ABSENCE} onClose={onClose} onSuccess={onSuccess} />);
  return { onSuccess, onClose };
}

describe('<AbsenceDeleteRequestDialog /> (P1.1)', () => {
  it('zeigt, welche Abwesenheit gelöscht werden soll', () => {
    renderDialog();
    expect(screen.getByRole('dialog', { name: 'Änderungsantrag: Löschung beantragen' })).toBeInTheDocument();
    expect(screen.getByText('03.06.2026')).toBeInTheDocument();
    expect(screen.getByText('Krank')).toBeInTheDocument();
  });

  it('verlangt eine Begründung, bevor etwas gesendet wird', async () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Antrag stellen' }));
    expect(await screen.findByText('Bitte geben Sie eine Begründung an')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('sendet einen Lösch-Antrag mit absence_id und Begründung', async () => {
    const { onSuccess } = renderDialog();
    fireEvent.change(screen.getByLabelText(/Begründung/), { target: { value: '  War doch im Dienst  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Antrag stellen' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/change-requests/', {
      request_type: 'delete',
      entry_kind: 'absence',
      absence_id: 'a1',
      reason: 'War doch im Dienst',
    }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });

  it('zeigt die Meldung des Servers und bleibt offen', async () => {
    post.mockRejectedValue({ response: { data: { detail: 'Es existiert bereits ein offener Antrag für diese Abwesenheit' } } });
    const { onSuccess } = renderDialog();
    fireEvent.change(screen.getByLabelText(/Begründung/), { target: { value: 'doppelt' } });
    fireEvent.click(screen.getByRole('button', { name: 'Antrag stellen' }));
    expect(await screen.findByText('Es existiert bereits ein offener Antrag für diese Abwesenheit')).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
