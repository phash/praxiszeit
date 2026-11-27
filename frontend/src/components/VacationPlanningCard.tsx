import { useEffect, useRef, useState } from 'react';
import apiClient from '../api/client';
import { formatDayCount } from '../utils/formatters';

/** #585: Antwort von `GET /dashboard/vacation?year=` (nur die gelesenen Felder). */
export interface VacationPlanning {
  year: number;
  budget_days: number;
  used_days: number;
  remaining_days: number;
  entitlement_days?: number | null;
  carryover_days?: number | null;
  closure_days?: number | null;
  pending_days?: number | null;
  plannable_days?: number | null;
}

interface Props {
  year: number;
  /** Nur Auslöser: neue Liste eigener Abwesenheiten = neu laden. */
  absences?: unknown;
  /** Nur Auslöser: neue Liste eigener Anträge = neu laden. */
  requests?: unknown;
}

/**
 * #585 (Kundenwunsch): Urlaubskonto des angezeigten Jahres auf der Seite
 * „Abwesenheiten" — damit Mitarbeitende den Urlaub des kommenden Jahres planen
 * können. Alle Zahlen rechnet der Server (Tagesprinzip, Betriebsferien,
 * offene Anträge); hier wird nur angezeigt.
 */
export default function VacationPlanningCard({ year, absences, requests }: Props) {
  const [data, setData] = useState<VacationPlanning | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    apiClient.get<VacationPlanning>(`/dashboard/vacation?year=${year}`)
      .then((res) => { if (mine === seq.current) setData(res.data); })
      .catch(() => { if (mine === seq.current) setData(null); });
  }, [year, absences, requests]);

  if (!data || data.year !== year) return null;

  const carryover = data.carryover_days ?? 0;
  const closure = data.closure_days ?? 0;
  const pending = data.pending_days ?? 0;
  const plannable = data.plannable_days ?? data.remaining_days;
  const entitlement = data.entitlement_days ?? data.budget_days - carryover;
  const futureYearWithoutCarryover = year > new Date().getFullYear() && carryover === 0;

  return (
    <section
      aria-label={`Urlaub ${year}`}
      className="bg-white rounded-xl shadow-xs border border-gray-200 p-4 mb-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h3 className="font-semibold text-gray-800">Urlaub {year}</h3>
        <p className="text-sm text-gray-600">
          Noch verplanbar:{' '}
          <span
            data-testid="vacation-plannable"
            className={`text-lg font-bold ${plannable < 0 ? 'text-red-600' : 'text-primary'}`}
          >
            {formatDayCount(plannable)}
          </span>
        </p>
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <dt className="text-gray-500">Anspruch</dt>
          <dd className="font-medium text-gray-900">{formatDayCount(entitlement)}</dd>
          {carryover > 0 && (
            <dd className="text-xs text-gray-500">+ {formatDayCount(carryover)} Übertrag</dd>
          )}
          {carryover < 0 && (
            <dd className="text-xs text-gray-500">
              − {formatDayCount(-carryover)} Übertrag (Minusurlaub aus {year - 1})
            </dd>
          )}
        </div>
        <div>
          <dt className="text-gray-500">Gebucht</dt>
          <dd className="font-medium text-gray-900">{formatDayCount(data.used_days)}</dd>
          {closure > 0 && (
            <dd className="text-xs text-gray-500">davon {formatDayCount(closure)} Betriebsferien</dd>
          )}
        </div>
        <div>
          <dt className="text-gray-500">Beantragt (offen)</dt>
          <dd className="font-medium text-gray-900">{formatDayCount(pending)}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Rest nach Buchungen</dt>
          <dd className="font-medium text-gray-900">{formatDayCount(data.remaining_days)}</dd>
        </div>
      </dl>
      {futureYearWithoutCarryover && (
        <p className="mt-3 text-xs text-gray-500">
          Resturlaub aus {year - 1} kommt erst mit dem Jahresabschluss dazu.
        </p>
      )}
    </section>
  );
}
