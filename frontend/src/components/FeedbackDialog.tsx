import { useEffect, useRef, useState } from 'react';
import DialogFocusTrap from './DialogFocusTrap';
import { Bug, X } from 'lucide-react';
import {
  previewReport,
  sendReport,
  type FeedbackPreview,
  type FeedbackPreviewRequest,
  type FeedbackSendResult,
  type ReportKind,
  type ServerErrorHint,
  type Severity,
} from '../api/feedback';
import { saveReportFile } from '../utils/reportFile';
import { useAuthStore } from '../stores/authStore';
import { getErrorMessage } from '../utils/errorMessage';

interface FeedbackDialogProps {
  onClose: () => void;
  /** Herkunft: Hilfe-Bereich (alle), Fehler-Toast bzw. Fehler-Monitoring (Admin, Art „crash“). */
  origin?: 'help' | 'toast' | 'error-log';
  errorLogId?: string;
  serverError?: ServerErrorHint;
  initialTitle?: string;
}

const SEVERITY_OPTIONS: { value: Severity; label: string }[] = [
  { value: 'low', label: 'Niedrig' },
  { value: 'medium', label: 'Mittel' },
  { value: 'high', label: 'Hoch' },
  { value: 'critical', label: 'Kritisch' },
];

const SCREENSHOT_TYPES = new Set(['image/png', 'image/jpeg']);
const SCREENSHOT_MAX_BYTES = 5 * 1024 * 1024;
const SCREENSHOT_ERROR = 'Nur PNG- oder JPEG-Bilder bis 5 MB.';

type Step = 'form' | 'preview' | 'done' | 'failed';

const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary';
const primaryButton =
  'bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed';
const secondaryButton =
  'bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed';

/**
 * Problemmeldung (#136, #557 — mrd-report-1). Ablauf: Formular → Vorschau
 * (vom Server bereinigt und fertig zusammengesetzt) → Senden genau dieser
 * Vorschau → Ergebnis mit Vorgangsnummer. Scheitert das Senden, bleibt alles
 * stehen und die Vorschau lässt sich als Datei speichern (kein automatischer
 * Neuversuch).
 */
export default function FeedbackDialog({
  onClose,
  origin = 'help',
  errorLogId,
  serverError,
  initialTitle,
}: FeedbackDialogProps) {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const programProposed = origin === 'toast' || origin === 'error-log';

  const [kind, setKind] = useState<ReportKind>(programProposed ? 'crash' : 'bug');
  const [title, setTitle] = useState(initialTitle ?? '');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<Severity>('medium');
  const [contactEmail, setContactEmail] = useState('');
  const [includeLog, setIncludeLog] = useState(true);
  const [screenshot, setScreenshot] = useState<File | undefined>(undefined);
  const [screenshotError, setScreenshotError] = useState<string | null>(null);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  const [step, setStep] = useState<Step>('form');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [preview, setPreview] = useState<FeedbackPreview | null>(null);
  const [request, setRequest] = useState<FeedbackPreviewRequest | null>(null);
  const [result, setResult] = useState<FeedbackSendResult | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  // Doppelklick-Schutz: `busy` greift erst nach dem nächsten Rendern, die Ref sofort.
  const inFlight = useRef(false);
  // Vorschau/Fehlschlag: Hintergrundklick und Escape schließen nicht (Eingabe nie verwerfen).
  // Ref, weil focus-trap seine Optionen beim Aktivieren übernimmt.
  const lockedOpen = step === 'preview' || step === 'failed';
  const lockedOpenRef = useRef(lockedOpen);
  lockedOpenRef.current = lockedOpen;

  useEffect(() => {
    if (!screenshot) {
      setThumbUrl(null);
      return;
    }
    const url = URL.createObjectURL(screenshot);
    setThumbUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [screenshot]);

  const canPreview =
    title.trim().length > 0 && description.trim().length > 0 && !screenshotError && !busy;

  const handleScreenshot = (file: File | undefined) => {
    if (!file) {
      setScreenshot(undefined);
      setScreenshotError(null);
      return;
    }
    if (!SCREENSHOT_TYPES.has(file.type) || file.size > SCREENSHOT_MAX_BYTES) {
      setScreenshot(undefined);
      setScreenshotError(SCREENSHOT_ERROR);
      return;
    }
    setScreenshot(file);
    setScreenshotError(null);
  };

  const buildRequest = (): FeedbackPreviewRequest => {
    const req: FeedbackPreviewRequest = {
      kind,
      title: title.trim(),
      text: description.trim(),
      severity,
    };
    const email = contactEmail.trim();
    if (email) req.contact_email = email;
    if (isAdmin && includeLog) req.include_log = true;
    if (errorLogId) req.error_log_id = errorLogId;
    if (serverError) req.server_error = serverError;
    return req;
  };

  const handlePreview = async () => {
    if (!canPreview || inFlight.current) return;
    const req = buildRequest();
    inFlight.current = true;
    setBusy(true);
    setFormError(null);
    try {
      const p = await previewReport(req);
      setRequest(req);
      setPreview(p);
      setStep('preview');
    } catch (error: unknown) {
      setFormError(getErrorMessage(error, 'Vorschau konnte nicht erstellt werden.'));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const handleSend = async () => {
    if (!preview || !request || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setSendError(null);
    try {
      const r = await sendReport(preview, request, screenshot);
      setResult(r);
      setStep('done');
    } catch (error: unknown) {
      setSendError(getErrorMessage(error, 'Die Meldung konnte nicht gesendet werden.'));
      setStep('failed');
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const handleSave = () => {
    if (preview) saveReportFile(preview, screenshot?.name);
  };

  const backToForm = () => {
    setStep('form');
    setSendError(null);
  };

  const fieldEntries = preview
    ? Object.entries(preview.fields)
        .filter(([k]) => k !== 'title' && k !== 'description' && !/credential/i.test(k))
        .sort(([a], [b]) => a.localeCompare(b))
    : [];

  return (
    <div
      data-testid="feedback-backdrop"
      className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-[60]"
      onClick={() => {
        if (!lockedOpenRef.current) onClose();
      }}
    >
      <DialogFocusTrap
        focusTrapOptions={{
          allowOutsideClick: true,
          escapeDeactivates: () => !lockedOpenRef.current,
          onDeactivate: onClose,
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="feedback-dialog-title"
          className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Bug size={20} className="text-primary" />
              <h3 id="feedback-dialog-title" className="text-xl font-semibold text-gray-900">
                Problem melden
              </h3>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition"
              aria-label="Dialog schließen"
            >
              <X size={24} />
            </button>
          </div>

          {step === 'form' && (
            <>
              {!programProposed && (
                <fieldset className="mb-4">
                  <legend className="sr-only">Art der Meldung</legend>
                  <div className="flex space-x-6">
                    <label className="flex items-center space-x-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="fb-kind"
                        value="bug"
                        checked={kind === 'bug'}
                        onChange={() => setKind('bug')}
                      />
                      <span>Fehler</span>
                    </label>
                    <label className="flex items-center space-x-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="fb-kind"
                        value="feedback"
                        checked={kind === 'feedback'}
                        onChange={() => setKind('feedback')}
                      />
                      <span>Feedback</span>
                    </label>
                  </div>
                </fieldset>
              )}

              <div className="mb-4">
                <label htmlFor="fb-title" className="block text-sm font-medium text-gray-700 mb-1">
                  Titel
                </label>
                <input
                  id="fb-title"
                  type="text"
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                  className={inputClass}
                  autoFocus
                />
                <p className="text-xs text-gray-400 mt-1 text-right">{title.length}/200</p>
              </div>

              <div className="mb-4">
                <label htmlFor="fb-desc" className="block text-sm font-medium text-gray-700 mb-1">
                  Beschreibung
                </label>
                <textarea
                  id="fb-desc"
                  value={description}
                  rows={5}
                  maxLength={4000}
                  onChange={(e) => setDescription(e.target.value)}
                  className={`${inputClass} resize-y`}
                />
                <p className="text-xs text-gray-400 mt-1 text-right">{description.length}/4000</p>
              </div>

              <div className="mb-4">
                <label htmlFor="fb-sev" className="block text-sm font-medium text-gray-700 mb-1">
                  Schweregrad
                </label>
                <select
                  id="fb-sev"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value as Severity)}
                  className={`${inputClass} bg-white`}
                >
                  {SEVERITY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="mb-4">
                <label htmlFor="fb-email" className="block text-sm font-medium text-gray-700 mb-1">
                  Rückmelde-E-Mail (optional)
                </label>
                <input
                  id="fb-email"
                  type="email"
                  value={contactEmail}
                  maxLength={254}
                  onChange={(e) => setContactEmail(e.target.value)}
                  className={inputClass}
                />
              </div>

              <div className="mb-4">
                <label htmlFor="fb-shot" className="block text-sm font-medium text-gray-700 mb-1">
                  Bildschirmfoto anhängen (optional)
                </label>
                <input
                  id="fb-shot"
                  type="file"
                  accept="image/png,image/jpeg"
                  onChange={(e) => handleScreenshot(e.target.files?.[0])}
                  className="w-full text-sm text-gray-700"
                />
                {screenshotError && (
                  <p role="alert" className="text-sm text-red-600 mt-1">
                    {screenshotError}
                  </p>
                )}
              </div>

              {isAdmin && (
                <label className="flex items-center space-x-2 text-sm text-gray-700 mb-4">
                  <input
                    type="checkbox"
                    checked={includeLog}
                    onChange={(e) => setIncludeLog(e.target.checked)}
                  />
                  <span>Protokollauszug anhängen (bereinigt)</span>
                </label>
              )}

              <p className="text-sm text-amber-700 bg-amber-50 rounded-lg p-3 mb-4">
                Bitte keine Namen von Mitarbeitenden oder Notizen aus Zeiteinträgen eintragen.
              </p>

              <p className="text-xs text-gray-400 mb-4">
                Version {__APP_VERSION__} · Vor dem Senden sehen Sie genau, was übertragen wird.
              </p>

              {formError && (
                <p role="alert" className="text-sm text-red-600 mb-3">
                  {formError}
                </p>
              )}

              <div className="flex justify-end space-x-2">
                <button onClick={onClose} className={secondaryButton}>
                  Abbrechen
                </button>
                <button onClick={handlePreview} disabled={!canPreview} className={primaryButton}>
                  Vorschau
                </button>
              </div>
            </>
          )}

          {(step === 'preview' || step === 'failed') && preview && (
            <>
              {step === 'failed' && (
                <div role="alert" className="bg-red-50 text-red-700 rounded-lg p-3 mb-4 text-sm">
                  <p className="font-semibold">Senden fehlgeschlagen – als Datei speichern?</p>
                  {sendError && <p className="mt-1">{sendError}</p>}
                </div>
              )}

              <p className="text-sm font-medium text-gray-700 mb-1">Titel</p>
              <p className="text-sm text-gray-900 mb-3 break-words">{preview.title}</p>

              <p className="text-sm font-medium text-gray-700 mb-1">Beschreibung</p>
              <pre
                data-testid="feedback-preview-description"
                className="text-xs text-gray-800 bg-gray-50 border border-gray-200 rounded-lg p-3 mb-3 max-h-64 overflow-auto whitespace-pre-wrap break-words"
              >
                {preview.description}
              </pre>

              {fieldEntries.length > 0 && (
                <dl className="text-xs text-gray-600 mb-3 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
                  {fieldEntries.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="font-mono">{k}</dt>
                      <dd className="break-all">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {preview.credential_note && (
                <p className="text-xs text-gray-600 mb-2">{preview.credential_note}</p>
              )}
              {preview.contact_email_dropped && (
                <p className="text-xs text-amber-700 mb-2">
                  Hinweis: Die Rückmelde-E-Mail wird über den bisherigen Meldeweg nicht übertragen.
                </p>
              )}
              {preview.truncated && (
                <p className="text-xs text-amber-700 mb-2">Protokollauszug gekürzt.</p>
              )}
              {thumbUrl && (
                <img
                  src={thumbUrl}
                  alt="Bildschirmfoto-Vorschau"
                  className="max-h-32 rounded border border-gray-200 mb-3"
                />
              )}

              <div className="flex flex-wrap justify-end gap-2 mt-4">
                <button onClick={backToForm} disabled={busy} className={secondaryButton}>
                  Zurück
                </button>
                <button onClick={handleSave} className={secondaryButton}>
                  Als Datei speichern
                </button>
                <button onClick={handleSend} disabled={busy} className={primaryButton}>
                  {busy ? 'Wird gesendet …' : step === 'failed' ? 'Erneut senden' : 'Senden'}
                </button>
              </div>
            </>
          )}

          {step === 'done' && result && (
            <>
              <p className="text-sm text-gray-900 mb-3">
                Danke! Ihre Meldung ist eingegangen: {result.ref ?? result.id ?? '–'}.
              </p>
              <a
                href={result.board_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-primary underline"
              >
                Bekannte Probleme ansehen
              </a>
              <div className="flex justify-end mt-4">
                <button onClick={onClose} className={primaryButton}>
                  Schließen
                </button>
              </div>
            </>
          )}
        </div>
      </DialogFocusTrap>
    </div>
  );
}
