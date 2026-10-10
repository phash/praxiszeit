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

describe('ChangeRequestForm — Anrechnung beantragen (Spec P21)', () => {
  const K7 = {
    id: 'te1', date: '2026-06-01', start_time: '07:45:00', end_time: '18:15:00',
    raw_start_time: '07:00:00', raw_end_time: '19:00:00', break_minutes: 0,
  };
  const AUTO_CLOSED_MSG = 'Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben.';
  const autoClosedK15 = { ...K7, start_time: '08:00:00', raw_start_time: null, raw_end_time: '23:59:00', auto_closed: true };

  it('belegt die Rohstempel vor und sendet das Kennzeichen', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={K7} requestType="update" requestCredit onClose={vi.fn()} onSuccess={onSuccess} />);
    expect(screen.getByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:00');
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('19:00');
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/change-requests', expect.objectContaining({
      request_type: 'update', time_entry_id: 'te1', proposed_start_time: '07:00',
      proposed_end_time: '19:00', request_credit_override: true,
    }));
  });

  it('verlangt bei einem automatisch geschlossenen Eintrag das tatsächliche Ende (P18)', async () => {
    render(<ChangeRequestForm
      entry={autoClosedK15}
      requestType="update" requestCredit onClose={vi.fn()} onSuccess={vi.fn()} />);
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('');
    submitWithReason();
    expect(await screen.findByText(AUTO_CLOSED_MSG)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  // Dieselbe Regel wie der Server (credit_override_service.lacks_actual_end):
  // das gespeicherte (gekappte) Ende ist kein tatsächliches Ende.
  it('lehnt das gekappte Ende 18:15 eines automatisch geschlossenen Eintrags ab, ein echtes Ende geht durch', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm
      entry={autoClosedK15}
      requestType="update" requestCredit onClose={vi.fn()} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByLabelText('Bis'), { target: { value: '18:15' } });
    submitWithReason();
    expect(await screen.findByText(AUTO_CLOSED_MSG)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Bis'), { target: { value: '17:30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Antrag stellen' }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/change-requests', expect.objectContaining({
      proposed_start_time: '08:00', proposed_end_time: '17:30', request_credit_override: true,
    }));
  });

  it('ein gewöhnlicher Änderungsantrag sendet kein Kennzeichen', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={K7} requestType="update" onClose={vi.fn()} onSuccess={onSuccess} />);
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:45');
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).not.toHaveProperty('request_credit_override');
  });

  // Das Monatsjournal kennt die Notiz eines Eintrags nicht (JournalTimeEntry
  // führt sie nicht). Ein leeres Feld darf die gespeicherte Notiz dann nicht
  // überschreiben — die Genehmigung übernimmt jede nicht-null proposed_note.
  it('sendet keine Notiz, wenn der Aufrufer sie nicht kennt und das Feld leer bleibt', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={K7} requestType="update" requestCredit onClose={vi.fn()} onSuccess={onSuccess} />);
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post.mock.calls[0][1].proposed_note).toBeNull();
  });

  it('Kontrolltest: eine bekannte, geleerte Notiz wird weiter als leer gesendet', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={{ ...K7, note: 'alt' }} requestType="update" onClose={vi.fn()} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByLabelText('Notiz'), { target: { value: '' } });
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post.mock.calls[0][1].proposed_note).toBe('');
  });
});
