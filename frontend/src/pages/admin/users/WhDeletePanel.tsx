import { useEffect, useRef, useState } from 'react';
import apiClient from '../../../api/client';
import { useToast } from '../../../contexts/ToastContext';
import { getErrorMessage } from '../../../utils/errorMessage';
import { showResponseWarning } from '../../../utils/arbzgWarnings';
import ShorteningChoice from './ShorteningChoice';
import WhImpactBox from './WhImpactBox';
import type { WorkingHoursChange, WorkingHoursChangePreview } from './workingHoursTypes';
import {
  EMPTY_REASON, closedYearMessage, dayBefore, formatDate, reasonComplete, reasonPayload, savedMessage,
  type ReasonState, type ShorteningOption,
} from './workingHoursTexts';

interface WhDeletePanelProps {
  userId: string;
  change: WorkingHoursChange;
  onCancel: () => void;
  onDone: () => Promise<void> | void;
  // Gesamtreview 1.20 (Fund 14, Nachzug): feste Monatsarbeitszeit — die
  // Auswirkungs-Box nennt die Tageswerte dann geplante Anwesenheit.
  plannedPresence?: boolean;
}

const PREVIEW_FAILED = 'Auswirkungen konnten nicht geprüft werden';

/**
 * Spec 2026-10-08, 9.7/12.1/P13: Löschen einer Verlaufszeile mit Vorschau
 * (`delete-preview`, gleiche Auswirkungs-Box wie beim Anlegen). Verkürzt das
 * Löschen, ist der Standard die Rücksetzung auf den vorherigen Stand —
 * `reset_body` geht UNVERÄNDERT an den Anlege-Endpunkt, der Client baut den
 * Snapshot nie selbst nach. Verkürzt es nicht, bleibt es bei der einfachen
 * Bestätigung (dieses Panel).
 */
export default function WhDeletePanel({
  userId, change, onCancel, onDone, plannedPresence = false,
}: WhDeletePanelProps) {
  const toast = useToast();
  const base = `/admin/users/${userId}/working-hours-changes/${change.id}`;
  const panelRef = useRef<HTMLElement>(null);
  const [dp, setDp] = useState<WorkingHoursChangePreview | null>(null);
  const [dpError, setDpError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [option, setOption] = useState<ShorteningOption>('lossless');
  const [reason, setReason] = useState<ReasonState>(EMPTY_REASON);
  const [resetPreview, setResetPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Das Panel erscheint über der Verlaufszeile — Fokus (und auf dem Handy die
  // Ansicht) dorthin, statt auf dem Papierkorb stehen zu bleiben.
  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDp(null);
    setDpError(null);
    setOption('lossless');
    apiClient
      .post(`${base}/delete-preview`, {})
      .then((res) => {
        if (!cancelled) setDp(res.data);
      })
      .catch((error) => {
        if (!cancelled) setDpError(getErrorMessage(error, PREVIEW_FAILED));
      });
    return () => {
      cancelled = true;
    };
  }, [base, reloadToken]);

  const blocked = dp?.blocked_reason ?? null;
  const isShortening = !!dp && !blocked && !!dp.is_shortening;
  const resetBody = isShortening ? (dp?.reset_body ?? null) : null;
  const resetDate = typeof resetBody?.effective_from === 'string' ? resetBody.effective_from : null;
  const useReset = resetBody !== null && resetDate !== null && option === 'lossless';
  const needsReason = isShortening && !useReset;
  const closedText = isShortening ? closedYearMessage(dp?.shortening_closed_years) : null;
  // Effekt-Schlüssel als String (stabil über Renderläufe, sonst Anfragesturm).
  const resetKey = useReset ? JSON.stringify(resetBody) : null;

  // Spec 12.1: die Box zeigt für die Rücksetzung die Vorschau mit DEMSELBEN Body.
  useEffect(() => {
    setResetPreview(null);
    setResetError(null);
    if (!resetKey) {
      setResetLoading(false);
      return;
    }
    setResetLoading(true);
    let cancelled = false;
    apiClient
      .post(`/admin/users/${userId}/working-hours-changes/preview`, JSON.parse(resetKey))
      .then((res) => {
        if (!cancelled) setResetPreview(res.data);
      })
      .catch((error) => {
        if (!cancelled) setResetError(getErrorMessage(error, PREVIEW_FAILED));
      })
      .finally(() => {
        if (!cancelled) setResetLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, resetKey]);

  // Review Task 19 (Fund 4, Release-Review 1.17.0): ein gesperrter Knopf
  // braucht eine sichtbare Begründung — Laden, Fehler oder die Sperre der
  // Rücksetzungs-Vorschau (z. B. Verlauf inzwischen geändert, 11.4).
  const shown = useReset ? resetPreview : dp;
  const shownLoading = useReset && resetLoading;
  const shownError = useReset ? resetError : null;
  const shownBlocked = useReset ? (resetPreview?.blocked_reason ?? null) : null;
  const actionDisabled = busy || !dp || !!blocked
    || (useReset && (resetLoading || !resetPreview || !!resetPreview.blocked_reason))
    || (needsReason && (!!closedText || !reasonComplete(reason)));

  // „Erneut prüfen" lädt die `delete-preview` neu — sie liefert einen frischen
  // `reset_body`, dessen Vorschau danach von selbst neu läuft.
  const retryButton = (
    <button
      type="button"
      onClick={() => setReloadToken((t) => t + 1)}
      className="mt-1 text-sm font-medium text-red-700 underline hover:no-underline"
    >
      Erneut prüfen
    </button>
  );

  const runReset = async () => {
    setBusy(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, resetBody);
      toast.success(savedMessage(res.data ?? {}));
      showResponseWarning(toast, res.data);
      await onDone();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Fehler beim Zurücksetzen'));
      // 11.4: 409 — der vorherige Stand hat sich geändert → delete-preview neu laden.
      if ((error as { response?: { status?: number } })?.response?.status === 409) {
        setReloadToken((t) => t + 1);
      }
    } finally {
      setBusy(false);
    }
  };

  const runDelete = async () => {
    setBusy(true);
    try {
      const res = needsReason
        ? await apiClient.delete(base, { data: reasonPayload(reason) })
        : await apiClient.delete(base);
      // I3: 200 + Zählung/Warnung oder 204 ohne Body (axios: data === '').
      const data = res?.data && typeof res.data === 'object' ? res.data : {};
      toast.success(savedMessage(data, 'Gelöscht'));
      showResponseWarning(toast, data);
      await onDone();
    } catch (error: unknown) {
      // I4: der Grund kommt vom Backend — nicht hinter einer pauschalen Meldung verschlucken.
      toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
    } finally {
      setBusy(false);
    }
  };

  // Review Task 20: Escape bricht nur das Panel ab. Der äußere Dialog schließt
  // bei Escape über focus-trap, das dafür am `document` lauscht (Bubble-Phase);
  // Reacts stopPropagation hält das Ereignis schon am Wurzelcontainer an. Ohne
  // das gingen mit dem ganzen Dialog auch Formular und Grund verloren — der
  // frühere ConfirmDialog hatte dafür eine eigene Fokusfalle.
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Escape') return;
    e.stopPropagation();
    onCancel();
  };

  return (
    <section
      ref={panelRef}
      tabIndex={-1}
      role="alertdialog"
      aria-labelledby="wh-delete-title"
      onKeyDown={handleKeyDown}
      className="mb-4 rounded-lg border border-red-300 bg-white p-3 sm:p-4 text-sm space-y-2 min-w-0 break-words focus:outline-none focus:ring-2 focus:ring-red-300"
    >
      <h4 id="wh-delete-title" className="font-semibold text-gray-900">
        {`Arbeitszeit-Änderung ab ${formatDate(change.effective_from)} löschen`}
      </h4>
      {dpError ? (
        <div>
          <p className="font-medium text-red-700">{dpError}</p>
          {retryButton}
        </div>
      ) : !dp ? (
        <p className="text-gray-600">Prüfe Auswirkungen…</p>
      ) : blocked ? (
        <p className="font-medium text-red-700">{blocked}</p>
      ) : (
        <>
          {isShortening && (
            <ShorteningChoice
              preview={dp}
              losslessText={resetDate ? `Ab ${formatDate(resetDate)} auf den vorherigen Stand zurücksetzen` : null}
              losslessNote={resetDate
                ? `Die Änderung ab ${formatDate(change.effective_from)} bleibt bis ${formatDate(dayBefore(resetDate))} `
                  + `wirksam und im Verlauf stehen; ab ${formatDate(resetDate)} gilt wieder der vorherige Stand.`
                : null}
              retroText="Rückwirkend löschen mit Neuberechnung"
              option={useReset ? 'lossless' : 'retro'}
              onOptionChange={setOption}
              closedText={closedText}
              reason={reason}
              onReasonChange={setReason}
              idPrefix="wh-del"
            />
          )}
          <div
            aria-live="polite"
            className={`rounded-lg border p-3 min-w-0 ${
              shownError || shownBlocked ? 'border-red-300 bg-red-50' : 'border-amber-300 bg-amber-50'
            }`}
          >
            {shownLoading ? (
              <p className="text-gray-600">Prüfe Auswirkungen…</p>
            ) : shownError ? (
              <>
                <p className="font-medium text-red-700">{shownError}</p>
                {retryButton}
              </>
            ) : shown ? (
              <>
                <p className="font-semibold text-amber-900">
                  {`${useReset ? 'Auswirkung der Rücksetzung' : 'Auswirkung des Löschens'}: `
                    + `${formatDate(shown.period_start)} – ${formatDate(shown.period_end)}`}
                </p>
                {shownBlocked ? (
                  <>
                    <p className="mt-1 font-medium text-red-700">{shownBlocked}</p>
                    {retryButton}
                  </>
                ) : (
                  <>
                    <WhImpactBox preview={shown} plannedPresence={plannedPresence} />
                    {shown.closed_year_warning && (
                      <p className="mt-1 font-medium text-amber-900">{shown.closed_year_warning}</p>
                    )}
                  </>
                )}
              </>
            ) : null}
          </div>
        </>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          Abbrechen
        </button>
        {useReset ? (
          <button
            type="button"
            disabled={actionDisabled}
            onClick={runReset}
            className="px-3 py-1.5 rounded-lg bg-primary text-white hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Zurücksetzen
          </button>
        ) : (
          <button
            type="button"
            disabled={actionDisabled}
            onClick={runDelete}
            className="px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Löschen
          </button>
        )}
      </div>
    </section>
  );
}
