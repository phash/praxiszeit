import { useState } from 'react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from './ConfirmDialog';
import { getErrorMessage } from '../utils/errorMessage';
import { showArbzgWarnings } from '../utils/arbzgWarnings';
import { notCreditedMinutes, type CreditEntry } from '../utils/workBlocks';

/**
 * Spec 2026-10-08, 13.3 „Anerkennen": die gesamte gestempelte Zeit eines
 * Eintrags anrechnen — dauerhaft, protokolliert. Eine Komponente für
 * Admin-Dashboard und Monatsjournal (Admin-Ansicht).
 */
export const AUTO_CLOSED_HINT = 'Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen.';

export function creditConfirmText(rawSpan: string): string {
  return (
    `Die gesamte gestempelte Zeit (${rawSpan}) wird angerechnet. Sie bleibt angerechnet — auch bei `
    + 'späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende können den '
    + 'Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit gearbeitet, den '
    + 'Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert.'
  );
}

export interface CreditButtonEntry extends CreditEntry {
  id: string;
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

interface CreditOverrideButtonProps {
  entry: CreditButtonEntry;
  onDone: () => void;
  className?: string;
}

export default function CreditOverrideButton({ entry, onDone, className }: CreditOverrideButtonProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [busy, setBusy] = useState(false);

  // Ohne nicht angerechnete Zeit, bei bereits anerkannten und bei offenen
  // Einträgen gibt es nichts anzuerkennen (der Server lehnt Offene mit 400 ab).
  const notCredited = entry.not_credited_minutes ?? notCreditedMinutes(entry);
  if (entry.credit_override || !entry.end_time || notCredited <= 0) return null;

  const hhmm = (t?: string | null) => (t ? t.substring(0, 5) : '');
  // Dieselbe Spanne, die der Server anrechnet (13.3 Schritt 3: raw_* or start/end).
  const rawSpan = `${hhmm(entry.raw_start_time ?? entry.start_time)}–${hhmm(entry.raw_end_time ?? entry.end_time)}`;

  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await apiClient.post(`/admin/time-entries/${entry.id}/credit-override`);
      toast.success('Zeit anerkannt');
      // P4: §3/§4/48 h und Anwesenheit kommen nur als weiche Warnung zurück.
      showArbzgWarnings(toast, res.data?.warnings);
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Anerkennen fehlgeschlagen'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <button
        type="button"
        // P18: ein automatisch geschlossener Eintrag trägt kein echtes Ende —
        // erst das tatsächliche Ende eintragen, dann anerkennen.
        disabled={!!entry.auto_closed || busy}
        title={entry.auto_closed ? AUTO_CLOSED_HINT : 'Nicht angerechnete Zeit anerkennen'}
        onClick={() => confirm({
          title: 'Nicht angerechnete Zeit anerkennen',
          message: creditConfirmText(rawSpan),
          confirmLabel: 'Zeit anerkennen',
          variant: 'warning',
          onConfirm: () => { void run(); },
        })}
        className={className ?? 'text-xs px-2 py-0.5 rounded-sm border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-50 disabled:cursor-not-allowed'}
      >
        Anerkennen
      </button>
      {entry.auto_closed && <span className="block text-xs text-gray-500">{AUTO_CLOSED_HINT}</span>}
    </>
  );
}
