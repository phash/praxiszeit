import { useEffect, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { ShieldCheck } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';

/**
 * #537 (A2-12): Prüfung des Änderungsprotokolls. Jede Protokollzeile trägt
 * eine Prüfsumme, und die Zeilen sind zu einer Kette versiegelt — eine
 * veränderte oder entfernte Zeile fällt auf. Bisher gab es dafür nur einen
 * Endpunkt, den niemand aufrief; jetzt prüft das System jede Nacht selbst,
 * und hier steht das Ergebnis (plus ein Knopf für die Prüfung sofort).
 */
interface LastCheck {
  checked_at: string;
  intact: boolean;
  checked: number;
  tampered: number;
  missing_links: number;
  head_ok?: boolean;
}

export interface IntegrityResult {
  checked: number;
  tampered: number;
  missing_links: number;
  broken_links: number;
  head_ok: boolean;
  head_problem?: string | null;
  reanchored?: number;
  legacy_unhashed: number;
  legacy_entry_deleted: number;
  intact: boolean;
}

function formatWhen(iso: string): string {
  const d = parseISO(iso);
  return isNaN(d.getTime()) ? iso : format(d, 'dd.MM.yyyy HH:mm');
}

/** Ergebnis in einem Satz — exportiert für den Test. */
export function integritySummary(r: IntegrityResult): string {
  if (r.intact) {
    const legacy = r.legacy_unhashed + r.legacy_entry_deleted;
    return `In Ordnung: ${r.checked} Zeilen geprüft, keine Veränderung.`
      + (legacy > 0 ? ` ${legacy} ältere Zeilen (Altbestand) ohne prüfbare Prüfsumme.` : '')
      + ((r.reanchored ?? 0) > 0 ? ' Das Kettenende wurde schon einmal neu gesetzt (siehe Protokoll).' : '');
  }
  const parts = [];
  if (r.tampered > 0) parts.push(`${r.tampered} veränderte Zeile(n)`);
  if (r.missing_links > 0) parts.push(`${r.missing_links} fehlende Zeile(n)`);
  if (r.broken_links > 0) parts.push(`${r.broken_links} gebrochene Verknüpfung(en)`);
  if (!r.head_ok) parts.push(r.head_problem ? `Kettenende ${r.head_problem}` : 'Kettenende passt nicht');
  return `Abweichung gefunden: ${parts.join(', ')} — von ${r.checked} geprüften Zeilen.`;
}

export default function AuditIntegrityCard() {
  const toast = useToast();
  const [last, setLast] = useState<LastCheck | null>(null);
  const [result, setResult] = useState<IntegrityResult | null>(null);
  const [running, setRunning] = useState(false);
  const [reanchorOpen, setReanchorOpen] = useState(false);
  const [reason, setReason] = useState('');

  // Einmal beim Öffnen — ohne `toast` in den Abhängigkeiten (instabile Referenz).
  useEffect(() => {
    apiClient
      .get('/admin/audit/integrity-status')
      .then((res) => setLast(res.data?.last_check ?? null))
      .catch(() => setLast(null));
  }, []);

  const runCheck = async () => {
    setRunning(true);
    try {
      const res = await apiClient.post('/admin/audit/verify-integrity');
      setResult(res.data);
      if (res.data?.last_check) setLast(res.data.last_check);
    } catch {
      toast.error('Die Prüfung konnte nicht ausgeführt werden');
    } finally {
      setRunning(false);
    }
  };

  const reanchor = async () => {
    setRunning(true);
    try {
      const res = await apiClient.post('/admin/audit/reanchor', { reason: reason.trim() });
      setResult(res.data);
      if (res.data?.last_check) setLast(res.data.last_check);
      setReanchorOpen(false);
      setReason('');
      toast.success('Kettenende neu gesetzt — der Vorgang steht im Änderungsprotokoll');
    } catch {
      toast.error('Das Kettenende konnte nicht neu gesetzt werden');
    } finally {
      setRunning(false);
    }
  };

  const status = result ? result.intact : last?.intact;
  // Kettenende fehlt/ungültig: Versiegeln und Löschen sind gesperrt, bis hier
  // jemand bewusst (mit Grund) neu setzt.
  const headBroken = result ? result.head_ok === false : last?.head_ok === false;

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden mt-8">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-primary" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Prüfung des Änderungsprotokolls</h2>
            <p className="text-xs text-gray-500">
              Erkennt veränderte und entfernte Protokollzeilen. Läuft jede Nacht automatisch.
            </p>
          </div>
        </div>
        <button
          onClick={runCheck}
          disabled={running}
          className="px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/5 rounded-lg disabled:opacity-50 whitespace-nowrap"
        >
          {running ? 'Prüft…' : 'Jetzt prüfen'}
        </button>
      </div>
      <div className="px-4 py-3 text-sm space-y-1">
        {last ? (
          <p className="text-gray-600">
            Letzte Prüfung: {formatWhen(last.checked_at)} —{' '}
            <span className={last.intact ? 'text-green-700' : 'text-red-700 font-medium'}>
              {last.intact ? 'in Ordnung' : 'Abweichung gefunden'}
            </span>
          </p>
        ) : (
          <p className="text-gray-500">Noch keine Prüfung gelaufen.</p>
        )}
        {result && (
          <p className={result.intact ? 'text-green-700' : 'text-red-700 font-medium'}>
            {integritySummary(result)}
          </p>
        )}
        {status === false && (
          <p className="text-gray-600">
            Eine Abweichung bedeutet: Protokollzeilen wurden außerhalb von PraxisZeit verändert
            oder entfernt. Bitte die Datensicherung aufbewahren und den Support informieren.
          </p>
        )}
        {headBroken && (
          <div className="mt-2 border-t border-gray-100 pt-2 space-y-2">
            <p className="text-gray-600">
              Das Kettenende fehlt oder stimmt nicht. Bis es neu gesetzt ist, sind das Löschen
              von Protokollzeilen (Endlöschung, Aufbewahrungsfrist) und das Versiegeln neuer
              Zeilen gesperrt. Neu setzen erst, nachdem die Ursache geklärt ist — der Vorgang
              wird mit Grund dauerhaft im Protokoll vermerkt.
            </p>
            {reanchorOpen ? (
              <div className="space-y-2">
                <label htmlFor="reanchor-reason" className="block text-gray-700 font-medium">
                  Grund (mindestens 10 Zeichen)
                </label>
                <textarea
                  id="reanchor-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={300}
                  rows={2}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    onClick={reanchor}
                    disabled={running || reason.trim().length < 10}
                    className="px-3 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                  >
                    Kettenende neu setzen
                  </button>
                  <button
                    onClick={() => setReanchorOpen(false)}
                    className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
                  >
                    Abbrechen
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setReanchorOpen(true)}
                className="px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 rounded-lg"
              >
                Kettenende neu setzen…
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
