// Plan 2026-11-21 Task 6: Auswahl der Einträge, die beim Speichern einer
// Arbeitszeit-Änderung anerkannt werden. Reine Funktionen — der Dialog hält
// nur den Zustand. Grundlage ist die Vorschau OHNE Anerkennen: `old_net`/
// `new_net` und die Kennzeichen beschreiben die Neukappung, nicht das Ergebnis
// nach dem Anerkennen. So bleibt die Liste stehen, während Häkchen gesetzt werden.
import { formatHoursHM } from '../../../utils/formatters';
import type { TimeEntryChange } from './workingHoursTypes';
import { shortDate } from './workingHoursTexts';

/** Einträge, die durch die Änderung angerechnete Zeit verlieren. */
export function losingEntries(changes: TimeEntryChange[]): TimeEntryChange[] {
  return changes.filter((c) => c.new_net < c.old_net);
}

/** Vorauswahl (Spec 6.2): verlierende, anerkennbare Einträge an einem Werktag
 * ohne Block oder an einem Tag, den der alte Vertrag gar nicht kappte. Ein
 * Randschnitt an einem schon bestehenden Block bleibt abgewählt — das ist eine
 * echte Verkürzung. */
export function defaultSelection(changes: TimeEntryChange[]): Set<string> {
  return new Set(
    losingEntries(changes)
      .filter((c) => c.recognizable && (c.blockless_workday || c.newly_clamped))
      .map((c) => c.entry_id),
  );
}

/** „Alle auswählen": alle verlierenden, anerkennbaren Einträge (sortiert). */
export function recognizableLosingIds(changes: TimeEntryChange[]): string[] {
  return losingEntries(changes).filter((c) => c.recognizable).map((c) => c.entry_id).sort();
}

/** Auswahl auf die Einträge der (neuen) Vorschau einschränken — fehlende oder
 * nicht anerkennbare IDs fallen heraus. Sortiert, damit der Vorschau-Schlüssel
 * nicht von der Klickreihenfolge abhängt. */
export function pruneSelection(selected: Iterable<string>, changes: TimeEntryChange[]): string[] {
  const allowed = new Set(recognizableLosingIds(changes));
  return [...new Set(selected)].filter((id) => allowed.has(id)).sort();
}

const WEEKDAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const clock = (t: string | null) => (t ? t.slice(0, 5) : '–');

/** „Mi 07.10. · gestempelt 07:50–12:05 · bisher 4:15 h → neu 0:00 h". */
export function recognizeRowText(c: TimeEntryChange): string {
  const weekday = WEEKDAYS[new Date(`${c.date.slice(0, 10)}T00:00:00Z`).getUTCDay()];
  return `${weekday} ${shortDate(c.date)} · gestempelt ${clock(c.old_start)}–${clock(c.old_end)}`
    + ` · bisher ${formatHoursHM(c.old_net)} h → neu ${formatHoursHM(c.new_net)} h`;
}
