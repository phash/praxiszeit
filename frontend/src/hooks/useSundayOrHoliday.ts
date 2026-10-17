import { useEffect, useState } from 'react';
import apiClient from '../api/client';

interface EntryLike {
  date: string;
  is_sunday_or_holiday?: boolean;
}

/**
 * #491 F4: Liegt `date` (YYYY-MM-DD) auf einem Sonntag oder einem gesetzlichen
 * Feiertag des Mandanten? Dann fragt eine Erfassungsfläche nach dem
 * §10-ArbZG-Ausnahmegrund.
 *
 * Gemeinsame Regel für das Antragsformular (`ChangeRequestForm`) und die
 * Direkteingabe (`TimeTracking`) — vorher prüfte die Direkteingabe nur den
 * Sonntag, und ein neuer Eintrag an einem Feiertag unter der Woche (KV-Dienst
 * an Christi Himmelfahrt) entstand ohne Grund. Das Monatsjournal fragt
 * ebenfalls an Sonn- und Feiertagen (dort über `is_holiday` der Journalzeile).
 *
 * - Samstag ist ein Werktag — dort fragt §10 nicht.
 * - Die Feiertage kommen je Jahr einmal von `GET /holidays?year=`; ein
 *   Datumswechsel innerhalb desselben Jahres löst keinen neuen Abruf aus.
 * - Schlägt der Abruf fehl, bleibt die Sonntagsregel (das Feld ist optional).
 * - `entry.is_sunday_or_holiday` (vom Server) gilt, solange das Datum des
 *   Eintrags unverändert ist — auch ohne geladene Feiertagsliste.
 * - `enabled = false` (z. B. Lösch-Antrag, geschlossenes Formular) lädt nichts.
 */
export function useSundayOrHoliday(
  date: string,
  entry?: EntryLike | null,
  enabled = true,
): boolean {
  const [holidayDates, setHolidayDates] = useState<Set<string>>(() => new Set());
  const year = /^\d{4}-/.test(date) ? date.slice(0, 4) : '';

  useEffect(() => {
    if (!enabled || !year) return;
    let cancelled = false;
    apiClient
      .get<{ date: string }[]>(`/holidays?year=${year}`)
      .then((res) => {
        if (!cancelled) setHolidayDates(new Set((res.data ?? []).map((h) => h.date)));
      })
      .catch(() => {
        if (!cancelled) setHolidayDates(new Set());
      });
    return () => {
      cancelled = true;
    };
  }, [year, enabled]);

  if (!enabled || !date) return false;
  if (new Date(`${date}T12:00:00`).getDay() === 0) return true;
  if (holidayDates.has(date)) return true;
  return !!entry?.is_sunday_or_holiday && date === entry.date;
}
