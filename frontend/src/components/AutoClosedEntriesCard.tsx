import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import apiClient from '../api/client';
import { formatHoursHM } from '../utils/errorMessage';

/**
 * #540 (A1-04): automatisch geschlossene Einträge, deren tatsächliches Ende
 * noch fehlt (`GET /admin/time-entries/auto-closed`). Bis dahin schrieb der
 * Auto-Close z. B. 15:59 h ohne jede Meldung — als Ist, im Saldo und in den
 * §16-Exporten. Die Karte nennt jeden Fall mit den §3/§4-Befunden; korrigiert
 * wird über das Monatsjournal der Person (Ende eintragen) bzw. über den
 * Änderungsantrag, den die Person aus der Stempeluhr stellt. Ohne Fälle
 * erscheint die Karte nicht.
 */
export interface AutoClosedRow {
  id: string;
  user_id: string;
  user_name: string;
  date: string;
  start_time: string;
  end_time: string | null;
  net_hours: number;
  findings: string[];
  pending_change_request: boolean;
}

function formatDE(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function AutoClosedEntriesCard() {
  const [rows, setRows] = useState<AutoClosedRow[]>([]);

  // Einmal beim Öffnen laden (keine instabile toast-Referenz in den Deps).
  useEffect(() => {
    apiClient
      .get('/admin/time-entries/auto-closed')
      .then((res) => setRows(Array.isArray(res.data) ? res.data : []))
      .catch(() => setRows([]));
  }, []);

  if (rows.length === 0) return null;

  return (
    <section
      aria-labelledby="auto-closed-title"
      className="bg-amber-50 rounded-xl border border-amber-200 p-4 mb-8"
    >
      <h2 id="auto-closed-title" className="flex items-center gap-2 text-base font-semibold text-amber-900">
        <AlertTriangle size={18} aria-hidden="true" />
        Automatisch geschlossene Einträge – Ende fehlt ({rows.length})
      </h2>
      <p className="text-sm text-amber-800 mt-1">
        Diese Einträge wurden geschlossen, weil das Ausstempeln fehlte. Angerechnet ist die Zeit bis zum
        automatischen Ende. Bitte das tatsächliche Ende im Monatsjournal der Person eintragen oder den
        Änderungsantrag der Person prüfen.
      </p>
      <ul className="mt-3 divide-y divide-amber-200">
        {rows.map((r) => (
          <li key={r.id} className="py-2 text-sm text-amber-950">
            <span className="font-medium">{r.user_name}</span>
            {' · '}
            {formatDE(r.date)} ab {r.start_time.substring(0, 5)}
            {r.end_time ? `, angerechnet bis ${r.end_time.substring(0, 5)} (${formatHoursHM(r.net_hours)} h)` : ''}
            {r.pending_change_request && (
              <span className="ml-2 inline-block rounded-full bg-white px-2 py-0.5 text-xs text-amber-800 border border-amber-300">
                Antrag gestellt
              </span>
            )}
            {r.findings.length > 0 && (
              <span className="block text-xs text-red-700 mt-0.5">{r.findings.join(' · ')}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
