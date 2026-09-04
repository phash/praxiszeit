import React, { useState, useEffect } from 'react';
import { format, parseISO, isBefore, isAfter, startOfDay } from 'date-fns';
import { de } from 'date-fns/locale';
import { Pencil, Plus, Trash2, Check, X } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { formatHoursHMText, parseHours } from '../utils/formatters';
import { submitWithBreakWaiver } from '../utils/breakWaiverRetry';
import { showArbzgWarnings, collectAbsenceWarnings } from '../utils/arbzgWarnings';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from './ConfirmDialog';
import MonthSelector from './MonthSelector';
import LoadingSpinner from './LoadingSpinner';
import { RawStampNote } from './RawStampNote';
import { myReasons } from '../api/absenceReasons';
import type { AbsenceReason } from '../api/absenceReasons';

// ---- Types ----------------------------------------------------------------

interface TimeEntryItem {
  id: string;
  start_time: string | null;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
}

interface AbsenceItem {
  id: string;
  type: string;
  hours: number;
  start_time: string | null;
  end_time: string | null;
}

interface JournalDay {
  date: string;
  weekday: string;
  type: 'work' | 'vacation' | 'sick' | 'overtime' | 'training' | 'other' | 'paid_leave' | 'absent' | 'holiday' | 'weekend' | 'empty' | 'mixed';
  is_holiday: boolean;
  holiday_name: string | null;
  time_entries: TimeEntryItem[];
  absences: AbsenceItem[];
  actual_hours: number;
  target_hours: number;
  balance: number;
}

interface JournalData {
  user: { id: string; first_name: string; last_name: string };
  year: number;
  month: number;
  days: JournalDay[];
  monthly_summary: { actual_hours: number; target_hours: number; balance: number };
  yearly_overtime: number;
  // #463: Im festen Monats-Soll (#377 Baustein 2b) gibt es kein Tages-Soll.
  // `target_hours` der Tageszeilen trägt dort die GEPLANTE Anwesenheit, und ein
  // Tages-Saldo hat keine definierte Bedeutung. Optional, weil ältere Antworten
  // das Feld nicht führen — fehlt es, gilt das bisherige Verhalten.
  use_fixed_monthly_target?: boolean;
}

// #382: the journal fetch can, in an auth/proxy edge, resolve HTTP 200 with a
// body that is NOT a journal (e.g. an HTML login page served after a
// token_version-invalidated 401 → silent-refresh → retry churn). Feeding that
// straight into `setData` used to reach `data.days.map(...)` and throw during
// render → caught by ErrorBoundary → full-screen "Etwas ist schiefgelaufen".
// Validate the shape at the fetch boundary so a malformed body degrades to the
// normal inline error instead of white-screening the whole app.
export function isJournalData(x: unknown): x is JournalData {
  if (!x || typeof x !== 'object') return false;
  const d = x as Partial<JournalData>;
  return (
    Array.isArray(d.days) &&
    !!d.monthly_summary &&
    typeof d.monthly_summary === 'object' &&
    typeof d.yearly_overtime === 'number'
  );
}

// date-fns format() throws RangeError on an Invalid Date. And in date-fns v3
// parseISO() itself THROWS on a non-string (it calls dateString.split(...)
// unconditionally) — so guard the input type BEFORE parseISO, then the isNaN
// check catches malformed strings ('', 'not-a-date'). One bad day.date must not
// crash the table.
function safeParseISO(dateStr: unknown): Date | null {
  if (typeof dateStr !== 'string') return null;
  const d = parseISO(dateStr);
  return isNaN(d.getTime()) ? null : d;
}

interface EditState {
  startTime: string;    // "HH:mm"
  endTime: string;      // "HH:mm"
  breakMinutes: string; // string for <input> binding
  entryType: 'work' | 'sick' | 'training' | 'overtime' | 'other';
  absenceHours: string;
  reasonId?: string | null; // #312: selected custom absence reason
}

// ---- Helper functions -----------------------------------------------------

const TYPE_LABELS: Record<string, string> = {
  work: 'Arbeitszeit',
  vacation: 'Urlaub',
  sick: 'Krank',
  overtime: 'Überstundenausgleich',
  training: 'Fortbildung',
  other: 'Sonstiges',
  paid_leave: 'Bezahlte Freistellung',
  absent: 'Abwesend',
  holiday: 'Feiertag',
  weekend: '',
  empty: '–',
  mixed: 'Arbeitszeit',
};

const TYPE_COLORS: Record<string, string> = {
  work: 'text-gray-900',
  vacation: 'text-blue-600',
  sick: 'text-orange-600',
  overtime: 'text-purple-600',
  training: 'text-green-600',
  other: 'text-gray-600',
  paid_leave: 'text-teal-600',
  absent: 'text-gray-500',
  holiday: 'text-red-600',
  weekend: 'text-gray-400',
  empty: 'text-gray-400',
  mixed: 'text-gray-900',
};

// Thin wrappers over the shared formatter (utils/formatters.ts) — the previous
// local implementations reintroduced the "7h 60min" rollover bug and lacked the
// non-finite guard (rendered "NaNh NaNmin"). formatHours = signed (balance);
// formatHoursSimple = unsigned (actual/target). Both show '–' for 0.
function formatHours(h: number): string {
  return formatHoursHMText(h, { signed: true, dashForZero: true });
}

function formatHoursSimple(h: number): string {
  return formatHoursHMText(h, { dashForZero: true });
}

function isPastDay(dateStr: unknown): boolean {
  if (typeof dateStr !== 'string') return false; // #382: parseISO v3 throws on non-string
  const d = parseISO(dateStr);
  if (isNaN(d.getTime())) return false; // #382: malformed date → not "past"
  return isBefore(startOfDay(d), startOfDay(new Date()));
}

// #375: a future day is NOT editable in the journal (planned future absences go
// through the vacation/absence request flow). Admins may edit past AND today
// (an employee calling in sick today must be bookable immediately); the employee
// self-view stays past-only (they use clock-in/out for the current day).
function isFutureDay(dateStr: unknown): boolean {
  if (typeof dateStr !== 'string') return false; // #382: parseISO v3 throws on non-string
  const d = parseISO(dateStr);
  if (isNaN(d.getTime())) return false; // #382: malformed date → treat as not future
  return isAfter(startOfDay(d), startOfDay(new Date()));
}

// ---- Main component -------------------------------------------------------

interface MonthlyJournalProps {
  userId: string;
  isAdminView: boolean;
}

export default function MonthlyJournal({ userId, isAdminView }: MonthlyJournalProps) {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(format(now, 'yyyy-MM'));
  const [data, setData] = useState<JournalData | null>(null);
  // #463: `=== true` statt truthy — fehlt das Feld (ältere Antwort), gilt das
  // bisherige Verhalten, nicht der Fix-Modus.
  const fixedMode = data?.use_fixed_monthly_target === true;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [editingDate, setEditingDate] = useState<string | null>(null);
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [addingDate, setAddingDate] = useState<string | null>(null); // separate state for adding new entry
  const [editState, setEditState] = useState<EditState>({ startTime: '', endTime: '', breakMinutes: '0', entryType: 'work', absenceHours: '8', reasonId: null });
  const [reasons, setReasons] = useState<AbsenceReason[]>([]); // #312
  useEffect(() => { myReasons().then(setReasons).catch(() => { /* picker omits custom reasons */ }); }, []);
  const [saving, setSaving] = useState(false);
  const [submittingDate, setSubmittingDate] = useState<string | null>(null);
  const [submitReason, setSubmitReason] = useState('');
  const [savingChangeRequest, setSavingChangeRequest] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const [year, month] = selectedMonth.split('-').map(Number);
    const url = isAdminView
      // Fix #6: admins legitimately review absences (incl. SICK) in the journal;
      // request the health data explicitly so the backend serves it AND logs the
      // Art. 9 access in the audit trail (otherwise SICK days are masked).
      ? `/admin/users/${userId}/journal?year=${year}&month=${month}&include_health_data=true`
      : `/journal/me?year=${year}&month=${month}`;

    setLoading(true);
    setError(null);

    apiClient
      .get(url, { signal: controller.signal })
      .then((res) => {
        if (!isJournalData(res.data)) {
          // #382: non-journal 200 body → show the inline error, never crash.
          setData(null);
          setError('Journal konnte nicht geladen werden.');
          return;
        }
        // Belt-and-suspenders: a valid `days` array whose per-day entry/absence
        // lists are null (serialization anomaly) would trip the many `.map` /
        // `.length` sites below. Normalize to empty arrays once, here.
        setData({
          ...res.data,
          days: res.data.days.map((d) => ({
            ...d,
            // Coerce to arrays AND drop null/non-object elements so the many
            // downstream e.start_time / a.type derefs can't throw on a bad element.
            time_entries: (Array.isArray(d.time_entries) ? d.time_entries : []).filter(
              (e): e is TimeEntryItem => !!e && typeof e === 'object',
            ),
            absences: (Array.isArray(d.absences) ? d.absences : []).filter(
              (a): a is AbsenceItem => !!a && typeof a === 'object',
            ),
          })),
        });
      })
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED') return;
        setError(getErrorMessage(err, 'Journal konnte nicht geladen werden.'));
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [selectedMonth, userId, isAdminView, reloadKey]);

  const isNonWorkDay = (day: JournalDay) =>
    day.type === 'weekend' || day.type === 'holiday';

  function startEdit(day: JournalDay, entryToEdit?: TimeEntryItem) {
    const entry = entryToEdit ?? day.time_entries[0] ?? null;
    const absence = day.absences[0] ?? null;
    const hasTimeEntry = !!entry;
    const hasAbsence = !hasTimeEntry && !!absence;
    setEditingDate(day.date);
    setEditingEntryId(entry?.id ?? null);
    setEditState({
      startTime: entry?.start_time ?? '',
      endTime: entry?.end_time ?? '',
      breakMinutes: String(entry?.break_minutes ?? 0),
      entryType: hasAbsence ? (absence.type as EditState['entryType']) : 'work',
      absenceHours: hasAbsence ? String(absence.hours) : '8',
      reasonId: (absence as { reason_id?: string | null } | null)?.reason_id ?? null, // #312
    });
  }

  function startAdd(day: JournalDay) {
    setAddingDate(day.date);
    setEditingDate(null);
    setEditState({
      startTime: '',
      endTime: '',
      breakMinutes: '0',
      entryType: 'work',
      absenceHours: '8',
      reasonId: null, // #312
    });
  }

  function cancelEdit() {
    setEditingDate(null);
    setEditingEntryId(null);
    setAddingDate(null);
    setSubmittingDate(null);
  }

  async function handleAdminAdd(dateStr: string, day?: JournalDay) {
    setSaving(true);
    try {
      if (editState.entryType === 'work') {
        if (!editState.startTime || !editState.endTime) {
          toast.error('Von und Bis sind Pflichtfelder');
          setSaving(false);
          return;
        }
        // Release-Review 1.19.1: Antwort auswerten wie im Bearbeiten-Pfad
        // (handleAdminSave). Vorher meldete dieselbe Kappung auf demselben
        // Bildschirm je nach Aktion mal etwas und mal nichts: ein NEUER Eintrag
        // wurde stumm gekappt, erst die spätere Korrektur sagte es.
        const res = await apiClient.post(`/admin/users/${userId}/time-entries`, {
          date: dateStr,
          start_time: editState.startTime,
          end_time: editState.endTime,
          break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
        });
        showArbzgWarnings(toast, res.data?.warnings);
      } else {
        const hasExistingEntries = day && day.time_entries.length > 0;
        const res = await apiClient.post('/absences', {
          user_id: userId,
          date: dateStr,
          type: editState.entryType,
          hours: parseHours(editState.absenceHours),
          reason_id: editState.reasonId ?? null, // #312
          keep_time_entries: hasExistingEntries,
        });
        // #376: weiche Kind-krank-Limit-Warnung (§45 SGB V), non-blocking
        showArbzgWarnings(toast, collectAbsenceWarnings(res.data));
      }
      toast.success('Eintrag hinzugefügt');
      cancelEdit();
      setReloadKey(k => k + 1);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSaving(false);
    }
  }

  /**
   * U1 (Audit 2026-07-31): ein Typwechsel lief als ZWEI getrennt committende
   * Aufrufe — erst DELETE, dann POST. Scheiterte der zweite Schritt (400
   * Beschäftigungsfenster, 400 freier Sondertag, 409 Misch-Tag) oder brach die
   * Pflichtfeld-Prüfung NACH dem DELETE ab, war der Datensatz weg; der
   * `catch`-Zweig zeigte nur eine Meldung und liess den gelöschten Eintrag
   * weiter auf dem Bildschirm stehen. Drei Änderungen:
   *
   * 1. Die Pflichtfeld-Prüfung läuft VOR jedem schreibenden Aufruf (und vor
   *    `setSaving`) — sie kann keinen Löschvorgang mehr hinterlassen. Der
   *    Bearbeitungsmodus bleibt hier bewusst offen: es wurde nichts verändert,
   *    und der/die Bearbeitende soll das fehlende Feld nachtragen können, ohne
   *    die Eingaben zu verlieren.
   * 2. Wo es trägt, wird der ATOMARE Serverweg genutzt: `POST /absences` löscht
   *    kollidierende Zeiteinträge in DERSELBEN Transaktion
   *    (`keep_time_entries: false`, mit Audit-Log `absence_creation`). Das
   *    greift, wenn am Tag kein weiterer Zeiteintrag stehen bleiben soll — der
   *    Regelfall. Bleiben andere Einträge stehen, kennt der Server nur
   *    „alle oder keinen"; dann muss der eine bearbeitete Eintrag weiterhin
   *    vorab gelöscht werden. Beim Wechsel Abwesenheit -> Arbeit ist die
   *    Reihenfolge umgedreht (erst schreiben, dann die Abwesenheit löschen):
   *    scheitert das Schreiben, ist nichts verloren; ein Tag mit beidem ist
   *    zulässig (Misch-Tag) und sofort sichtbar korrigierbar.
   * 3. Jeder Fehlschlag beendet den Bearbeitungsmodus und lädt neu, damit der
   *    Bildschirm den Wahrheitsstand zeigt. Eine LEERE Antwort auf
   *    `POST /absences` gilt als Fehler (die Serverseite antwortet dafür seit
   *    dem Audit mit 400 — die Prüfung hier deckt ältere Backends ab).
   */
  async function handleAdminSave(day: JournalDay) {
    const hadTimeEntry = day.time_entries.length > 0;
    const hadAbsence = day.absences.length > 0;
    const switchingToAbsence = hadTimeEntry && editState.entryType !== 'work';
    const switchingToWork = hadAbsence && editState.entryType === 'work';
    const editedEntry = editingEntryId ? day.time_entries.find(e => e.id === editingEntryId) : day.time_entries[0];

    // (1) Pflichtfeld-Prüfung VOR jedem schreibenden Aufruf.
    if (editState.entryType === 'work' && (!editState.startTime || !editState.endTime)) {
      toast.error('Von und Bis sind Pflichtfelder');
      return;
    }

    setSaving(true);
    try {
      if (editState.entryType === 'work') {
        const payload = {
          start_time: editState.startTime,
          end_time: editState.endTime,
          break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
        };
        const existing = !switchingToWork ? editedEntry : null;
        // #200: §4-Pausen-Ausnahme per Retry mit dokumentierter Begründung.
        const res = await submitWithBreakWaiver(async (extra) =>
          existing
            ? apiClient.put(`/admin/time-entries/${existing.id}`, { ...payload, ...extra })
            : apiClient.post(`/admin/users/${userId}/time-entries`, { date: day.date, ...payload, ...extra }),
        );
        // (2) Die Abwesenheit ERST nach erfolgreichem Schreiben entfernen.
        if (switchingToWork && day.absences[0]) {
          await apiClient.delete(`/absences/${day.absences[0].id}`);
        }
        // ArbZG-Warnungen der Admin-Schreibpfade anzeigen (§3 >8h/Tag, >48h/Woche,
        // §6 Nacht, BREAK_WAIVER) — analog zu den MA-Pfaden (StampWidget/TimeTracking).
        showArbzgWarnings(toast, res.data?.warnings);
      } else {
        const remainingEntries = day.time_entries.filter(e => e.id !== editingEntryId);
        // (2) Atomarer Weg, wenn am Tag kein Zeiteintrag stehen bleiben soll.
        const serverDropsEntries = switchingToAbsence && remainingEntries.length === 0;
        if (switchingToAbsence && !serverDropsEntries && editedEntry) {
          await apiClient.delete(`/admin/time-entries/${editedEntry.id}`);
        }
        // Eine bestehende Abwesenheit ANDEREN Typs muss weichen — der POST würde
        // sonst mit 409 abgelehnt (ein Ersetzen kennt der Endpunkt nicht).
        if (hadAbsence && day.absences[0]) {
          await apiClient.delete(`/absences/${day.absences[0].id}`);
        }
        const res = await apiClient.post('/absences', {
          user_id: userId,
          date: day.date,
          type: editState.entryType,
          hours: parseHours(editState.absenceHours),
          reason_id: editState.reasonId ?? null, // #312
          keep_time_entries: !serverDropsEntries && remainingEntries.length > 0,
        });
        // (3) „Erfolg" ohne angelegte Zeile ist keiner.
        if (!Array.isArray(res.data) || res.data.length === 0) {
          const empty = new Error(
            'Es wurde keine Abwesenheit angelegt — am Zieltag sind keine Arbeitsstunden geplant.',
          ) as Error & { response?: { data: { detail: string } } };
          // Form wie ein API-Fehler, damit getErrorMessage den Klartext zeigt.
          empty.response = { data: { detail: empty.message } };
          throw empty;
        }
        // #376: weiche Kind-krank-Limit-Warnung (§45 SGB V), non-blocking
        showArbzgWarnings(toast, collectAbsenceWarnings(res.data));
      }
      toast.success('Gespeichert');
      cancelEdit();
      setReloadKey(k => k + 1);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
      // (3) Wahrheitsstand herstellen: der Bildschirm darf nach einem
      // Fehlschlag keinen Stand mehr zeigen, den es so nicht (mehr) gibt.
      cancelEdit();
      setReloadKey(k => k + 1);
    } finally {
      setSaving(false);
    }
  }

  function handleAdminDelete(day: JournalDay) {
    const timeEntry = editingEntryId ? day.time_entries.find(e => e.id === editingEntryId) : day.time_entries[0];
    const absence = !editingEntryId ? day.absences[0] : null; // nur löschen wenn kein spezifischer Eintrag editiert wird
    if (!timeEntry && !absence) return;
    confirm({
      title: 'Eintrag löschen',
      message: 'Soll dieser Eintrag wirklich gelöscht werden?',
      variant: 'danger',
      confirmLabel: 'Löschen',
      onConfirm: async () => {
        setSaving(true);
        try {
          if (timeEntry) {
            await apiClient.delete(`/admin/time-entries/${timeEntry.id}`);
          }
          if (absence) {
            await apiClient.delete(`/absences/${absence.id}`);
          }
          toast.success('Eintrag gelöscht');
          cancelEdit();
          setReloadKey(k => k + 1);
        } catch (err: unknown) {
          toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
        } finally {
          setSaving(false);
        }
      },
    });
  }

  function startEmployeeSubmit(day: JournalDay) {
    if (editState.entryType === 'work') {
      if (!editState.startTime || !editState.endTime) {
        toast.error('Von und Bis sind Pflichtfelder');
        return;
      }
    }
    setSubmittingDate(day.date);
    setSubmitReason('');
  }

  async function confirmEmployeeSubmit(day: JournalDay) {
    if (!submitReason.trim()) {
      toast.error('Bitte eine Begründung angeben');
      return;
    }
    setSavingChangeRequest(true);
    try {
      let payload: Record<string, unknown>;

      if (editState.entryType === 'work') {
        // TimeEntry CR (existing logic)
        const existing = editingEntryId ? day.time_entries.find(e => e.id === editingEntryId) : day.time_entries[0];
        payload = {
          request_type: existing ? 'update' : 'create',
          entry_kind: 'time_entry',
          reason: submitReason.trim(),
          proposed_date: day.date,
          proposed_start_time: editState.startTime,
          proposed_end_time: editState.endTime,
          proposed_break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
        };
        if (existing) payload.time_entry_id = existing.id;
      } else {
        // Absence CR
        payload = {
          request_type: 'create',
          entry_kind: 'absence',
          reason: submitReason.trim(),
          proposed_date: day.date,
          proposed_absence_type: editState.entryType,
          proposed_absence_hours: parseHours(editState.absenceHours),
          reason_id: editState.reasonId ?? null, // #312
        };
      }

      await apiClient.post('/change-requests/', payload);
      toast.success('Änderungsantrag eingereicht');
      setSubmittingDate(null);
      cancelEdit();
      setReloadKey(k => k + 1);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Einreichen'));
    } finally {
      setSavingChangeRequest(false);
    }
  }

  function handleEmployeeDelete(day: JournalDay) {
    const entry = day.time_entries?.[0];
    if (!entry) return;
    confirm({
      title: 'Lösch-Antrag stellen',
      message: 'Einen Lösch-Antrag für diesen Eintrag einreichen?',
      confirmLabel: 'Antrag stellen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.post('/change-requests/', {
            request_type: 'delete',
            time_entry_id: entry.id,
            reason: 'Eintrag fehlerhaft erfasst',
          });
          toast.success('Lösch-Antrag eingereicht');
          cancelEdit();
          setReloadKey(k => k + 1);
        } catch (err) {
          toast.error(getErrorMessage(err, 'Fehler'));
        }
      },
    });
  }


  return (
    <div className="space-y-4">
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <MonthSelector
        value={selectedMonth}
        onChange={(month) => {
          setSelectedMonth(month);
          cancelEdit();
        }}
      />

      {loading && <LoadingSpinner />}
      {error && <p className="text-red-600">{error}</p>}

      {data && !loading && (
        <>
          {/* #463: Feste Monatsarbeitszeit — die Tageszeilen sind hier keine
              Soll/Ist-Abrechnung, sondern eine Anwesenheitsübersicht. Ohne
              diesen Hinweis liest man die Spalten als verbindliche Zahlen und
              schließt aus einem Urlaubstag ohne Sollstunden auf einen
              Rechenfehler (genau die Meldung, die das Ticket ausgelöst hat). */}
          {fixedMode && (
            <p className="mb-3 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-xs text-blue-800">
              <strong>Feste Monatsarbeitszeit aktiv.</strong> Die Tageszeilen zeigen die{' '}
              <strong>geplante</strong> Anwesenheit und die tatsächlich erfassten Stunden —
              ein Tages-Soll gibt es in diesem Modus nicht, deshalb entfällt auch der
              Tages-Saldo. Verbindlich ist die <strong>Monatsübersicht</strong> unter der Tabelle.
            </p>
          )}

          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-2 text-left">Datum</th>
                  <th className="px-3 py-2 text-left hidden sm:table-cell">Tag</th>
                  <th className="px-3 py-2 text-left">Typ</th>
                  <th className="px-3 py-2 text-left hidden md:table-cell">Von–Bis</th>
                  <th className="px-3 py-2 text-right hidden md:table-cell">Pause</th>
                  <th className="px-3 py-2 text-right">Ist</th>
                  <th className="px-3 py-2 text-right">{fixedMode ? 'Geplant' : 'Soll'}</th>
                  {!fixedMode && <th className="px-3 py-2 text-right">Saldo</th>}
                  <th className="px-3 py-2 text-right w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.days.map((day) => {
                  const dateObj = safeParseISO(day.date);
                  const isGray = isNonWorkDay(day);

                  const rowClass = isGray
                    ? 'bg-gray-50 text-gray-400'
                    : 'bg-white';

                  const balanceColor =
                    isGray || day.type === 'empty'
                      ? 'text-gray-400'
                      : day.balance > 0
                      ? 'text-green-600 font-medium'
                      : day.balance < 0
                      ? 'text-red-600 font-medium'
                      : 'text-gray-600';

                  return (
                    <React.Fragment key={day.date}>
                      <tr className={`${rowClass} hover:bg-gray-50 transition-colors`}>
                        <td className="px-3 py-2 font-medium whitespace-nowrap">
                          {dateObj ? format(dateObj, 'dd.MM.', { locale: de }) : day.date}
                        </td>
                        <td className="px-3 py-2 hidden sm:table-cell">
                          {dateObj ? format(dateObj, 'EEE', { locale: de }) : ''}
                        </td>
                        <td className={`px-3 py-2 ${TYPE_COLORS[day.type]}`}>
                          {editingDate === day.date && isAdminView ? (
                            <select
                              value={editState.reasonId ? `reason:${editState.reasonId}` : editState.entryType}
                              onChange={(e) => {
                                const v = e.target.value;
                                if (v.startsWith('reason:')) {
                                  // a custom reason is always an absence — force the absence path
                                  setEditState(s => ({ ...s, reasonId: v.slice('reason:'.length), entryType: s.entryType === 'work' ? 'other' : s.entryType }));
                                } else {
                                  setEditState(s => ({ ...s, entryType: v as EditState['entryType'], reasonId: null }));
                                }
                              }}
                              className="border border-gray-300 rounded-sm px-1 py-0.5 text-sm"
                            >
                              <option value="work">Arbeit</option>
                              <option value="sick">Krank</option>
                              <option value="training">Fortbildung</option>
                              <option value="overtime">ÜSt-Ausgleich</option>
                              <option value="other">Sonstiges</option>
                              {reasons.length > 0 && (
                                <optgroup label="Eigene Gründe">
                                  {reasons.map(r => (
                                    <option key={r.id} value={`reason:${r.id}`}>{r.name}</option>
                                  ))}
                                </optgroup>
                              )}
                            </select>
                          ) : (
                            <>
                              {day.is_holiday && day.holiday_name
                                ? day.holiday_name
                                : (day.time_entries.length > 1 || day.type === 'mixed') ? (
                                  <div className="space-y-0.5">
                                    {day.time_entries.map((_, i) => (
                                      <div key={`w${i}`} className="text-gray-900">Arbeitszeit</div>
                                    ))}
                                    {day.absences.map((a, i) => (
                                      <div key={`a${i}`} className={TYPE_COLORS[a.type] || 'text-gray-600'}>
                                        {TYPE_LABELS[a.type] || a.type}
                                      </div>
                                    ))}
                                  </div>
                                ) : TYPE_LABELS[day.type] ?? day.type}
                            </>
                          )}
                        </td>
                        <td className="px-3 py-2 hidden md:table-cell text-gray-600 whitespace-nowrap">
                          {isGray ? '–' : editingDate === day.date ? (
                            editState.entryType === 'work' ? (
                              <div className="flex items-center gap-1">
                                <input
                                  type="time"
                                  value={editState.startTime}
                                  onChange={(e) => setEditState(s => ({ ...s, startTime: e.target.value }))}
                                  className="w-22 border border-gray-300 rounded-sm px-1 py-0.5 text-sm"
                                />
                                <span className="text-gray-400">–</span>
                                <input
                                  type="time"
                                  value={editState.endTime}
                                  onChange={(e) => setEditState(s => ({ ...s, endTime: e.target.value }))}
                                  className="w-22 border border-gray-300 rounded-sm px-1 py-0.5 text-sm"
                                />
                              </div>
                            ) : (
                              <input
                                type="number"
                                step="0.5"
                                min={0}
                                max={24}
                                value={editState.absenceHours}
                                onChange={(e) => setEditState(s => ({ ...s, absenceHours: e.target.value }))}
                                className="w-20 border border-gray-300 rounded-sm px-1 py-0.5 text-sm"
                                placeholder="Stunden"
                              />
                            )
                          ) : day.time_entries.length > 0 || (day.type === 'mixed' && day.absences.length > 0) ? (
                            <div className="space-y-0.5">
                              {day.time_entries.map((e, i) => (
                                <div key={`w${i}`}>
                                  {e.start_time && e.end_time ? `${e.start_time.substring(0, 5)}–${e.end_time.substring(0, 5)}` : '–'}
                                  <RawStampNote raw={e.raw_start_time} effective={e.start_time} side="start" className="text-xs text-gray-500" />
                                  <RawStampNote raw={e.raw_end_time} effective={e.end_time} side="end" className="text-xs text-gray-500" />
                                </div>
                              ))}
                              {day.type === 'mixed' && day.absences.map((a, i) => (
                                <div key={`a${i}`} className="text-gray-400">
                                  {a.start_time && a.end_time
                                    ? `${a.start_time}–${a.end_time}`
                                    : 'ganzer Tag'}
                                </div>
                              ))}
                            </div>
                          ) : day.absences.length > 0 ? (
                            <div className="space-y-0.5">
                              {day.absences.map((a, i) => (
                                <div key={`a${i}`} className="text-gray-400">
                                  {a.start_time && a.end_time
                                    ? `${a.start_time}–${a.end_time}`
                                    : 'ganzer Tag'}
                                </div>
                              ))}
                            </div>
                          ) : '–'}
                        </td>
                        <td className="px-3 py-2 hidden md:table-cell text-right text-gray-500">
                          {isGray ? '' : editingDate === day.date && editState.entryType === 'work' ? (
                            <input
                              type="number"
                              inputMode="numeric"
                              min={0}
                              max={480}
                              value={editState.breakMinutes}
                              onChange={(e) => setEditState(s => ({ ...s, breakMinutes: e.target.value }))}
                              className="w-16 border border-gray-300 rounded-sm px-1 py-0.5 text-sm text-right"
                            />
                          ) : editingDate === day.date ? '' : day.time_entries.length > 0 || (day.type === 'mixed' && day.absences.length > 0) ? (
                            <div className="space-y-0.5">
                              {day.time_entries.map((e, i) => (
                                <div key={`w${i}`}>
                                  {e.break_minutes > 0 ? `${e.break_minutes} min` : '–'}
                                </div>
                              ))}
                              {day.type === 'mixed' && day.absences.map((_, i) => (
                                <div key={`a${i}`}>–</div>
                              ))}
                            </div>
                          ) : '–'}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">
                          {isGray ? '' : formatHoursSimple(day.actual_hours)}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-500">
                          {isGray ? '' : formatHoursSimple(day.target_hours)}
                        </td>
                        {!fixedMode && (
                          <td className={`px-3 py-2 text-right ${balanceColor}`}>
                            {isGray ? '' : formatHours(day.balance)}
                          </td>
                        )}
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {editingDate === day.date ? (
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => isAdminView ? void handleAdminSave(day) : startEmployeeSubmit(day)}
                                disabled={saving}
                                className="p-2.5 text-green-600 hover:text-green-800 disabled:opacity-50"
                                title="Speichern"
                              >
                                <Check size={15} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                disabled={saving}
                                className="p-2.5 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                                title="Abbrechen"
                              >
                                <X size={15} />
                              </button>
                              {(day.time_entries.length > 0 || day.absences.length > 0) && (
                                <button
                                  onClick={() => isAdminView ? void handleAdminDelete(day) : handleEmployeeDelete(day)}
                                  disabled={saving}
                                  className="p-2.5 text-red-400 hover:text-red-600 disabled:opacity-50"
                                  title="Löschen"
                                >
                                  <Trash2 size={15} />
                                </button>
                              )}
                            </div>
                          ) : !isGray && (isAdminView ? !isFutureDay(day.date) : isPastDay(day.date)) ? (
                            <div className="flex flex-col items-end">
                              {(day.time_entries.length > 0 || day.absences.length > 0) ? (
                                <div className="space-y-0.5">
                                  {day.time_entries.map((e) => (
                                    <div key={e.id} className="flex items-center justify-end gap-0.5">
                                      <button
                                        onClick={() => startEdit(day, e)}
                                        className="p-1.5 text-gray-400 hover:text-gray-600"
                                        title={`${e.start_time}–${e.end_time} bearbeiten`}
                                      >
                                        <Pencil size={13} />
                                      </button>
                                    </div>
                                  ))}
                                  {day.absences.map((a) => (
                                    <div key={a.id} className="flex items-center justify-end gap-0.5">
                                      <button
                                        onClick={() => startEdit(day)}
                                        className="p-1.5 text-gray-400 hover:text-gray-600"
                                        title={`${TYPE_LABELS[a.type] || a.type} bearbeiten`}
                                      >
                                        <Pencil size={13} />
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              ) : null}
                              {isAdminView && (
                                <button
                                  onClick={() => startAdd(day)}
                                  className="p-1.5 text-blue-400 hover:text-blue-600"
                                  title="Weiteren Eintrag hinzufügen"
                                >
                                  <Plus size={13} />
                                </button>
                              )}
                              {!isAdminView && day.time_entries.length === 0 && day.absences.length === 0 && (
                                <button
                                  onClick={() => startEdit(day)}
                                  className="p-2 text-blue-400 hover:text-blue-600"
                                  title="Eintrag anlegen"
                                >
                                  <Plus size={14} />
                                </button>
                              )}
                            </div>
                          ) : null}
                        </td>
                      </tr>
                      {/* Add-new-entry row */}
                      {addingDate === day.date && isAdminView && (
                        <tr key={`${day.date}-add`} className="bg-green-50">
                          <td className="px-3 py-2"></td>
                          <td className="px-3 py-2 hidden sm:table-cell"></td>
                          <td className="px-3 py-2">
                            <select
                              value={editState.reasonId ? `reason:${editState.reasonId}` : editState.entryType}
                              onChange={(e) => {
                                const v = e.target.value;
                                if (v.startsWith('reason:')) {
                                  // a custom reason is always an absence — force the absence path
                                  setEditState(s => ({ ...s, reasonId: v.slice('reason:'.length), entryType: s.entryType === 'work' ? 'other' : s.entryType }));
                                } else {
                                  setEditState(s => ({ ...s, entryType: v as EditState['entryType'], reasonId: null }));
                                }
                              }}
                              className="border border-gray-300 rounded-sm px-1 py-0.5 text-sm"
                            >
                              <option value="work">Arbeit</option>
                              <option value="sick">Krank</option>
                              <option value="training">Fortbildung</option>
                              <option value="overtime">ÜSt-Ausgleich</option>
                              <option value="other">Sonstiges</option>
                              {reasons.length > 0 && (
                                <optgroup label="Eigene Gründe">
                                  {reasons.map(r => (
                                    <option key={r.id} value={`reason:${r.id}`}>{r.name}</option>
                                  ))}
                                </optgroup>
                              )}
                            </select>
                          </td>
                          <td className="px-3 py-2 hidden md:table-cell">
                            {editState.entryType === 'work' ? (
                              <div className="flex items-center gap-1">
                                <input type="time" value={editState.startTime} onChange={(e) => setEditState(s => ({ ...s, startTime: e.target.value }))} className="w-22 border border-gray-300 rounded-sm px-1 py-0.5 text-sm" />
                                <span className="text-gray-400">–</span>
                                <input type="time" value={editState.endTime} onChange={(e) => setEditState(s => ({ ...s, endTime: e.target.value }))} className="w-22 border border-gray-300 rounded-sm px-1 py-0.5 text-sm" />
                              </div>
                            ) : (
                              <input type="number" step="0.5" min={0} max={24} value={editState.absenceHours} onChange={(e) => setEditState(s => ({ ...s, absenceHours: e.target.value }))} className="w-20 border border-gray-300 rounded-sm px-1 py-0.5 text-sm" placeholder="Stunden" />
                            )}
                          </td>
                          <td className="px-3 py-2 hidden md:table-cell text-right">
                            {editState.entryType === 'work' && (
                              <input type="number" min={0} max={480} value={editState.breakMinutes} onChange={(e) => setEditState(s => ({ ...s, breakMinutes: e.target.value }))} className="w-16 border border-gray-300 rounded-sm px-1 py-0.5 text-sm text-right" />
                            )}
                          </td>
                          {/* Release-Review 1.19.0: Ist + Soll + Saldo — im
                              Fix-Modus entfaellt der Saldo, sonst haette diese
                              Zeile eine Zelle mehr als der Tabellenkopf und die
                              Aktionsknoepfe rutschten aus der Spalte. */}
                          <td colSpan={fixedMode ? 2 : 3}></td>
                          <td className="px-3 py-2 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1">
                              <button onClick={() => void handleAdminAdd(day.date, day)} disabled={saving} className="p-2.5 text-green-600 hover:text-green-800 disabled:opacity-50" title="Hinzufügen"><Check size={15} /></button>
                              <button onClick={cancelEdit} disabled={saving} className="p-2.5 text-gray-400 hover:text-gray-600 disabled:opacity-50" title="Abbrechen"><X size={15} /></button>
                            </div>
                          </td>
                        </tr>
                      )}
                      {submittingDate === day.date && !isAdminView && (
                        <tr key={`${day.date}-reason`} className="bg-blue-50">
                          <td colSpan={fixedMode ? 8 : 9} className="px-3 py-2">
                            <div className="flex flex-wrap gap-2 items-center">
                              <input
                                type="text"
                                value={submitReason}
                                onChange={(e) => setSubmitReason(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') void confirmEmployeeSubmit(day); }}
                                placeholder="Begründung eingeben (Pflicht)"
                                className="flex-1 min-w-0 px-2 py-1 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                                autoFocus
                              />
                              <button
                                onClick={() => void confirmEmployeeSubmit(day)}
                                disabled={!submitReason.trim() || savingChangeRequest}
                                className="px-3 py-1 text-sm bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50"
                              >
                                {savingChangeRequest ? '…' : 'Absenden'}
                              </button>
                              <button
                                onClick={() => setSubmittingDate(null)}
                                className="px-3 py-1 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
                              >
                                Abbrechen
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Aggregates */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Ist (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.actual_hours)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Soll (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.target_hours)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.monthly_summary.balance >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Saldo (Monat)</p>
              <p className={`text-lg font-semibold ${data.monthly_summary.balance >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                {formatHours(data.monthly_summary.balance)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.yearly_overtime >= 0 ? 'bg-blue-50' : 'bg-orange-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Überstunden (kumuliert)</p>
              <p className={`text-lg font-semibold ${data.yearly_overtime >= 0 ? 'text-blue-700' : 'text-orange-700'}`}>
                {formatHours(data.yearly_overtime)}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
