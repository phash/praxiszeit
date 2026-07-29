import { ABSENCE_TYPE_LABELS, type AbsenceType } from '../constants/absenceTypes';
import { deHoursExact } from '../utils/formatters';

/**
 * Darstellung einer „Alte Werte"/„Neue Werte"-Seite einer Audit-Zeile.
 *
 * Es gibt ZWEI Ansichten desselben Protokolls — die Seite
 * `admin/AuditLog.tsx` (Änderungsprotokoll, ganze Tabelle) und das
 * Detail-Modal in `admin/AdminDashboard.tsx` (dasselbe Protokoll je
 * Mitarbeiter:in, `/admin/audit-log?user_id=…&changes_only=true`). Beide
 * rendern dieselben Zeilen; beide hatten denselben Fehler, und ein Fix in nur
 * einer der beiden lässt die andere kaputt. Deshalb lebt die Entscheidung
 * „welche Teilangabe gibt es überhaupt" ab jetzt hier, an genau einer Stelle.
 *
 * Der Fehler: Datum, Von–Bis und Pause wurden bedingungslos gerendert und
 * `old_note`/`new_note` gar nicht. Nicht jede Audit-Zeile ist ein Zeiteintrag —
 * die Zeilen der Wochenstunden-Rückrechnung (`source="wh_change"`) tragen ihren
 * Inhalt im Freitext: die Sammelzeile ganz ohne Datum und Zeiten (sie war damit
 * inhaltlich unsichtbar), die Einzelzeile je nachgezogener Abwesenheit mit
 * Datum, aber ohne Von–Bis und ohne Pause (sie hätte „- P:min" gezeigt und den
 * eigentlichen Text verschluckt).
 */

/**
 * Interne Audit-Marker in deutschen Klartext übersetzen.
 *
 * Mehrere Schreibpfade legen die Abwesenheit maschinenlesbar ab —
 * `absence:sick:8.0h` (`absences.py`, `admin_change_requests.py`),
 * teils mit Zusatz: `absence:vacation:8.0h (cancelled vacation_request <uuid>)`
 * (`vacation_requests.py`) oder `… (link-existing)`. Solange die Notizen gar
 * nicht angezeigt wurden, fiel das nicht auf; sichtbar gemacht gehört diese
 * Syntax (samt roher UUID) nicht in eine deutsche Kundenoberfläche.
 *
 * Übersetzt wird ausschliesslich für die ANZEIGE. Die gespeicherten
 * Marker-Strings bleiben unangetastet: sie sind §16-Bestand und gehen in den
 * `row_hash` der Tamper-Evidence (#121) ein — sie umzuschreiben würde jede
 * betroffene Altzeile als „manipuliert" melden.
 *
 * Alles, was nicht sicher als Marker erkannt wird (unbekannter Typ, unparsbare
 * Stundenzahl, jede andere Notiz), wird unverändert durchgereicht.
 */
const ABSENCE_MARKER = /^absence:([a-z_]+):(-?\d+(?:\.\d+)?)h(.*)$/;

/** Bekannte Zusätze hinter dem Marker — inkl. der rohen UUID, die entfällt. */
const MARKER_SUFFIXES: ReadonlyArray<[RegExp, string]> = [
  [/^\s*\(link-existing\)$/, ' (bestehende Abwesenheit verknüpft)'],
  [/^\s*\(cancelled vacation_request [^)]*\)$/i, ' (Urlaubsantrag storniert)'],
];

export function formatAuditNote(note?: string | null): string | undefined {
  if (!note) return undefined;
  const match = ABSENCE_MARKER.exec(note);
  if (!match) return note;
  const label = ABSENCE_TYPE_LABELS[match[1] as AbsenceType];
  if (!label) return note; // unbekannter Typ → lieber roh als falsch
  const hours = Number(match[2]);
  if (!Number.isFinite(hours)) return note;

  let tail = match[3];
  for (const [pattern, replacement] of MARKER_SUFFIXES) {
    if (pattern.test(tail)) {
      tail = replacement;
      break;
    }
  }
  // Ein unbekannter Zusatz bleibt wörtlich stehen — die Stundenangabe davor ist
  // trotzdem lesbar, und nichts geht verloren.
  return `${label} ${deHoursExact(hours)} h${tail}`;
}

/**
 * Datum + Zeitspanne als eine Zeile, ohne hängenden Bindestrich, wenn es gar
 * keine Zeiten gibt. Für die Datums-„Pillen" der Mobile-Karte.
 * Leerstring, wenn beides fehlt.
 */
export function auditPillText(date?: string, start?: string, end?: string): string {
  const times = start || end
    ? `${start?.substring(0, 5) ?? ''} - ${end?.substring(0, 5) ?? ''}`.trim()
    : '';
  return [date, times].filter(Boolean).join(' ');
}

interface AuditValuesProps {
  date?: string;
  start?: string;
  end?: string;
  breakMinutes?: number | null;
  note?: string | null;
  /**
   * Gesetzt = kompakte EINE-Zeile-Variante mit vorangestelltem „Alt"/„Neu"
   * (Detail-Modal des Admin-Dashboards, schmale Scroll-Liste). Nicht gesetzt =
   * Block-Variante für die Tabellenzelle des Änderungsprotokolls.
   */
  prefix?: string;
  className?: string;
}

export default function AuditValues({
  date, start, end, breakMinutes, note, prefix, className,
}: AuditValuesProps) {
  const times = start || end
    ? `${start?.substring(0, 5) ?? ''} - ${end?.substring(0, 5) ?? ''}`.trim()
    : null;
  const text = formatAuditNote(note);
  const hasBreak = breakMinutes !== null && breakMinutes !== undefined;
  const empty = !date && !times && !hasBreak && !text;

  if (prefix) {
    // Im Modal gibt es für eine leere Seite keinen Platzhalter — die Zeile
    // entfällt einfach (Verhalten wie bisher).
    if (empty) return null;
    const head = [date, times, hasBreak ? `P:${breakMinutes}min` : null]
      .filter(Boolean).join(' ');
    return (
      <p className={`${className ?? ''} break-words`.trim()}>
        {prefix}: {[head, text].filter(Boolean).join(' ')}
      </p>
    );
  }

  if (empty) return <span className="text-gray-400">-</span>;
  return (
    <div>
      {date && <p>{date}</p>}
      {times && <p>{times}</p>}
      {hasBreak && <p>Pause: {breakMinutes} min</p>}
      {text && <p className="text-gray-500 break-words">{text}</p>}
    </div>
  );
}
