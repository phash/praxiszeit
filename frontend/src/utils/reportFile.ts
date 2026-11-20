import type { FeedbackPreview } from '../api/feedback';
import { downloadBlob } from './downloadBlob';

/**
 * „Als Datei speichern“ (#557): die VORSCHAU als Textdatei, wenn das Senden
 * scheitert oder der Nutzer die Meldung selbst weitergeben will. Enthält nie
 * den Meldeschlüssel (der Server schickt ihn nie; Feldnamen mit
 * „credential“ werden zusätzlich verworfen).
 */
const TARGETS: Record<FeedbackPreview['transport'], string> = {
  'mrd-report-1': 'Ziel: POST https://report.mr-development.de/v1/reports (mrd-report-1)',
  legacy: 'Ziel: POST https://praxiszeit.mr-development.de/v1/bugs (bisheriger Meldeweg)',
};

const SKIPPED_FIELDS = new Set(['title', 'description']);

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function reportFileName(now: Date): string {
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `praxiszeit-meldung-${date}-${time}.txt`;
}

export function formatReportFile(preview: FeedbackPreview, now: Date, screenshotName?: string): string {
  const lines = [
    'PraxisZeit – Problemmeldung (nicht gesendet)',
    `Erstellt: ${now.toISOString()}`,
    TARGETS[preview.transport] ?? TARGETS['mrd-report-1'],
  ];
  const keys = Object.keys(preview.fields)
    .filter((k) => !SKIPPED_FIELDS.has(k) && !/credential/i.test(k))
    .sort();
  for (const key of keys) {
    lines.push(`${key}: ${preview.fields[key]}`);
  }
  if (screenshotName) {
    lines.push(`Anhang: ${screenshotName} (nicht in dieser Datei enthalten)`);
  }
  lines.push('', `Titel: ${preview.title}`, '', preview.description);
  return lines.join('\n');
}

export function saveReportFile(preview: FeedbackPreview, screenshotName?: string): void {
  const now = new Date();
  downloadBlob(formatReportFile(preview, now, screenshotName), reportFileName(now), 'text/plain;charset=utf-8');
}
