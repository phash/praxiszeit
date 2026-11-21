import { useId } from 'react';
import { AUTO_CLOSED_HINT } from '../../../utils/creditOverride';
import type { TimeEntryChange } from './workingHoursTypes';
import { losingEntries, recognizableLosingIds, recognizeRowText } from './recognizeSelection';
import { RECOGNIZE_NOTE, RECOGNIZE_TITLE } from './workingHoursTexts';

interface RecognizeEntriesListProps {
  /** `time_entry_changes` der Vorschau (alle neu gekappten Einträge). */
  changes: TimeEntryChange[];
  selected: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
}

/**
 * Plan 2026-11-21 Task 6 (Spec 6.2): „Einträge, die Zeit verlieren" — je
 * verlierendem Eintrag ein Häkchen. Gewählte Einträge werden beim Speichern
 * der Arbeitszeit-Änderung anerkannt. Nicht anerkennbare (automatisch
 * geschlossene) Einträge haben ein deaktiviertes Häkchen mit dem Hinweis aus
 * `utils/creditOverride.ts`.
 */
export default function RecognizeEntriesList({ changes, selected, onChange }: RecognizeEntriesListProps) {
  const baseId = useId();
  const losing = losingEntries(changes);
  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    onChange(next);
  };

  return (
    <section
      aria-labelledby={`${baseId}-title`}
      className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 min-w-0 break-words"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 id={`${baseId}-title`} className="font-semibold">{RECOGNIZE_TITLE}</h4>
        <div className="flex gap-1 text-sm">
          <button
            type="button"
            onClick={() => onChange(new Set(recognizableLosingIds(changes)))}
            className="font-medium underline hover:no-underline"
          >
            Alle auswählen
          </button>
          <span aria-hidden="true">/</span>
          <button
            type="button"
            onClick={() => onChange(new Set())}
            className="font-medium underline hover:no-underline"
          >
            Keine
          </button>
        </div>
      </div>
      <ul className="mt-2 space-y-1">
        {losing.map((c) => {
          const hintId = `${baseId}-${c.entry_id}-hint`;
          const enabled = !!c.recognizable;
          return (
            <li key={c.entry_id}>
              <label className={`flex items-start gap-2 ${enabled ? 'cursor-pointer' : 'cursor-not-allowed text-amber-800'}`}>
                <input
                  type="checkbox"
                  checked={enabled && selected.has(c.entry_id)}
                  disabled={!enabled}
                  aria-describedby={enabled ? undefined : hintId}
                  onChange={(e) => toggle(c.entry_id, e.target.checked)}
                  className="w-4 h-4 mt-0.5 shrink-0 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                />
                <span>
                  {recognizeRowText(c)}
                  {c.blockless_workday && (
                    <span className="ml-2 inline-block rounded bg-amber-200 px-1.5 text-xs font-medium text-amber-900">
                      Tag ohne Block
                    </span>
                  )}
                </span>
              </label>
              {!enabled && <p id={hintId} className="ml-6 text-xs text-amber-800">{AUTO_CLOSED_HINT}</p>}
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-amber-800">{RECOGNIZE_NOTE}</p>
    </section>
  );
}
