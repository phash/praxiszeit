import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('./client', () => ({ default: { post } }));

import { previewReport, sendReport, type FeedbackPreview } from './feedback';

const preview: FeedbackPreview = {
  transport: 'mrd-report-1',
  title: 'T (bereinigt)',
  description: 'D (bereinigt)',
  fields: { error_fingerprint: 'abc123', product: 'praxiszeit' },
  credential_note: null,
  log_line_count: 0,
  truncated: false,
  board_url: 'https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit',
  contact_email_dropped: false,
};

beforeEach(() => post.mockReset());

describe('api/feedback', () => {
  it('previewReport posts JSON to /feedback/preview', async () => {
    post.mockResolvedValue({ data: preview });
    const req = { kind: 'bug' as const, title: 'T', text: 'x' };
    await expect(previewReport(req)).resolves.toBe(preview);
    expect(post).toHaveBeenCalledWith('/feedback/preview', req);
  });

  it('sendReport sends the previewed title/description as multipart payload', async () => {
    post.mockResolvedValue({ data: { status: 'received', ref: 'PZ-1', id: 'r', board_url: preview.board_url } });
    const shot = new File([new Uint8Array(3)], 'a.png', { type: 'image/png' });
    await sendReport(preview, { kind: 'crash', title: 'roh', text: 'roh', severity: 'high', contact_email: 'a@example.invalid' }, shot);
    const [url, form, config] = post.mock.calls[0];
    expect(url).toBe('/feedback/send');
    expect(config.timeout).toBe(30000);
    expect(JSON.parse((form as FormData).get('payload') as string)).toEqual({
      kind: 'crash',
      title: 'T (bereinigt)',
      description: 'D (bereinigt)',
      severity: 'high',
      contact_email: 'a@example.invalid',
      error_fingerprint: 'abc123',
    });
    expect((form as FormData).get('attachment')).toBeInstanceOf(File);
  });
});
