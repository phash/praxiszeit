import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// #491 F4: das Antragsformular der Zeiterfassung fragt an Sonn- und Feiertagen
// nach dem §10-Ausnahmegrund — wie das Monatsjournal.
const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock('../api/client', () => ({ default: { post, get } }));

import ChangeRequestForm from './ChangeRequestForm';

const SUNDAY = '2026-06-07';
const MONDAY = '2026-06-08';
const ASCENSION = '2026-05-14'; // Donnerstag, Christi Himmelfahrt
const LABEL = /Ausnahmegrund \(§10 ArbZG\)/;

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  post.mockResolvedValue({ data: {} });
  get.mockResolvedValue({ data: [{ date: ASCENSION, name: 'Christi Himmelfahrt' }] });
});

function renderCreate() {
  const onSuccess = vi.fn();
  render(<ChangeRequestForm entry={null} requestType="create" onClose={vi.fn()} onSuccess={onSuccess} />);
  return { onSuccess };
}

function setDate(value: string) {
  fireEvent.change(screen.getByLabelText('Datum'), { target: { value } });
}

function submitWithReason() {
  fireEvent.change(screen.getByPlaceholderText('Warum ist diese Änderung notwendig?'), {
    target: { value: 'Vergessen zu stempeln' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Antrag stellen' }));
}

describe('ChangeRequestForm — §10-Ausnahmegrund (#491 F4)', () => {
  it('fragt an einem Sonntag nach dem Grund und sendet ihn mit', async () => {
    const { onSuccess } = renderCreate();
    setDate(SUNDAY);
    const field = await screen.findByLabelText(LABEL);
    fireEvent.change(field, { target: { value: '  KV-Notdienst  ' } });
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/change-requests', expect.objectContaining({
      request_type: 'create',
      proposed_date: SUNDAY,
      proposed_sunday_exception_reason: 'KV-Notdienst',
    }));
  });

  it('fragt an einem gesetzlichen Feiertag unter der Woche ebenfalls', async () => {
    renderCreate();
    setDate(ASCENSION);
    expect(await screen.findByLabelText(LABEL)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/holidays?year=2026');
  });

  it('zeigt das Feld an einem normalen Werktag nicht und sendet keinen Grund', async () => {
    const { onSuccess } = renderCreate();
    setDate(MONDAY);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument();
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    const payload = post.mock.calls[0][1];
    expect(payload.proposed_sunday_exception_reason ?? null).toBeNull();
  });

  it('sendet keinen Grund, wenn das Datum nachträglich auf einen Werktag wechselt', async () => {
    const { onSuccess } = renderCreate();
    setDate(SUNDAY);
    fireEvent.change(await screen.findByLabelText(LABEL), { target: { value: 'Notdienst' } });
    setDate(MONDAY);
    await waitFor(() => expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument());
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post.mock.calls[0][1].proposed_sunday_exception_reason ?? null).toBeNull();
  });

  it('übernimmt beim Ändern den gespeicherten Grund des Eintrags', async () => {
    const entry = {
      id: 'e1', date: SUNDAY, start_time: '09:00:00', end_time: '13:00:00', break_minutes: 0,
      is_sunday_or_holiday: true, sunday_exception_reason: 'Notdienst',
    };
    render(<ChangeRequestForm entry={entry} requestType="update" onClose={vi.fn()} onSuccess={vi.fn()} />);
    expect(await screen.findByLabelText(LABEL)).toHaveValue('Notdienst');
  });

  it('bleibt bei fehlgeschlagenem Feiertagsabruf auf die Sonntagsregel zurück', async () => {
    get.mockRejectedValue(new Error('offline'));
    renderCreate();
    setDate(SUNDAY);
    expect(await screen.findByLabelText(LABEL)).toBeInTheDocument();
  });

  it('fragt beim Lösch-Antrag nicht', async () => {
    const entry = {
      id: 'e1', date: SUNDAY, start_time: '09:00:00', end_time: '13:00:00', break_minutes: 0,
      is_sunday_or_holiday: true,
    };
    render(<ChangeRequestForm entry={entry} requestType="delete" onClose={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument();
  });
});
