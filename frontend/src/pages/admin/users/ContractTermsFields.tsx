import { useSystemStore } from '../../../stores/systemStore';
import { formatDayNumber, formatFixedDe } from '../../../utils/formatters';
import { MAX_VACATION_DAYS } from './workingHoursTypes';
import type { ContractTerms } from './workingHoursTypes';

interface ContractTermsFieldsProps {
  value: ContractTerms;
  onChange: (value: ContractTerms) => void;
  /** `create` = Benutzerformular beim Anlegen, `change` = Dialog „Arbeitszeit ändern". */
  mode: 'create' | 'change';
  /** Vorgeschlagener Urlaubsanspruch (`null` = keiner). */
  suggestion: number | null;
  /** `""` im Benutzerformular (E2E-Ids `f-vacation`, `track_hours`, …), `"wh-"` im Dialog. */
  idPrefix: string;
  /** Wochenstunden für die Schätzung „aus Wochenstunden ≈ …" (#377 2a). */
  weeklyHours: number;
  /** Nur `create`: Arbeitstage, auf denen die Empfehlung beruht. */
  workDays?: number;
}

/**
 * Teil A (Spec „Dialog", Task 13): die fünf Vertragsfelder neben den Stunden —
 * Urlaubsanspruch, Stundenzählung, MiLoG-Arbeitszeitkonto, vereinbarte
 * Monatsarbeitszeit, festes Monats-Soll. EINE Stelle für Benutzerformular
 * (Anlegen) und Dialog, damit Beschriftungen und Abhängigkeiten gleich bleiben.
 * Liefert ein Fragment aus Rasterzellen (`md:col-span-2` für die breiten).
 */
export default function ContractTermsFields({
  value, onChange, mode, suggestion, idPrefix, weeklyHours, workDays,
}: ContractTermsFieldsProps) {
  const minWage = useSystemStore((s) => s.getMinimumWage()); // #377
  const set = (patch: Partial<ContractTerms>) => onChange({ ...value, ...patch });
  // Feld-Ids des Benutzerformulars bleiben, wie sie waren (`f-vacation`, `f-agreed-monthly`).
  const fieldId = (name: string) => `${idPrefix || 'f-'}${name}`;
  const vacationId = fieldId('vacation');
  const showSuggestion = suggestion !== null && value.vacation_days !== suggestion;
  const derivedMonthly = weeklyHours * 13 / 3;

  return (
    <>
      <div>
        <label htmlFor={vacationId} className="block text-sm font-medium text-gray-700 mb-1">
          {mode === 'change' ? 'Urlaubsanspruch pro Jahr ab diesem Datum' : 'Urlaubstage'}
        </label>
        <input
          id={vacationId}
          type="number"
          // Leer bleibt im Dialog leer (NaN) — er sperrt dann das Speichern,
          // statt still 0 Tage zu senden.
          value={Number.isFinite(value.vacation_days) ? value.vacation_days : ''}
          onChange={(e) => set({
            vacation_days: mode === 'change'
              ? (e.target.value === '' ? Number.NaN : parseFloat(e.target.value))
              : (parseFloat(e.target.value) || 0),
          })}
          required
          min="0"
          max={MAX_VACATION_DAYS}
          step="0.1"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
        />
        {showSuggestion && mode === 'create' && (
          <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded-sm text-xs">
            💡 <strong>Empfehlung:</strong> {suggestion} Tage
            (basierend auf {workDays} Arbeitstagen/Woche)
            <button
              type="button"
              onClick={() => set({ vacation_days: suggestion })}
              className="ml-2 text-blue-600 underline"
            >
              Übernehmen
            </button>
          </div>
        )}
        {showSuggestion && mode === 'change' && (
          <button
            type="button"
            onClick={() => set({ vacation_days: suggestion })}
            className="mt-1 text-sm text-blue-700 underline hover:no-underline"
          >
            {`Vorschlag übernehmen (${formatDayNumber(suggestion)})`}
          </button>
        )}
      </div>

      <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
        <input
          type="checkbox"
          id={`${idPrefix}track_hours`}
          checked={value.track_hours}
          // F009: festes Monats-Soll setzt Stundenzählung und MiLoG-Konto voraus
          // (Backend 400) — beim Abschalten mit zurücksetzen, sonst blockiert
          // ein (ggf. verborgener) Haken die Änderung.
          onChange={(e) => set(e.target.checked
            ? { track_hours: true }
            : { track_hours: false, use_fixed_monthly_target: false })}
          className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
        />
        <label htmlFor={`${idPrefix}track_hours`} className="text-sm font-medium text-gray-700 cursor-pointer">
          Stundenzählung aktiv (Soll-Stunden werden berechnet)
        </label>
      </div>

      {/* #377 Minijob / Arbeitszeitkonto (§2 Abs.2 MiLoG) */}
      <div className="md:col-span-2 p-3 bg-amber-50 rounded-lg border border-amber-200">
        <div className="flex items-center space-x-2">
          <input
            type="checkbox"
            id={`${idPrefix}milog_working_time_account`}
            checked={value.milog_working_time_account}
            onChange={(e) => set(e.target.checked
              ? { milog_working_time_account: true }
              : { milog_working_time_account: false, use_fixed_monthly_target: false })}
            className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
          />
          <label
            htmlFor={`${idPrefix}milog_working_time_account`}
            className="text-sm font-medium text-gray-700 cursor-pointer"
          >
            Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) – 50-%-Prüfung & 12-Monats-Ausgleichsfrist
          </label>
        </div>
        {value.milog_working_time_account && (
          <div className="mt-2">
            {/* #377 Baustein 2a: vereinbarte Monatsarbeitszeit direkt eingeben */}
            <label htmlFor={fieldId('agreed-monthly')} className="block text-sm font-medium text-gray-700 mb-1">
              Vereinbarte Monatsarbeitszeit (h){value.use_fixed_monthly_target ? ' *' : ''}
            </label>
            <input
              id={fieldId('agreed-monthly')}
              type="number"
              // Bug-Tracker #4: `0.5` wies u. a. den eigenen Vorschlagswert
              // (Wochenstunden × 13/3, eine Nachkommastelle) als Schrittfehler
              // ab. `0.1` = Genauigkeit der Spalte `Numeric(5, 1)`; feiner
              // einzugeben hieße, dass die DB still rundet.
              step="0.1"
              min="0"
              max="400"
              placeholder={
                value.use_fixed_monthly_target
                  ? 'Pflichtfeld – festes Monats-Soll'
                  : `aus Wochenstunden ≈ ${formatFixedDe(derivedMonthly, 1)}`
              }
              value={value.agreed_monthly_hours ?? ''}
              onChange={(e) => set({
                // #377 2a: 0/negativ/leer = „keine Monatszahl vereinbart" → null
                // (aus Wochenstunden ableiten). Backend akzeptiert nur > 0.
                agreed_monthly_hours: parseFloat(e.target.value) > 0 ? parseFloat(e.target.value) : null,
              })}
              required={value.use_fixed_monthly_target}
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                value.use_fixed_monthly_target ? 'border-amber-400' : 'border-gray-300'
              }`}
            />
            {(() => {
              const monthly = value.agreed_monthly_hours != null ? value.agreed_monthly_hours : derivedMonthly;
              return (
                <p className="mt-1 text-xs text-amber-800">
                  {minWage && typeof minWage.current === 'number'
                    ? `Aktueller Mindestlohn: ${formatFixedDe(minWage.current, 2)} €/h (seit ${new Date(minWage.since).toLocaleDateString('de-DE')}). `
                    : ''}
                  Leer = automatisch aus den Wochenstunden (≈ {formatFixedDe(derivedMonthly, 1)} h).
                  Vereinbarte Monatszeit {value.agreed_monthly_hours != null ? '' : '≈ '}{formatFixedDe(monthly, 1)} h
                  → max. Konto ≈ {formatFixedDe((monthly / 2), 1)} h/Monat (50 %, § 2 Abs. 2 MiLoG). Warnung ist weich
                  (nicht blockierend), sofern zur Mindestlohnhöhe vergütet. Keine Verdienst-/603-€-Prüfung.
                </p>
              );
            })()}

            {/* #377 Baustein 2b: festes Monats-Soll statt Wochenstunden×Arbeitstage */}
            <div className="mt-3 pt-3 border-t border-amber-200">
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id={`${idPrefix}use_fixed_monthly_target`}
                  checked={value.use_fixed_monthly_target}
                  onChange={(e) => set({ use_fixed_monthly_target: e.target.checked })}
                  className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                />
                <label
                  htmlFor={`${idPrefix}use_fixed_monthly_target`}
                  className="text-sm font-medium text-gray-700 cursor-pointer"
                >
                  Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)
                </label>
              </div>
              <p className="mt-1 text-xs text-amber-800">
                Statt aus Wochenstunden/Arbeitstagen/Kalendertagen wird das Monats-Soll fest auf die oben
                vereinbarte Monatsarbeitszeit gesetzt (Minijob-typisch bei schwankenden Einsatzplänen).
                Erfordert Stundenzählung und ein gesetztes Feld oben. Wochenstunden bleiben als Basisangabe
                bestehen, wirken sich in diesem Modus aber nicht mehr auf das Soll aus.
              </p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
