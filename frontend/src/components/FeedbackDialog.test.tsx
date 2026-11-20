import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FeedbackPreview } from '../api/feedback';

const { previewReport, sendReport, saveReportFile, authState } = vi.hoisted(() => ({
  previewReport: vi.fn(),
  sendReport: vi.fn(),
  saveReportFile: vi.fn(),
  authState: { user: { id: 'u1', role: 'employee' } as { id: string; role: string } },
}));

vi.mock('../api/feedback', () => ({ previewReport, sendReport }));
vi.mock('../utils/reportFile', () => ({ saveReportFile }));
vi.mock('../stores/authStore', () => ({
  useAuthStore: (sel?: (s: typeof authState) => unknown) => (sel ? sel(authState) : authState),
}));

import FeedbackDialog from './FeedbackDialog';

const SERVER_DESCRIPTION = 'Bereinigte Beschreibung\n\n--- Protokoll ---\nZeile <user>';

function preview(overrides: Partial<FeedbackPreview> = {}): FeedbackPreview {
  return {
    transport: 'mrd-report-1',
    title: 'Es hakt (bereinigt)',
    description: SERVER_DESCRIPTION,
    fields: { product: 'praxiszeit', app_version: '1.24.3', error_fingerprint: 'abc123' },
    credential_note: 'mrk_praxiszeit_… (nicht angezeigt)',
    log_line_count: 1,
    truncated: false,
    board_url: 'https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit',
    contact_email_dropped: false,
    ...overrides,
  };
}

beforeEach(() => {
  previewReport.mockReset();
  sendReport.mockReset();
  saveReportFile.mockReset();
  authState.user = { id: 'u1', role: 'employee' };
  (URL as any).createObjectURL = vi.fn(() => 'blob:thumb');
  (URL as any).revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function fillAndPreview(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Titel'), 'Es hakt');
  await user.type(screen.getByLabelText('Beschreibung'), 'Beim Stempeln passiert X');
  await user.click(screen.getByRole('button', { name: 'Vorschau' }));
}

describe('FeedbackDialog', () => {
  it('renders the form with Sie-form copy', () => {
    render(<FeedbackDialog onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('heading', { name: 'Problem melden' })).toBeInTheDocument();
    expect(screen.getByLabelText('Fehler')).toBeChecked();
    expect(screen.getByLabelText('Feedback')).toBeInTheDocument();
    expect(screen.getByLabelText('Titel')).toHaveAttribute('maxLength', '200');
    expect(screen.getByLabelText('Beschreibung')).toHaveAttribute('maxLength', '4000');
    expect(screen.getByLabelText('Schweregrad')).toBeInTheDocument();
    expect(screen.getByLabelText('Rückmelde-E-Mail (optional)')).toBeInTheDocument();
    expect(screen.getByLabelText('Bildschirmfoto anhängen (optional)')).toBeInTheDocument();
    expect(
      screen.getByText('Bitte keine Namen von Mitarbeitenden oder Notizen aus Zeiteinträgen eintragen.'),
    ).toBeInTheDocument();
  });

  it('preview shows exactly the server description', async () => {
    const user = userEvent.setup();
    previewReport.mockResolvedValue(preview());
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    const pre = await screen.findByTestId('feedback-preview-description');
    expect(pre.tagName).toBe('PRE');
    expect(pre.textContent).toBe(SERVER_DESCRIPTION);
    expect(screen.getByText('Es hakt (bereinigt)')).toBeInTheDocument();
    expect(screen.getByText('mrk_praxiszeit_… (nicht angezeigt)')).toBeInTheDocument();
    expect(previewReport).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'bug', title: 'Es hakt', text: 'Beim Stempeln passiert X', severity: 'medium' }),
    );
    expect(previewReport.mock.calls[0][0].include_log).toBeFalsy();
  });

  it('send posts previewed title and description unchanged', async () => {
    const user = userEvent.setup();
    const p = preview();
    previewReport.mockResolvedValue(p);
    sendReport.mockResolvedValue({ status: 'received', ref: 'PZ-42', id: 'r1', board_url: p.board_url });
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    await waitFor(() => expect(sendReport).toHaveBeenCalledTimes(1));
    const [sentPreview, req] = sendReport.mock.calls[0];
    expect(sentPreview).toBe(p);
    expect(sentPreview.title).toBe('Es hakt (bereinigt)');
    expect(sentPreview.description).toBe(SERVER_DESCRIPTION);
    expect(req).toMatchObject({ kind: 'bug', severity: 'medium' });
  });

  it('shows ref and board link on success', async () => {
    const user = userEvent.setup();
    const p = preview();
    previewReport.mockResolvedValue(p);
    sendReport.mockResolvedValue({ status: 'received', ref: 'PZ-42', id: 'r1', board_url: p.board_url });
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByText('Danke! Ihre Meldung ist eingegangen: PZ-42.')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Bekannte Probleme ansehen' });
    expect(link).toHaveAttribute('href', p.board_url);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('falls back to id when ref is missing', async () => {
    const user = userEvent.setup();
    const p = preview({ transport: 'legacy' });
    previewReport.mockResolvedValue(p);
    sendReport.mockResolvedValue({ status: 'received', ref: null, id: 'bug-7', board_url: p.board_url });
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByText('Danke! Ihre Meldung ist eingegangen: bug-7.')).toBeInTheDocument();
  });

  it('shows save-file path when send fails with 502', async () => {
    const user = userEvent.setup();
    const p = preview();
    previewReport.mockResolvedValue(p);
    sendReport.mockRejectedValue({
      response: { status: 502, data: { detail: 'Meldeserver nicht erreichbar.', upstream_status: null } },
    });
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByText('Senden fehlgeschlagen – als Datei speichern?')).toBeInTheDocument();
    expect(screen.getByText('Meldeserver nicht erreichbar.')).toBeInTheDocument();
    expect(screen.getByTestId('feedback-preview-description').textContent).toBe(SERVER_DESCRIPTION);
    fireEvent.click(screen.getByRole('button', { name: 'Als Datei speichern' }));
    expect(saveReportFile).toHaveBeenCalledWith(p, undefined);
    expect(screen.getByRole('button', { name: 'Erneut senden' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zurück' })).toBeInTheDocument();
    // no automatic retry
    expect(sendReport).toHaveBeenCalledTimes(1);
  });

  it('back from preview keeps the input', async () => {
    const user = userEvent.setup();
    previewReport.mockResolvedValue(preview());
    render(<FeedbackDialog onClose={vi.fn()} />);
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    fireEvent.click(screen.getByRole('button', { name: 'Zurück' }));
    expect(screen.getByLabelText('Titel')).toHaveValue('Es hakt');
    expect(screen.getByLabelText('Beschreibung')).toHaveValue('Beim Stempeln passiert X');
  });

  it('employee sees no log checkbox', () => {
    render(<FeedbackDialog onClose={vi.fn()} />);
    expect(screen.queryByLabelText('Protokollauszug anhängen (bereinigt)')).not.toBeInTheDocument();
  });

  it('admin sees log checkbox checked by default', () => {
    authState.user = { id: 'a1', role: 'admin' };
    render(<FeedbackDialog onClose={vi.fn()} />);
    expect(screen.getByLabelText('Protokollauszug anhängen (bereinigt)')).toBeChecked();
  });

  it('admin from error-log origin sends kind crash with error_log_id and include_log', async () => {
    authState.user = { id: 'a1', role: 'admin' };
    const user = userEvent.setup();
    const p = preview();
    previewReport.mockResolvedValue(p);
    sendReport.mockResolvedValue({ status: 'received', ref: 'PZ-1', id: 'r', board_url: p.board_url });
    render(
      <FeedbackDialog onClose={vi.fn()} origin="error-log" errorLogId="el-1" initialTitle="Serverfehler 500" />,
    );
    expect(screen.queryByLabelText('Fehler')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Feedback')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Titel')).toHaveValue('Serverfehler 500');
    expect(screen.getByLabelText('Protokollauszug anhängen (bereinigt)')).toBeChecked();
    await user.type(screen.getByLabelText('Beschreibung'), 'Beim Export');
    await user.click(screen.getByRole('button', { name: 'Vorschau' }));
    await screen.findByTestId('feedback-preview-description');
    expect(previewReport).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'crash', error_log_id: 'el-1', include_log: true }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    await waitFor(() => expect(sendReport).toHaveBeenCalled());
    expect(sendReport.mock.calls[0][1]).toMatchObject({ kind: 'crash' });
  });

  it('legacy preview shows contact e-mail note', async () => {
    const user = userEvent.setup();
    previewReport.mockResolvedValue(preview({ transport: 'legacy', credential_note: null, contact_email_dropped: true, truncated: true }));
    render(<FeedbackDialog onClose={vi.fn()} />);
    await user.type(screen.getByLabelText('Rückmelde-E-Mail (optional)'), 'praxis@example.invalid');
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    expect(
      screen.getByText('Hinweis: Die Rückmelde-E-Mail wird über den bisherigen Meldeweg nicht übertragen.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Protokollauszug gekürzt.')).toBeInTheDocument();
    expect(previewReport.mock.calls[0][0]).toMatchObject({ contact_email: 'praxis@example.invalid' });
  });

  it('rejects screenshot over 5 MB before preview', async () => {
    const user = userEvent.setup();
    render(<FeedbackDialog onClose={vi.fn()} />);
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'gross.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Bildschirmfoto anhängen (optional)'), { target: { files: [big] } });
    expect(screen.getByText('Nur PNG- oder JPEG-Bilder bis 5 MB.')).toBeInTheDocument();
    await fillAndPreview(user);
    expect(previewReport).not.toHaveBeenCalled();
  });

  it('passes an accepted screenshot to send and shows a thumbnail', async () => {
    const user = userEvent.setup();
    const p = preview();
    previewReport.mockResolvedValue(p);
    sendReport.mockResolvedValue({ status: 'received', ref: 'PZ-2', id: 'r', board_url: p.board_url });
    render(<FeedbackDialog onClose={vi.fn()} />);
    const img = new File([new Uint8Array(10)], 'bild.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByLabelText('Bildschirmfoto anhängen (optional)'), { target: { files: [img] } });
    await fillAndPreview(user);
    await screen.findByTestId('feedback-preview-description');
    expect(screen.getByAltText('Bildschirmfoto-Vorschau')).toHaveAttribute('src', 'blob:thumb');
    fireEvent.click(screen.getByRole('button', { name: 'Senden' }));
    await waitFor(() => expect(sendReport).toHaveBeenCalled());
    expect(sendReport.mock.calls[0][2]).toBe(img);
  });
});
