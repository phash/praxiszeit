import { describe, expect, it, vi } from 'vitest';
import type { FeedbackPreview } from '../api/feedback';

const { downloadBlob } = vi.hoisted(() => ({ downloadBlob: vi.fn() }));
vi.mock('./downloadBlob', () => ({ downloadBlob }));

import { formatReportFile, reportFileName, saveReportFile } from './reportFile';

function preview(overrides: Partial<FeedbackPreview> = {}): FeedbackPreview {
  return {
    transport: 'mrd-report-1',
    title: 'Es hakt',
    description: 'Zeile 1\nZeile 2',
    fields: {
      product: 'praxiszeit',
      app_version: '1.24.3',
      title: 'Es hakt',
      description: 'Zeile 1\nZeile 2',
      kind: 'bug',
    },
    credential_note: 'mrk_praxiszeit_… (nicht angezeigt)',
    license_note: null,
    log_line_count: 0,
    truncated: false,
    board_url: 'https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit',
    contact_email_dropped: false,
    ...overrides,
  };
}

describe('reportFile', () => {
  it('formats header, fields, title and description', () => {
    const now = new Date('2026-11-20T09:05:00.000Z');
    const text = formatReportFile(preview(), now, { type: 'image/png' });
    expect(text.split('\n')).toEqual([
      'PraxisZeit – Problemmeldung (nicht gesendet)',
      `Erstellt: ${now.toISOString()}`,
      'Ziel: POST https://report.mr-development.de/v1/reports (mrd-report-1)',
      'app_version: 1.24.3',
      'kind: bug',
      'product: praxiszeit',
      'Anhang: screenshot.png (nicht in dieser Datei enthalten)',
      '',
      'Titel: Es hakt',
      '',
      'Zeile 1',
      'Zeile 2',
    ]);
  });

  it('uses the legacy target line for the legacy transport', () => {
    const text = formatReportFile(preview({ transport: 'legacy' }), new Date());
    expect(text).toContain('Ziel: POST https://praxiszeit.mr-development.de/v1/bugs (bisheriger Meldeweg)');
    expect(text).not.toContain('Anhang:');
  });

  it('never contains credential or mrk_', () => {
    const p = preview({ fields: { product: 'praxiszeit', credential: 'mrk_praxiszeit_secret' } });
    const text = formatReportFile(p, new Date());
    expect(text).not.toMatch(/credential/i);
    expect(text).not.toContain('mrk_');
  });

  it('file name pattern', () => {
    const now = new Date(2026, 10, 20, 7, 3); // local time
    expect(reportFileName(now)).toBe('praxiszeit-meldung-20261120-0703.txt');
  });

  it('saveReportFile downloads text/plain with the generated name', () => {
    saveReportFile(preview());
    expect(downloadBlob).toHaveBeenCalledTimes(1);
    const [data, name, mime] = downloadBlob.mock.calls[0];
    expect(data).toContain('Titel: Es hakt');
    expect(name).toMatch(/^praxiszeit-meldung-\d{8}-\d{4}\.txt$/);
    expect(mime).toBe('text/plain;charset=utf-8');
  });

  it('writes a neutral attachment name, never the local file name', () => {
    const f = new File([new Uint8Array(1)], 'Krankmeldung_Mueller_Petra.jpg', { type: 'image/jpeg' });
    const text = formatReportFile(preview(), new Date(), f);
    expect(text).toContain('Anhang: screenshot.jpg (nicht in dieser Datei enthalten)');
    expect(text).not.toContain('Krankmeldung');
  });

  it('writes the license note but never a license value', () => {
    const note = 'Lizenzkennung der Praxis (wird beim Senden ergänzt, nicht angezeigt)';
    const p = preview({ license_note: note, fields: { product: 'praxiszeit', license_id: 'CUST-4711' } });
    const text = formatReportFile(p, new Date());
    expect(text).toContain(note);
    expect(text).not.toContain('CUST-4711');
    expect(text).not.toContain('license_id');
  });
});
