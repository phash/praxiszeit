import { useEffect, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { ShieldAlert } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';

/**
 * #489: Kontovorgänge (security_events) — wer hat wen deaktiviert, reaktiviert,
 * umgestuft oder wessen Passwort neu gesetzt; dazu die Notfall-Vorgänge über die
 * Kommandozeile (#425). Vorher stand nur `deactivated_at` in der Nutzerzeile:
 * eine Praxis, die sich ausgesperrt hatte, konnte nicht nachvollziehen, wie.
 */
interface SecurityEvent {
  id: string;
  created_at: string;
  event: string;
  subject_user_id: string | null;
  subject_name: string | null;
  actor: string;
  actor_name: string;
  detail: string | null;
}

const EVENT_LABELS: Record<string, string> = {
  user_deactivated: 'Konto deaktiviert',
  user_reactivated: 'Konto reaktiviert',
  user_role_changed: 'Rolle geändert',
  admin_set_password: 'Passwort durch Verwaltung gesetzt',
  admin_password_reset_cli: 'Passwort per Kommandozeile zurückgesetzt',
  totp_disabled_cli: 'Zwei-Faktor per Kommandozeile abgeschaltet',
  user_reactivated_cli: 'Konto per Kommandozeile reaktiviert',
};

function formatWhen(iso: string): string {
  const d = parseISO(iso);
  return isNaN(d.getTime()) ? iso : format(d, 'dd.MM.yyyy HH:mm');
}

export default function SecurityEventsCard() {
  const toast = useToast();
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);

  // Einmal beim Öffnen laden — bewusst ohne `toast` in den Abhängigkeiten
  // (instabile Referenz → Lade-Schleife, siehe CLAUDE.md #305 M2d).
  useEffect(() => {
    apiClient
      .get('/admin/security-events')
      .then((res) => setEvents(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Fehler beim Laden der Konto-Vorgänge'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden mt-8">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-2">
        <ShieldAlert size={18} className="text-primary" />
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Konto-Vorgänge</h2>
          <p className="text-xs text-gray-500">
            Deaktivieren, Reaktivieren, Rollen- und Passwortänderungen – wer hat wann was getan.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="px-4 py-6 text-sm text-gray-500">Lade …</p>
      ) : events.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-500">Noch keine Konto-Vorgänge protokolliert.</p>
      ) : (
        <>
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Zeitpunkt</th>
                  <th className="px-4 py-2 text-left font-medium">Vorgang</th>
                  <th className="px-4 py-2 text-left font-medium">Konto</th>
                  <th className="px-4 py-2 text-left font-medium">Durch</th>
                  <th className="px-4 py-2 text-left font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {events.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-2 whitespace-nowrap text-gray-600">{formatWhen(e.created_at)}</td>
                    <td className="px-4 py-2">{EVENT_LABELS[e.event] ?? e.event}</td>
                    <td className="px-4 py-2">{e.subject_name ?? '–'}</td>
                    <td className="px-4 py-2">{e.actor_name}</td>
                    <td className="px-4 py-2 text-gray-500">{e.detail ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="lg:hidden divide-y divide-gray-100">
            {events.map((e) => (
              <li key={e.id} className="px-4 py-3 text-sm">
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{EVENT_LABELS[e.event] ?? e.event}</span>
                  <span className="text-gray-500 whitespace-nowrap">{formatWhen(e.created_at)}</span>
                </div>
                <div className="text-gray-700">{e.subject_name ?? '–'}</div>
                <div className="text-gray-500">durch {e.actor_name}</div>
                {e.detail && <div className="text-gray-500">{e.detail}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
