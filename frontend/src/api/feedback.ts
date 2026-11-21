import apiClient from './client';

/**
 * Problemmeldung (#136, #557 — Protokoll mrd-report-1).
 *
 * Ablauf: `previewReport` lässt den Server Titel und Beschreibung fertig
 * zusammensetzen und bereinigen; `sendReport` schickt GENAU diese Vorschau
 * (Titel + Beschreibung unverändert) zurück — „Vorschau = gesendet“.
 */
export type ReportKind = 'bug' | 'feedback' | 'crash';
export type Severity = 'low' | 'medium' | 'high' | 'critical';

export interface ServerErrorHint {
  status: number;
  method: string;
  path: string;
}

export interface FeedbackPreviewRequest {
  kind: ReportKind;
  title: string;
  text: string;
  severity?: Severity;
  contact_email?: string;
  include_log?: boolean;
  error_log_id?: string;
  server_error?: ServerErrorHint;
}

export interface FeedbackPreview {
  transport: 'mrd-report-1' | 'legacy';
  title: string;
  description: string;
  fields: Record<string, string>;
  credential_note: string | null;
  /** Hinweis, dass die Lizenzkennung beim Senden serverseitig ergänzt wird (nie ein Wert). */
  license_note: string | null;
  log_line_count: number;
  truncated: boolean;
  board_url: string;
  contact_email_dropped: boolean;
}

export interface FeedbackSendResult {
  status: 'received';
  ref: string | null;
  id: string | null;
  board_url: string;
}

export async function previewReport(req: FeedbackPreviewRequest): Promise<FeedbackPreview> {
  const res = await apiClient.post<FeedbackPreview>('/feedback/preview', req);
  return res.data;
}

export async function sendReport(
  preview: FeedbackPreview,
  req: FeedbackPreviewRequest,
  screenshot?: File,
): Promise<FeedbackSendResult> {
  const payload = {
    kind: req.kind,
    title: preview.title,
    description: preview.description,
    severity: req.severity,
    contact_email: req.contact_email,
    error_fingerprint: preview.fields.error_fingerprint,
  };
  const form = new FormData();
  form.append('payload', JSON.stringify(payload));
  if (screenshot) form.append('attachment', screenshot, screenshot.name);
  const res = await apiClient.post<FeedbackSendResult>('/feedback/send', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  });
  return res.data;
}
