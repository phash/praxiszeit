import { useState, useEffect, useMemo } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Plus, X, Trash2 } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useConfirm } from '../../../hooks/useConfirm';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours, deHoursExact, formatDayPlan } from '../../../utils/formatters';

// #431: Eine Zeile der Historie ist ein vollstaendiger Vertrags-Snapshot ab
// `effective_from` — Modus, Tageswerte, Arbeitstage und Wochenstunden. Die
// Snapshot-Felder sind optional typisiert, weil eine ganz alte Antwort (oder
// ein Testdouble) sie nicht tragen muss; aufgeloest wird ueber
// `scheduleFromChange`.
interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  use_daily_schedule?: boolean;
  hours_monday?: number | null;
  hours_tuesday?: number | null;
  hours_wednesday?: number | null;
  hours_thursday?: number | null;
  hours_friday?: number | null;
  work_days_per_week?: number | null;
  note?: string;
  created_at: string;
}

// Task 7 (#Wochenstunden-anpassen): Antwortform von
// GET .../working-hours-changes/preview — strikt lesend, schreibt nichts.
interface WorkingHoursChangePreview {
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  // #431: Tagessoll je Wochentag (Mo…Fr, immer fuenf Eintraege) vor und nach
  // der Aenderung. Ein Skalar bildet einen individuellen Tagesplan nicht ab.
  day_targets_current: number[];
  day_targets_new: number[];
  // #431: Ueberstundensaldo (Stichtag #313) und verbrauchte Urlaubstage des
  // Jahres von `period_start` — im Ist-Zustand und im simulierten Zustand nach
  // dem Speichern.
  overtime_before: number;
  overtime_after: number;
  vacation_days_before: number;
  vacation_days_after: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
}

interface WorkingHoursModalProps {
  userId: string;
  userName: string;
  currentWeeklyHours: number;
  // #431: der Rest des aktuell gueltigen Snapshots. Optional mit Defaults, weil
  // sie nur der RUECKFALL fuer den (seltenen) Fall „noch keine Historie" sind —
  // sobald der Verlauf geladen ist, gewinnt er (siehe `scheduleAt`).
  currentUseDailySchedule?: boolean;
  currentDayHours?: (number | null)[];
  currentWorkDays?: number;
  onClose: () => void;
  onChanged: () => void;
}

// #431: Die fuenf Wochentagsfelder an EINER Stelle — Feldname (= API-Feld),
// Beschriftung des Eingabefelds und Kurzform fuer Verlauf/Vorschau.
const DAY_FIELDS = [
  { key: 'hours_monday', label: 'Montag', short: 'Mo' },
  { key: 'hours_tuesday', label: 'Dienstag', short: 'Di' },
  { key: 'hours_wednesday', label: 'Mittwoch', short: 'Mi' },
  { key: 'hours_thursday', label: 'Donnerstag', short: 'Do' },
  { key: 'hours_friday', label: 'Freitag', short: 'Fr' },
] as const;

type DayFieldKey = typeof DAY_FIELDS[number]['key'];

const NO_DAY_HOURS: (number | null)[] = [null, null, null, null, null];

// U+2212 MINUS SIGN — nicht der Bindestrich: „−47,5 h" steht in einer Spalte
// neben „+41,5 h", da muss das Vorzeichen auf einen Blick lesbar sein.
const MINUS_SIGN = '−';

/** #431: der Vertrags-Snapshot, wie ihn Dialog und Backend gleichermaßen sehen. */
interface ScheduleSnapshot {
  weekly_hours: number;
  use_daily_schedule: boolean;
  /** Fünf Werte, Index 0 = Montag. 0 = kein geplanter Arbeitstag (wie `null`). */
  day_hours: number[];
  work_days_per_week: number;
}

interface FormState {
  effective_from: string;
  weekly_hours: number;
  use_daily_schedule: boolean;
  hours_monday: number;
  hours_tuesday: number;
  hours_wednesday: number;
  hours_thursday: number;
  hours_friday: number;
  work_days_per_week: number;
  note: string;
}

function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

function normaliseDayHours(values: (number | null | undefined)[]): number[] {
  return DAY_FIELDS.map((_, i) => {
    const v = values[i];
    return typeof v === 'number' && Number.isFinite(v) ? v : 0;
  });
}

/** Die fünf Tageswerte eines Snapshots als Formularfelder. */
function dayFieldsFromSnapshot(dayHours: number[]): Record<DayFieldKey, number> {
  return {
    hours_monday: dayHours[0],
    hours_tuesday: dayHours[1],
    hours_wednesday: dayHours[2],
    hours_thursday: dayHours[3],
    hours_friday: dayHours[4],
  };
}

function scheduleFromChange(change: WorkingHoursChange, fallbackWorkDays: number): ScheduleSnapshot {
  return {
    weekly_hours: change.weekly_hours,
    use_daily_schedule: !!change.use_daily_schedule,
    day_hours: normaliseDayHours([
      change.hours_monday, change.hours_tuesday, change.hours_wednesday,
      change.hours_thursday, change.hours_friday,
    ]),
    // NULL heißt beim Backend „Rückfall auf die User-Zeile" (Bestandszeilen vor
    // #431) — hier ist das die Prop.
    work_days_per_week: change.work_days_per_week ?? fallbackWorkDays,
  };
}

// Fund 3 (Release-Review 1.17.0), #431 erweitert: der zu einem Datum gültige
// Snapshot wird NICHT aus den Props übernommen (die sind ein Stand von vor dem
// Öffnen des Dialogs und werden von Users.tsx nach dem Speichern nicht
// nachgezogen — der Dialog bleibt offen), sondern aus dem gerade geladenen
// Verlauf abgeleitet: die jüngste Zeile mit `effective_from <= datum` gilt.
// Genau die Auflösung, die `calculation_service.get_schedule_for_date`
// backendseitig macht.
function scheduleAt(
  changes: WorkingHoursChange[], iso: string, fallback: ScheduleSnapshot,
): ScheduleSnapshot {
  let latest: WorkingHoursChange | null = null;
  for (const c of changes) {
    if (c.effective_from <= iso && (!latest || c.effective_from > latest.effective_from)) {
      latest = c;
    }
  }
  return latest ? scheduleFromChange(latest, fallback.work_days_per_week) : fallback;
}

/**
 * #431: Der Snapshot als Klartext — für die Kopfzeile und jede Verlaufszeile.
 *
 * Formuliert wie der Datei-Export (`export_service.format_weekly_hours_history`
 * / `utils/formatters.ts::formatWeeklyHoursChanges`): Bildschirm und §16-Beleg
 * müssen denselben Satz schreiben.
 */
function describeSchedule(s: ScheduleSnapshot): string {
  const days = `${s.work_days_per_week} Tage/Woche`;
  if (s.use_daily_schedule) {
    const plan = formatDayPlan(s.day_hours);
    // Kein einziger Tageswert → gleichmäßige Formulierung statt leerem Satz.
    if (plan) return `${plan} = ${deHoursExact(s.weekly_hours)} Std/Woche · ${days}`;
  }
  return `${deHoursExact(s.weekly_hours)} Std/Woche · ${days}`;
}

/**
 * #431: Vergleichsform des Snapshots — DIE eine Definition von „hat sich
 * etwas geändert" im Dialog, gebaut wie `admin_users._comparable_snapshot`.
 *
 * Im gleichmäßigen Modus sind die Tageswerte inert (das Tagessoll liest sie
 * dort nicht) und werden ausgeblendet, sonst würde ein Rest aus einer früheren
 * Tagesplan-Phase eine Änderung vortäuschen.
 */
function comparableSnapshot(s: ScheduleSnapshot): string {
  return JSON.stringify([
    round2(s.weekly_hours),
    s.use_daily_schedule,
    s.use_daily_schedule ? s.day_hours.map(round2) : [0, 0, 0, 0, 0],
    s.work_days_per_week,
  ]);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/** #431: '+41,5' / '−47,5' / '0,0' — Vorzeichen vor der DE-Schreibweise. */
function signed(value: number): string {
  const v = round2(value);
  const text = deHoursExact(Math.abs(v));
  if (v > 0) return `+${text}`;
  if (v < 0) return `${MINUS_SIGN}${text}`;
  return text;
}

// Kalendertag VOR dem übergebenen ISO-Datum (YYYY-MM-DD) — UTC-basiert, um
// Zeitzonen-/DST-Rollover bei reiner Tagesarithmetik zu vermeiden.
function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}

// „Heute" in der LOKALEN Zeitzone des Browsers (= die des Praxis-Rechners,
// faktisch Europe/Berlin) als YYYY-MM-DD.
//
// M1 (Abschluss-Review): NICHT `toISOString()` — das liefert UTC. Zwischen
// 00:00 und 02:00 Berliner Zeit hielt der Dialog damit das GESTRIGE Datum für
// „heute": keine Vorschau, keine Bestätigungspflicht — während das Backend
// (`today_local()`, Europe/Berlin) dasselbe Datum als rückwirkend behandelt und
// die Abwesenheits-Stunden retargetet. Die laut Spezifikation zwingende
// ausdrückliche Bestätigung war damit umgehbar.
//
// (`dayBefore` rechnet weiterhin bewusst in UTC — dort geht es um reine
// Tagesarithmetik auf einem bereits feststehenden Datum, ohne DST-Rollover.)
function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Debounce (ms), bevor die rein lesende Vorschau abgerufen wird, während der
// Admin Datum/Stunden noch anpasst.
const PREVIEW_DEBOUNCE_MS = 400;

export default function WorkingHoursModal({
  userId,
  userName,
  currentWeeklyHours,
  currentUseDailySchedule = false,
  currentDayHours = NO_DAY_HOURS,
  currentWorkDays = 5,
  onClose,
  onChanged,
}: WorkingHoursModalProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  // Guards against double-submit (fast double-click would add duplicate hours changes).
  const [submitting, setSubmitting] = useState(false);

  // Der Snapshot aus den Props — Rückfall, solange (oder falls) es keine
  // Historie gibt.
  const propsSchedule = useMemo<ScheduleSnapshot>(() => ({
    weekly_hours: currentWeeklyHours,
    use_daily_schedule: currentUseDailySchedule,
    day_hours: normaliseDayHours(currentDayHours),
    work_days_per_week: currentWorkDays,
  }), [currentWeeklyHours, currentUseDailySchedule, currentDayHours, currentWorkDays]);

  const [formData, setFormData] = useState<FormState>(() => ({
    effective_from: todayIso(),
    note: '',
    weekly_hours: currentWeeklyHours,
    use_daily_schedule: currentUseDailySchedule,
    ...dayFieldsFromSnapshot(normaliseDayHours(currentDayHours)),
    work_days_per_week: currentWorkDays,
  }));

  // Task 7: rückwirkende Vorschau (Zeitraum, altes/neues Tagessoll, betroffene
  // Abwesenheiten, abgeschlossene Jahre, Blockade-Grund) — siehe Backend
  // GET .../working-hours-changes/preview.
  const [preview, setPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Fund 4 (Release-Review 1.17.0): scheitert die Vorschau (Netzwerk, 5xx, ein
  // getipptes weekly_hours > 60 → 422 …), zeigte der Dialog bisher einen leeren
  // amber Kasten und ein gesperrtes „Hinzufügen" ohne jede Begründung. Jetzt
  // wird der Fehler festgehalten und angezeigt, plus eine Möglichkeit, die
  // Vorschau erneut anzustoßen, ohne Datum/Stunden ändern zu müssen.
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewRetryToken, setPreviewRetryToken] = useState(0);
  // Der Kern des Verständnisproblems: eine rückwirkende Änderung darf erst
  // nach ausdrücklicher Bestätigung der Vorschau gespeichert werden.
  const [confirmedRetroactive, setConfirmedRetroactive] = useState(false);

  const isRetroactive = formData.effective_from < todayIso();

  const dayValues = DAY_FIELDS.map((f) => formData[f.key]);
  const daySum = round2(dayValues.reduce((sum, h) => sum + h, 0));
  const plannedDays = dayValues.filter((h) => h > 0).length;

  // Fund 3: die Kopfzeile hängt an diesem abgeleiteten Wert statt an der (nicht
  // nachgezogenen) Prop.
  const displaySchedule = useMemo(
    () => scheduleAt(hoursChanges, todayIso(), propsSchedule),
    [hoursChanges, propsSchedule],
  );

  // #431: Die Vorschau-Parameter UND der POST-Body kommen aus derselben
  // Funktion — zwei Formulierungen desselben Payloads laufen garantiert
  // auseinander, und die beiden Modi schließen einander serverseitig hart aus
  // (Tageswerte im gleichmäßigen Modus → HTTP 400).
  //
  // Bewusst nur PRIMITIVE Abhängigkeiten: dieses Objekt hängt im
  // Dependency-Array des Vorschau-Effekts. Eine bei jedem Rendern neu erzeugte
  // Identität (z. B. über ein Array wie `dayValues`) würde bei JEDEM Rendern
  // einen Request auslösen.
  const scheduleParams = useMemo<Record<string, string | number | boolean>>(() => {
    if (formData.use_daily_schedule) {
      const days = [
        formData.hours_monday, formData.hours_tuesday, formData.hours_wednesday,
        formData.hours_thursday, formData.hours_friday,
      ];
      const planned = days.filter((h) => h > 0).length;
      const params: Record<string, string | number | boolean> = { use_daily_schedule: true };
      DAY_FIELDS.forEach((f, i) => { params[f.key] = days[i]; });
      // Die Wochensumme setzt der Server (`check_mode`) — ein eigener Wert des
      // Clients könnte ihr widersprechen. Die Arbeitstage ergeben sich aus den
      // Tagen MIT Stunden; ohne einen einzigen bleibt der Rückfall auf die
      // User-Zeile (die Eingabe ist dann ohnehin ungültig und kommt als
      // `blocked_reason` zurück).
      if (planned > 0) params.work_days_per_week = planned;
      return params;
    }
    return {
      use_daily_schedule: false,
      weekly_hours: formData.weekly_hours,
      work_days_per_week: formData.work_days_per_week,
    };
  }, [
    formData.use_daily_schedule, formData.weekly_hours, formData.work_days_per_week,
    formData.hours_monday, formData.hours_tuesday, formData.hours_wednesday,
    formData.hours_thursday, formData.hours_friday,
  ]);

  useEffect(() => {
    fetchHoursChanges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Jede Änderung an Datum/Stunden entwertet eine zuvor gegebene Bestätigung
  // — der Admin muss die (ggf. neue) Vorschau erneut bestätigen.
  //
  // Release-Review 1.17.0: Die Vorschau wird jetzt für JEDES Wirkungsdatum
  // geladen, nicht nur für ein rückwirkendes. Hier stand vorher „ein
  // zukünftiges Datum betrifft ausschließlich noch nicht gebuchte Tage" —
  // das stimmt nicht: genehmigte Urlaubsanträge, Betriebsferien und geplante
  // Fortbildungen sind längst gebucht und werden vom Speichern auf das neue
  // Tagessoll umgeschrieben. Ohne Vorschau passierte das still. Ob ein
  // Warnblock erscheint, entscheidet deshalb nicht mehr das Datum allein,
  // sondern `affected_absences` (siehe `showImpactBox`).
  //
  // #431: Der Effekt hängt jetzt an bis zu acht Formularwerten (Datum, Modus,
  // fünf Tageswerte, Wochenstunden, Arbeitstage) — gebündelt in
  // `scheduleParams`. Der 400-ms-Debounce plus das Aufräumen unten sorgen
  // dafür, dass daraus trotzdem EIN Request je Eingabepause wird und nicht
  // acht parallele.
  useEffect(() => {
    setConfirmedRetroactive(false);
    setPreviewLoading(true);
    setPreviewError(null);
    // Fund 1 (Release-Review 1.17.0): `cancelled` is the same guard UserForm.tsx
    // uses for its carryover fetch (:148/:157). Without it, last-RESPONSE-wins
    // instead of last-REQUEST-wins: a slow answer for a date/hours combination
    // the admin has since navigated away from could still land in `setPreview`
    // after a newer, faster request already resolved — showing a period/
    // Tagessoll/Abwesenheits-Anzahl that doesn't match the change actually
    // about to be saved, right under the mandatory confirmation checkbox.
    // Setting `cancelled = true` in the cleanup (which React runs for the
    // PREVIOUS effect invocation before running the next one, i.e. on EVERY
    // dependency change) discards a stale response regardless of arrival
    // order — out-of-order (B-before-A) is covered exactly like the more
    // common late-A-after-B case.
    let cancelled = false;
    const handle = setTimeout(() => {
      apiClient
        .get(`/admin/users/${userId}/working-hours-changes/preview`, {
          params: { effective_from: formData.effective_from, ...scheduleParams },
        })
        .then((res) => {
          if (cancelled) return;
          setPreview(res.data);
        })
        .catch((error) => {
          if (cancelled) return;
          setPreview(null);
          // Fund 4: surface WHY the preview is unavailable instead of leaving
          // an unexplained empty box + a disabled save button.
          setPreviewError(getErrorMessage(error, 'Auswirkungen konnten nicht geprüft werden'));
        })
        .finally(() => {
          if (cancelled) return;
          setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [userId, formData.effective_from, scheduleParams, previewRetryToken]);

  // Fund 3: gibt die frisch geladene Liste zurück (nicht nur über State), damit
  // handleAddHoursChange den soeben aktualisierten aktiven Wert SOFORT für den
  // Formular-Reset verwenden kann — auf `hoursChanges` selbst wartend würde
  // noch der Wert von vor dem Re-Fetch im Closure stehen (State-Updates sind
  // nicht synchron).
  const fetchHoursChanges = async (): Promise<WorkingHoursChange[]> => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      const list: WorkingHoursChange[] = Array.isArray(response.data) ? response.data : []; // #382
      setHoursChanges(list);
      return list;
    } catch (error) {
      toast.error('Fehler beim Laden der Stundenhistorie');
      return hoursChanges;
    }
  };

  // Task 7: "ab … bis …" statt nur "ab …" — das Ende ergibt sich implizit aus
  // dem jeweils nächsten Eintrag (Vortag), der jüngste Eintrag läuft "bis
  // heute". Genau dieses implizite Ende war der Kern des Verständnisproblems.
  const historyEndDates = useMemo(() => {
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    const map = new Map<string, string | null>();
    asc.forEach((c, idx) => {
      const next = asc[idx + 1];
      map.set(c.id, next ? dayBefore(next.effective_from) : null);
    });
    return map;
  }, [hoursChanges]);

  // I4: Das Backend lehnt das Löschen der FRÜHESTEN Zeile ab, solange spätere
  // existieren — sie verankert den davor gültigen Wert, der sonst nirgends
  // mehr gespeichert ist. Verbieten und trotzdem anbieten ist schlechte
  // Führung: der Löschen-Button ist dort deaktiviert und nennt den Grund.
  // Ist es die EINZIGE Zeile, bleibt das Löschen erlaubt (Backend genauso).
  const lockedEarliestId = useMemo(() => {
    if (hoursChanges.length < 2) return null;
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    return asc[0].id;
  }, [hoursChanges]);

  const LOCKED_EARLIEST_HINT =
    'Die früheste erfasste Stundenänderung verankert den davor gültigen Wert — '
    + 'bitte zuerst die späteren Änderungen löschen.';

  // Release-Review 1.17.0, Nachtrag: `blocked_reason` galt nur für rückwirkende
  // Daten — ein Rest aus der Zeit, als die Vorschau ausschließlich dafür geladen
  // wurde. Jetzt kennt der Dialog auch bei einem Datum ab heute die Fälle, in
  // denen der POST mit 400 abweist (unvollständiger Tagesplan, bereits belegtes
  // Wirkungsdatum). Genau dafür wurde der Mechanismus gebaut: den Grund vorher
  // zeigen, statt den Admin in den 400 laufen zu lassen.
  const blockedReason = preview?.blocked_reason ?? null;
  // Release-Review 1.17.0: Der eigentliche Grund für die Bestätigungspflicht ist
  // nicht „das Datum liegt in der Vergangenheit", sondern „das Speichern
  // schreibt bereits gebuchte, §16-relevante Zeilen um". Das kann ein
  // zukünftiges Wirkungsdatum genauso (bereits genehmigter Urlaub,
  // Betriebsferien, geplante Fortbildung ab diesem Datum) — dann muss der
  // Dialog es anzeigen und bestätigen lassen, statt still zu korrigieren.
  const affectsBookedAbsences = !!preview && !preview.blocked_reason && preview.affected_absences > 0;
  const showImpactBox = isRetroactive || affectsBookedAbsences || !!blockedReason;

  // #431: Was der Admin eingegeben hat — und was zum Wirkungsdatum ohnehin
  // gilt. Sind beide gleich, gibt es nichts zu speichern (das Backend rechnet
  // für diesen Fall bewusst nicht einmal eine Simulation).
  //
  // Verglichen wird gegen den Stand AM WIRKUNGSDATUM, nicht gegen den von
  // heute: „ab 01.03. gelten 20 h" kann eine echte Änderung sein, obwohl heute
  // längst 20 h gelten. Dieselbe Auflösung nutzt der Schreibpfad.
  const inputSchedule: ScheduleSnapshot = {
    weekly_hours: formData.use_daily_schedule ? daySum : formData.weekly_hours,
    use_daily_schedule: formData.use_daily_schedule,
    day_hours: dayValues,
    work_days_per_week: formData.use_daily_schedule
      ? (plannedDays || formData.work_days_per_week)
      : formData.work_days_per_week,
  };
  const baselineSchedule = scheduleAt(hoursChanges, formData.effective_from, propsSchedule);
  const snapshotUnchanged =
    comparableSnapshot(inputSchedule) === comparableSnapshot(baselineSchedule);

  // Solange die Vorschau für ein rückwirkendes Datum noch lädt/fehlt, blockiert
  // oder noch nicht bestätigt ist, bleibt „Hinzufügen" gesperrt — der Nutzer
  // soll nicht ungeprüft in einen 400 laufen (blocked_reason) oder eine
  // rückwirkende Änderung ohne die Vorschau gesehen zu haben speichern.
  //
  // Für ein Datum ab heute hängt die Sperre AUSSCHLIESSLICH an einem positiven
  // Vorschau-Befund — bewusst nicht an `previewLoading`/`!preview`: fällt die
  // Vorschau aus (Netzwerk, 5xx), bleibt das Anlegen einer normalen
  // zukunftsdatierten Änderung wie bisher möglich, statt dauerhaft zu blockieren.
  const saveDisabled =
    submitting ||
    !!blockedReason ||
    snapshotUnchanged ||
    (isRetroactive && (previewLoading || !preview || !confirmedRetroactive)) ||
    (!isRetroactive && affectsBookedAbsences && !confirmedRetroactive);

  const setDayHours = (key: DayFieldKey, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: parseHours(value) }));
  };

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saveDisabled) return;
    setSubmitting(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, {
        effective_from: formData.effective_from,
        note: formData.note,
        ...scheduleParams,
      });
      const freshChanges = await fetchHoursChanges();
      onChanged();
      // Fund 3: der neue aktive Snapshot steht jetzt in `freshChanges` (die
      // gerade gespeicherte Änderung eingeschlossen) — NICHT in den Props, die
      // Users.tsx erst beim nächsten Öffnen des Dialogs neu übergibt. Ohne das
      // sprang das Feld nach dem Speichern auf den ALTEN Wert zurück, obwohl
      // der Verlauf darunter schon den neuen zeigte.
      const active = scheduleAt(freshChanges, todayIso(), propsSchedule);
      setFormData({
        effective_from: todayIso(),
        note: '',
        weekly_hours: active.weekly_hours,
        use_daily_schedule: active.use_daily_schedule,
        ...dayFieldsFromSnapshot(active.day_hours),
        work_days_per_week: active.work_days_per_week,
      });
      setPreview(null);
      setConfirmedRetroactive(false);
      // Task 7: adjusted_absences + warning aus der Antwort mit zurückmelden.
      const created: { adjusted_absences?: number; warning?: string | null } = res.data ?? {};
      let message = 'Stundenänderung erfolgreich hinzugefügt';
      if (created.adjusted_absences) {
        message += ` — ${created.adjusted_absences} Abwesenheit(en) auf das neue Tagessoll umgerechnet`;
      }
      toast.success(message);
      if (created.warning) {
        toast.warning(created.warning);
      }
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Hinzufügen'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteHoursChange = (changeId: string) => {
    confirm({
      title: 'Stundenänderung löschen',
      message: 'Möchten Sie diese Stundenänderung wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          const res = await apiClient.delete(`/admin/users/${userId}/working-hours-changes/${changeId}`);
          await fetchHoursChanges();
          onChanged();
          toast.success('Stundenänderung erfolgreich gelöscht');
          // I3: Berührt die Rückrechnung ein bereits abgeschlossenes Jahr,
          // antwortet das Backend mit 200 + {warning} statt 204 ohne Body
          // (Muster von delete_closure / Urlaubs-Storno). Bei 204 setzt axios
          // data auf '' — der Objekt-Check fängt das ab.
          const body = res?.data;
          const warning = body && typeof body === 'object' ? (body as { warning?: string }).warning : undefined;
          if (warning) {
            toast.warning(warning);
          }
        } catch (error: unknown) {
          // I4: Der Grund kommt vom Backend (z. B. „…verankert den davor
          // gültigen Wert… bitte zuerst die späteren Änderungen löschen") —
          // eine hardcodierte Meldung verschluckte ihn. Parität zum Anlegen.
          toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
        }
      },
    });
  };

  // #431: Tagessoll je Wochentag aus der Vorschau. Nur Tage, an denen VOR oder
  // NACH der Änderung ein Soll steht — ein durchgehend freier Freitag sagt
  // nichts. Bewusst nicht als „geplante Arbeitstage" beschriftet: im
  // gleichmäßigen Modus trägt jeder der fünf Wochentage denselben Wert, so
  // rechnet die Engine.
  const dayTargetText = (() => {
    const before = preview?.day_targets_current;
    const after = preview?.day_targets_new;
    if (!Array.isArray(before) || !Array.isArray(after)) return '';
    const parts = DAY_FIELDS.map((f, i) => {
      const cur = before[i] ?? 0;
      const next = after[i] ?? 0;
      if (cur <= 0 && next <= 0) return null;
      return `${f.short} ${deHoursExact(cur)} → ${deHoursExact(next)}`;
    }).filter((p): p is string => p !== null);
    return parts.length ? `Tagessoll je Wochentag: ${parts.join(' · ')}` : '';
  })();

  const overtimeDelta = preview ? round2(preview.overtime_after - preview.overtime_before) : 0;
  const vacationDelta = preview ? round2(preview.vacation_days_after - preview.vacation_days_before) : 0;
  // Ein zukunftsdatierter Wechsel liefert oft „12,5 → 12,5". Das ist korrekt —
  // der Saldo-Stichtag (#313) liegt vor dem Wirkungsfenster — darf aber nicht
  // als „keine Auswirkung" gelesen werden, während unten Abwesenheiten
  // umgeschrieben werden.
  const balanceUnchangedAhead =
    !!preview && !isRetroactive && overtimeDelta === 0 && vacationDelta === 0;
  const vacationYear = preview ? preview.period_start.slice(0, 4) : '';

  return (
    <>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
        onClick={onClose}
      >
        <FocusTrap
          focusTrapOptions={{
            allowOutsideClick: true,
            escapeDeactivates: true,
            onDeactivate: onClose,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="hours-modal-title"
            className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 id="hours-modal-title" className="text-2xl font-bold text-gray-900">
                  Wochenstunden &amp; Tagesplan
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  {userName} • Aktuell: {describeSchedule(displaySchedule)}
                </p>
              </div>
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700"
                aria-label={`Wochenstunden & Tagesplan für ${userName} schließen`}
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-6">
              {/* Add New Change Form */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Stundenänderung</h3>
                <form onSubmit={handleAddHoursChange} className="space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label htmlFor="wh-effective-from" className="block text-sm font-medium text-gray-700 mb-1">
                        Gültig ab
                      </label>
                      <input
                        id="wh-effective-from"
                        type="date"
                        value={formData.effective_from}
                        onChange={(e) => setFormData({ ...formData, effective_from: e.target.value })}
                        required
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label htmlFor="wh-note" className="block text-sm font-medium text-gray-700 mb-1">
                        Notiz (optional)
                      </label>
                      <input
                        id="wh-note"
                        type="text"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="z.B. Teilzeitänderung"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                      />
                    </div>
                  </div>

                  {/* #431: Modus-Umschalter. Der Wechsel selbst ist eine
                      Vertragsänderung mit Wirkungsdatum — deshalb steht er
                      hier und nicht mehr als Haken im Bearbeiten-Formular. */}
                  <fieldset className="border border-blue-200 rounded-lg p-3 bg-white">
                    <legend className="px-1 text-sm font-medium text-gray-700">
                      Ab diesem Datum gilt
                    </legend>
                    <div className="flex flex-wrap gap-4 mb-3">
                      <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                        <input
                          type="radio"
                          name="wh-mode"
                          checked={!formData.use_daily_schedule}
                          onChange={() => setFormData((prev) => ({ ...prev, use_daily_schedule: false }))}
                          className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                        />
                        Gleichmäßig
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                        <input
                          type="radio"
                          name="wh-mode"
                          checked={formData.use_daily_schedule}
                          onChange={() => setFormData((prev) => ({ ...prev, use_daily_schedule: true }))}
                          className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                        />
                        Nach Tagen
                      </label>
                    </div>

                    {formData.use_daily_schedule ? (
                      <div className="grid grid-cols-5 gap-2">
                        {DAY_FIELDS.map((f) => (
                          <div key={f.key}>
                            <label htmlFor={`wh-${f.key}`} className="block text-xs font-medium text-gray-600 mb-1">
                              {f.label}
                            </label>
                            <input
                              id={`wh-${f.key}`}
                              type="number"
                              step="0.5"
                              min="0"
                              max="24"
                              value={formData[f.key]}
                              onChange={(e) => setDayHours(f.key, e.target.value)}
                              className="w-full px-2 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-sm"
                            />
                          </div>
                        ))}
                        {/* Die Wochensumme rechnet der Server aus denselben
                            Werten (`check_mode`) — hier steht sie in derselben
                            Schreibweise, damit Bildschirm und gespeicherte
                            Zeile nie verschiedene Zahlen nennen. */}
                        <p className="col-span-5 text-sm text-gray-700 mt-1">
                          → {deHoursExact(daySum)} h/Woche · {plannedDays}{' '}
                          {plannedDays === 1 ? 'Arbeitstag' : 'Arbeitstage'}
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label htmlFor="wh-weekly-hours" className="block text-sm font-medium text-gray-700 mb-1">
                            Wochenstunden
                          </label>
                          <input
                            id="wh-weekly-hours"
                            type="number"
                            step="0.5"
                            value={formData.weekly_hours}
                            onChange={(e) => setFormData({ ...formData, weekly_hours: parseHours(e.target.value) })}
                            required
                            min="0"
                            max="60"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label htmlFor="wh-work-days" className="block text-sm font-medium text-gray-700 mb-1">
                            Arbeitstage pro Woche
                          </label>
                          <input
                            id="wh-work-days"
                            type="number"
                            step="1"
                            min="1"
                            max="7"
                            value={formData.work_days_per_week}
                            onChange={(e) => setFormData({
                              ...formData,
                              work_days_per_week: Math.round(parseHours(e.target.value)),
                            })}
                            required
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                          />
                        </div>
                      </div>
                    )}
                  </fieldset>

                  {/* Task 7: Auswirkungs-Hinweis — VOR dem Speichern zeigen, was
                      die Änderung anfasst (Zeitraum, Tagessoll je Wochentag,
                      betroffene Abwesenheiten, Saldo/Urlaub vorher-nachher,
                      abgeschlossenes Jahr), plus Blockade-Grund bzw.
                      Bestätigungspflicht.
                      Release-Review 1.17.0: auch bei einem Datum AB heute, sobald
                      die Vorschau bereits gebuchte Abwesenheiten meldet. */}
                  {showImpactBox && (
                    <div
                      role="status"
                      className={`rounded-lg border p-3 text-sm ${
                        blockedReason || previewError ? 'bg-red-50 border-red-300' : 'bg-amber-50 border-amber-300'
                      }`}
                    >
                      {previewLoading ? (
                        <p className="text-gray-600">Prüfe Auswirkungen…</p>
                      ) : preview ? (
                        <>
                          <p className="font-semibold text-amber-900">
                            {isRetroactive ? 'Rückwirkende Änderung' : 'Betrifft bereits gebuchte Abwesenheiten'}:{' '}
                            {formatDate(preview.period_start)} – {formatDate(preview.period_end)}
                          </p>
                          {dayTargetText && (
                            <p className="text-amber-800 mt-1">{dayTargetText}</p>
                          )}
                          <p className="text-amber-800">
                            {preview.affected_absences} Abwesenheit(en) betroffen.
                          </p>
                          {!blockedReason && (
                            <table className="mt-2 w-full text-amber-900">
                              <thead>
                                <tr className="text-xs uppercase text-amber-700">
                                  <th scope="col" className="text-left font-medium">Auswirkung</th>
                                  <th scope="col" className="text-right font-medium">bisher</th>
                                  <th scope="col" className="text-right font-medium">neu</th>
                                  <th scope="col" className="text-right font-medium">
                                    <span aria-hidden="true">Δ</span>
                                    <span className="sr-only">Änderung</span>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <th scope="row" className="text-left font-medium">Überstunden</th>
                                  <td className="text-right">{`${signed(preview.overtime_before)} h`}</td>
                                  <td className="text-right">{`${signed(preview.overtime_after)} h`}</td>
                                  <td className="text-right font-medium">{`${signed(overtimeDelta)} h`}</td>
                                </tr>
                                <tr>
                                  {/* Die Urlaubszahlen gehören zum Jahr des
                                      Wirkungszeitraums — ohne Jahreszahl liest
                                      man sie als „dieses Jahr". */}
                                  <th scope="row" className="text-left font-medium">{`Urlaub ${vacationYear}`}</th>
                                  <td className="text-right">{`${deHoursExact(preview.vacation_days_before)} Tage`}</td>
                                  <td className="text-right">{`${deHoursExact(preview.vacation_days_after)} Tage`}</td>
                                  <td className="text-right font-medium">{`${signed(vacationDelta)} Tage`}</td>
                                </tr>
                              </tbody>
                            </table>
                          )}
                          {balanceUnchangedAhead && (
                            <p className="text-amber-800 mt-1">
                              Saldo und Urlaub stehen auf dem Stand von heute — die Änderung
                              wirkt erst ab dem {formatDate(formData.effective_from)}. Die oben
                              genannten Abwesenheiten werden trotzdem umgeschrieben.
                            </p>
                          )}
                          {preview.closed_year_warning && (
                            <p className="text-amber-900 font-medium mt-1">{preview.closed_year_warning}</p>
                          )}
                          {blockedReason ? (
                            <p className="text-red-700 font-medium mt-2">{blockedReason}</p>
                          ) : (
                            <label className="flex items-center gap-2 mt-2 text-amber-900 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={confirmedRetroactive}
                                onChange={(e) => setConfirmedRetroactive(e.target.checked)}
                                className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                              />
                              Ich habe die Auswirkungen geprüft und möchte trotzdem speichern
                            </label>
                          )}
                        </>
                      ) : previewError ? (
                        // Fund 4 (Release-Review 1.17.0): vorher `: null` — ein
                        // sichtbar leerer Kasten neben einem gesperrten
                        // „Hinzufügen"-Button, ohne jede Begründung.
                        <>
                          <p className="text-red-700 font-medium">{previewError}</p>
                          <button
                            type="button"
                            onClick={() => setPreviewRetryToken((t) => t + 1)}
                            className="mt-2 text-sm font-medium text-red-700 underline hover:no-underline"
                          >
                            Erneut prüfen
                          </button>
                        </>
                      ) : null}
                    </div>
                  )}

                  {/* Ein gesperrter Button ohne Begründung ist genau der
                      Fund-4-Fehler — der häufigste Grund ist der frisch
                      geöffnete, mit dem aktuellen Stand vorbefüllte Dialog. */}
                  {snapshotUnchanged && !blockedReason && (
                    <p className="text-sm text-gray-600">
                      Noch nichts zu speichern — die Eingabe entspricht dem Stand, der
                      am {formatDate(formData.effective_from)} ohnehin gilt.
                    </p>
                  )}

                  <div>
                    <button
                      type="submit"
                      disabled={saveDisabled}
                      className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Plus size={18} />
                      <span>Hinzufügen</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* History List */}
              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => {
                      const end = historyEndDates.get(change.id);
                      return (
                        <div
                          key={change.id}
                          className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                        >
                          <div>
                            <p className="font-medium text-gray-900">
                              Ab {formatDate(change.effective_from)} bis {end ? formatDate(end) : 'heute'}:{' '}
                              {describeSchedule(scheduleFromChange(change, propsSchedule.work_days_per_week))}
                            </p>
                            {change.note && (
                              <p className="text-sm text-gray-600 mt-1">{change.note}</p>
                            )}
                            <p className="text-xs text-gray-500 mt-1">
                              Erstellt: {new Date(change.created_at).toLocaleDateString('de-DE', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                          {change.id === lockedEarliestId ? (
                            // Der Titel sitzt am umschließenden <span>: ein
                            // disabled <button> feuert keine Hover-Events, der
                            // Tooltip käme dort nie an.
                            <span title={LOCKED_EARLIEST_HINT} className="shrink-0">
                              <button
                                type="button"
                                disabled
                                aria-label="Löschen nicht möglich – früheste Stundenänderung"
                                className="text-gray-300 cursor-not-allowed"
                              >
                                <Trash2 size={18} />
                              </button>
                            </span>
                          ) : (
                            <button
                              onClick={() => handleDeleteHoursChange(change.id)}
                              className="text-red-600 hover:text-red-800"
                              title="Löschen"
                            >
                              <Trash2 size={18} />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Hinweis:</strong> Die Berechnungen von Soll-Stunden berücksichtigen automatisch die
                  historischen Werte. Wenn z.B. jemand ab 15.03. von 20h auf 30h wechselt, werden für den
                  März die ersten 14 Tage mit 20h und ab dem 15. mit 30h berechnet.
                </p>
              </div>
            </div>
          </div>
        </FocusTrap>
      </div>
    </>
  );
}
