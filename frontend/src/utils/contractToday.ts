/**
 * Teil A (075, F011): Urlaubsanspruch und Stundenzählung sind je Datum
 * historisiert. Die User-Zeile spiegelt eine zukunftsdatierte Verlaufszeile erst
 * beim nächsten Schreiben (kein Scheduler, Spec 9.8) — „heute"-Fragen der
 * Oberfläche lesen deshalb den heute gültigen Snapshot (`schedule_today`) und
 * fallen nur bei älteren Antworten ohne das Feld auf die Zeile zurück.
 */
interface ContractSource {
  track_hours?: boolean | null;
  vacation_days?: number | null;
  schedule_today?: { track_hours?: boolean | null; vacation_days?: number | null } | null;
}

/** Stundenzählung heute; unbekannt (kein Nutzer) → `undefined`. */
export function trackHoursToday(user: ContractSource | null | undefined): boolean | undefined {
  if (!user) return undefined;
  return user.schedule_today?.track_hours ?? user.track_hours ?? undefined;
}

/** Urlaubsanspruch (Tage/Jahr) heute. */
export function vacationDaysToday(user: ContractSource | null | undefined): number | undefined {
  if (!user) return undefined;
  return user.schedule_today?.vacation_days ?? user.vacation_days ?? undefined;
}
