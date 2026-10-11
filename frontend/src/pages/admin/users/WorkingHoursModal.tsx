import { useState, useEffect, useMemo } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Save, X, Trash2, Info } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useConfirm } from '../../../hooks/useConfirm';
import ConfirmDialog from '../../../components/ConfirmDialog';
import WorkBlocksEditor from '../../../components/WorkBlocksEditor';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours, deHoursExact, formatDayPlan } from '../../../utils/formatters';
import { showResponseWarning } from '../../../utils/arbzgWarnings';
import {
  deriveTargets, emptyWeek, formatBlocksText, isLegacyWeek, validateWeekBlocks,
} from '../../../utils/workBlocks';
import type { WeekBlocks } from '../../../types/workBlocks';
import type { WorkingHoursChange, WorkingHoursChangePreview } from './workingHoursTypes';
import WhImpactBox from './WhImpactBox';
import {
  BLOCKS_WITHOUT_EFFECT, JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT, formatDate, modeSwitchHint, savedMessage,
} from './workingHoursTexts';

interface WorkingHoursModalProps {
  userId: string;
  userName: string;
  currentWeeklyHours: number;
  // #431: der Rest des aktuell gültigen Snapshots. Optional mit Defaults, weil
  // sie nur der RÜCKFALL für den (seltenen) Fall „noch keine Historie" sind —
  // sobald der Verlauf geladen ist, gewinnt er (siehe `scheduleAt`).
  currentUseDailySchedule?: boolean;
  currentDayHours?: (number | null)[];
  currentWorkDays?: number;
  // Spec 2026-10-08 (12.1): heute gültige Blöcke (`work_blocks_today`) — ebenfalls
  // nur Rückfall — und die Stundenzählung (ohne sie kein Block-Modus, P24).
  currentBlocks?: WeekBlocks | null;
  trackHours?: boolean;
  onClose: () => void;
  onChanged: () => void;
}

// #431: Die fünf Wochentagsfelder an EINER Stelle — Feldname (= API-Feld),
// Beschriftung des Eingabefelds und Kurzform.
const DAY_FIELDS = [
  { key: 'hours_monday', label: 'Montag', short: 'Mo' },
  { key: 'hours_tuesday', label: 'Dienstag', short: 'Di' },
  { key: 'hours_wednesday', label: 'Mittwoch', short: 'Mi' },
  { key: 'hours_thursday', label: 'Donnerstag', short: 'Do' },
  { key: 'hours_friday', label: 'Freitag', short: 'Fr' },
] as const;

type DayFieldKey = typeof DAY_FIELDS[number]['key'];

const NO_DAY_HOURS: (number | null)[] = [null, null, null, null, null];

/** Spec 12.1: „Gleichmäßig" / „Nach Tagen" / „Nach Arbeitsblöcken". */
type Mode = 'even' | 'days' | 'blocks';

/** #431 + Spec 3.1: der Vertrags-Snapshot, wie ihn Dialog und Backend sehen. */
interface ScheduleSnapshot {
  weekly_hours: number;
  use_daily_schedule: boolean;
  /** Fünf Werte, Index 0 = Montag. 0 = kein geplanter Arbeitstag (wie `null`). */
  day_hours: number[];
  work_days_per_week: number;
  /** Blöcke der Zeile — neu (mit Pausen) oder Altfenster (Pausen NULL) — oder `null`. */
  blocks: WeekBlocks | null;
}

interface FormState {
  effective_from: string;
  mode: Mode;
  weekly_hours: number;
  hours_monday: number;
  hours_tuesday: number;
  hours_wednesday: number;
  hours_thursday: number;
  hours_friday: number;
  work_days_per_week: number;
  blocks: WeekBlocks;
  /** P2: Altfenster ausdrücklich entfernen statt übernehmen. */
  remove_legacy_window: boolean;
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

function hasNewBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && !isLegacyWeek(week);
}

function hasLegacyBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && isLegacyWeek(week);
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
    blocks: Array.isArray(change.blocks) ? change.blocks : null,
  };
}

// Fund 3 (Release-Review 1.17.0), #431: der zu einem Datum gültige Snapshot
// kommt aus dem geladenen Verlauf (jüngste Zeile mit effective_from <= datum),
// nicht aus den Props — die sind ein Stand von vor dem Öffnen des Dialogs und
// werden von Users.tsx nach dem Speichern nicht nachgezogen. Genau die
// Auflösung von `calculation_service.get_schedule_for_date`.
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
 * #431: Der Snapshot als Klartext — für die Kopfzeile und jede Verlaufszeile,
 * formuliert wie der Datei-Export (`export_service.format_weekly_hours_history`
 * / `utils/formatters.ts::formatWeeklyHoursChanges`).
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

/** Blockzeile für Kopf und Verlauf (Spec 12.1/4.4). */
function blocksLine(week: WeekBlocks | null, trackHours: boolean): string | null {
  const text = formatBlocksText(week);
  if (!text) return null;
  if (!trackHours) return `${BLOCKS_WITHOUT_EFFECT}: ${text}`;
  return hasLegacyBlocks(week) ? `${LEGACY_BOX_TITLE}: ${text}` : `Arbeitszeit-Blöcke: ${text}`;
}

/** Kanonische Vergleichsform der Blöcke (Schlüsselreihenfolge egal). */
function blocksKey(week: WeekBlocks | null): string | null {
  if (!Array.isArray(week)) return null;
  return JSON.stringify(week.map((d) => [d.blocks.map((b) => [b.start, b.end]), d.pause_minutes]));
}

/**
 * #431 + Spec 12.1: DIE Definition von „hat sich etwas geändert" — wie
 * `admin_users._comparable_snapshot`, jetzt mit Blöcken und Pausen.
 *
 * Im gleichmäßigen Modus sind die Tageswerte inert (das Tagessoll liest sie
 * dort nicht) und werden ausgeblendet, sonst täuschte ein Rest aus einer
 * früheren Tagesplan-Phase eine Änderung vor. Ohne Stundenzählung zählen die
 * Blöcke nicht (sie wirken nicht; beendet werden sie von jeder echten
 * Änderung, P24) — außer beim ausdrücklichen Entfernen eines Altfensters
 * (`compareBlocks` im Aufrufer).
 *
 * Review Focus 5: verglichen wird über die auf 0,01 h gerundeten Tageswerte —
 * 7:55 h im Editor ist gespeichert 7,92 h, beides ist derselbe Stand.
 */
function comparableSnapshot(s: ScheduleSnapshot, withBlocks: boolean): string {
  return JSON.stringify([
    round2(s.weekly_hours),
    s.use_daily_schedule,
    s.use_daily_schedule ? s.day_hours.map(round2) : [0, 0, 0, 0, 0],
    s.work_days_per_week,
    withBlocks ? blocksKey(s.blocks) : null,
  ]);
}

/** Formularstand aus einem Snapshot: Block-Modus, sobald neue Blöcke gelten
 * (und Stunden gezählt werden, P24). */
function formFromSnapshot(s: ScheduleSnapshot, effectiveFrom: string, trackHours: boolean): FormState {
  const blocksMode = trackHours && hasNewBlocks(s.blocks);
  return {
    effective_from: effectiveFrom,
    mode: blocksMode ? 'blocks' : s.use_daily_schedule ? 'days' : 'even',
    weekly_hours: s.weekly_hours,
    ...dayFieldsFromSnapshot(s.day_hours),
    work_days_per_week: s.work_days_per_week,
    blocks: blocksMode && s.blocks ? s.blocks : emptyWeek(),
    remove_legacy_window: false,
    note: '',
  };
}

/** Spec 4.4: Altfenster vorbefüllt in den Block-Modus — Werte unverändert
 * (07:37, 23:59), Pause leer und Pflicht an Tagen mit Blöcken (Review Focus 4:
 * der Editor meldet Raster und Pause, statt still zu korrigieren). */
function legacyToEditable(week: WeekBlocks): WeekBlocks {
  return week.map((d) => ({
    blocks: d.blocks.map((b) => ({ start: b.start.slice(0, 5), end: b.end.slice(0, 5) })),
    pause_minutes: d.blocks.length ? null : 0,
  }));
}

// Kalendertag VOR dem ISO-Datum (YYYY-MM-DD) — UTC-basiert, um Zeitzonen-/
// DST-Rollover bei reiner Tagesarithmetik zu vermeiden.
function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}

// M1 (Abschluss-Review): „heute" in der LOKALEN Zeitzone des Browsers, nicht
// `toISOString()` (UTC) — sonst hält der Dialog zwischen 00:00 und 02:00
// Berliner Zeit das gestrige Datum für „heute" und umgeht die
// Bestätigungspflicht, während das Backend (`today_local()`) dasselbe Datum
// als rückwirkend behandelt.
function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Debounce (ms), bevor die rein lesende Vorschau abgerufen wird, während der
// Admin Datum/Stunden/Blöcke noch anpasst.
const PREVIEW_DEBOUNCE_MS = 400;

export default function WorkingHoursModal({
  userId,
  userName,
  currentWeeklyHours,
  currentUseDailySchedule = false,
  currentDayHours = NO_DAY_HOURS,
  currentWorkDays = 5,
  currentBlocks = null,
  trackHours = true,
  onClose,
  onChanged,
}: WorkingHoursModalProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  // Schützt vor doppeltem Absenden (schneller Doppelklick legte zwei Zeilen an).
  const [submitting, setSubmitting] = useState(false);

  // Der Snapshot aus den Props — Rückfall, solange (oder falls) es keine Historie gibt.
  const propsSchedule = useMemo<ScheduleSnapshot>(() => ({
    weekly_hours: currentWeeklyHours,
    use_daily_schedule: currentUseDailySchedule,
    day_hours: normaliseDayHours(currentDayHours),
    work_days_per_week: currentWorkDays,
    blocks: currentBlocks,
  }), [currentWeeklyHours, currentUseDailySchedule, currentDayHours, currentWorkDays, currentBlocks]);

  const [formData, setFormData] = useState<FormState>(() => formFromSnapshot(propsSchedule, todayIso(), trackHours));

  const [preview, setPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Fund 4 (Release-Review 1.17.0): scheitert die Vorschau (Netzwerk, 5xx, ein
  // gecachtes altes Frontend gegen den entfallenen GET → 405 …), wird der
  // Fehler angezeigt, mit „Erneut prüfen" — statt eines leeren Kastens neben
  // einem gesperrten Knopf ohne Begründung.
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewRetryToken, setPreviewRetryToken] = useState(0);
  // Eine Änderung mit Auswirkung darf erst nach ausdrücklicher Bestätigung der
  // Vorschau gespeichert werden (9.4/12.1).
  const [confirmedRetroactive, setConfirmedRetroactive] = useState(false);

  const dayValues = DAY_FIELDS.map((f) => formData[f.key]);
  const daySum = round2(dayValues.reduce((sum, h) => sum + h, 0));
  const plannedDays = dayValues.filter((h) => h > 0).length;
  const derived = useMemo(() => deriveTargets(formData.blocks), [formData.blocks]);
  // Spec 3.4/12.1: Validierung im Client mit den Texten des Servers; Speichern
  // bleibt bei einem Fehler gesperrt (der Editor zeigt ihn als `role="alert"`).
  const blocksError = formData.mode === 'blocks' ? validateWeekBlocks(formData.blocks) : null;

  // Fund 3: die Kopfzeile hängt am Verlauf statt an der (nicht nachgezogenen) Prop.
  const displaySchedule = useMemo(
    () => scheduleAt(hoursChanges, todayIso(), propsSchedule),
    [hoursChanges, propsSchedule],
  );
  // #431: Verglichen wird gegen den Stand AM WIRKUNGSDATUM, nicht gegen den von
  // heute — „ab 01.03. gelten 20 h" kann eine echte Änderung sein, obwohl heute
  // längst 20 h gelten. Dieselbe Auflösung nutzt der Schreibpfad.
  const baselineSchedule = scheduleAt(hoursChanges, formData.effective_from, propsSchedule);
  const baselineLegacy = hasLegacyBlocks(baselineSchedule.blocks);
  const baselineNewBlocks = hasNewBlocks(baselineSchedule.blocks);
  // P2: ein Altfenster des Vorgänger-Snapshots wird in „Gleichmäßig"/„Nach
  // Tagen" übernommen, außer es wird ausdrücklich entfernt.
  const removeLegacy = baselineLegacy && formData.remove_legacy_window;
  const carriedBlocks = baselineLegacy && !formData.remove_legacy_window ? baselineSchedule.blocks : null;

  // #431 + Spec 11.1/11.2: Vorschau-Body UND Anlege-Body aus DERSELBEN Quelle —
  // zwei Formulierungen desselben Payloads laufen garantiert auseinander. Die
  // Modi schließen einander serverseitig hart aus: Block-Modus sendet nur
  // `blocks` (Stundenwerte daneben → 422, der Server leitet sie selbst ab, 4.2),
  // „Gleichmäßig" keine Tageswerte (→ 400).
  const scheduleBody: Record<string, unknown> = (() => {
    if (formData.mode === 'blocks') return { blocks: formData.blocks };
    const legacy = removeLegacy ? { remove_legacy_window: true } : {};
    if (formData.mode === 'days') {
      const body: Record<string, unknown> = { use_daily_schedule: true, ...legacy };
      DAY_FIELDS.forEach((f, i) => { body[f.key] = dayValues[i]; });
      // Die Wochensumme setzt der Server (`check_mode`) — ein eigener Wert des
      // Clients könnte ihr widersprechen. Arbeitstage = Tage mit Stunden; ohne
      // einen einzigen bleibt der Rückfall (die Eingabe kommt dann ohnehin als
      // `blocked_reason` zurück).
      if (plannedDays > 0) body.work_days_per_week = plannedDays;
      return body;
    }
    return {
      use_daily_schedule: false,
      weekly_hours: formData.weekly_hours,
      work_days_per_week: formData.work_days_per_week,
      ...legacy,
    };
  })();
  // Spec 12.1: der Effekt-Schlüssel ist der serialisierte Body — ein String,
  // also stabil über Renderläufe. Ein bei jedem Rendern neu erzeugtes Objekt im
  // Dependency-Array löste bei JEDEM Rendern eine Anfrage aus (Anfragesturm);
  // die Notiz gehört bewusst nicht dazu.
  const previewKey = JSON.stringify({ effective_from: formData.effective_from, ...scheduleBody });

  useEffect(() => {
    fetchHoursChanges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Vorschau für JEDES Wirkungsdatum (Release-Review 1.17.0: auch ein
  // zukünftiges Datum schreibt gebuchte Abwesenheiten um), seit Spec 11.1 per
  // POST mit JSON-Body — unfertige Eingaben kommen als `blocked_reason` zurück,
  // nie als 422. Jede Änderung entwertet eine zuvor gegebene Bestätigung.
  //
  // Fund 1 (Release-Review 1.17.0): `cancelled` verwirft verspätete Antworten
  // — React räumt den vorigen Effekt bei JEDER Schlüsseländerung auf, also
  // gewinnt die letzte Anfrage, nicht die letzte Antwort.
  useEffect(() => {
    setConfirmedRetroactive(false);
    setPreviewLoading(true);
    setPreviewError(null);
    let cancelled = false;
    const handle = setTimeout(() => {
      apiClient
        .post(`/admin/users/${userId}/working-hours-changes/preview`, JSON.parse(previewKey))
        .then((res) => {
          if (!cancelled) setPreview(res.data);
        })
        .catch((error) => {
          if (cancelled) return;
          setPreview(null);
          setPreviewError(getErrorMessage(error, 'Auswirkungen konnten nicht geprüft werden'));
        })
        .finally(() => {
          if (!cancelled) setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [userId, previewKey, previewRetryToken]);

  // Fund 3: gibt die frisch geladene Liste zurück (nicht nur über State), damit
  // der Formular-Reset nach dem Speichern SOFORT den neuen Stand nutzt.
  const fetchHoursChanges = async (): Promise<WorkingHoursChange[]> => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      const list: WorkingHoursChange[] = Array.isArray(response.data) ? response.data : []; // #382
      setHoursChanges(list);
      return list;
    } catch {
      toast.error('Fehler beim Laden der Stundenhistorie');
      return hoursChanges;
    }
  };

  // Task 7: „ab … bis …" — das Ende ergibt sich aus dem jeweils nächsten
  // Eintrag (Vortag), der jüngste läuft „bis heute".
  const historyEndDates = useMemo(() => {
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    const map = new Map<string, string | null>();
    asc.forEach((c, idx) => {
      const next = asc[idx + 1];
      map.set(c.id, next ? dayBefore(next.effective_from) : null);
    });
    return map;
  }, [hoursChanges]);

  // I4: die früheste Zeile ist gesperrt, solange spätere existieren — sie
  // verankert den davor gültigen Wert. Ist es die EINZIGE, bleibt sie löschbar.
  const lockedEarliestId = useMemo(() => {
    if (hoursChanges.length < 2) return null;
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    return asc[0].id;
  }, [hoursChanges]);

  const LOCKED_EARLIEST_HINT =
    'Die früheste erfasste Stundenänderung verankert den davor gültigen Wert — '
    + 'bitte zuerst die späteren Änderungen löschen.';

  // Was gesendet wird und welche Vorschau die Auswirkungs-Box zeigt. Heute
  // dasselbe Datum; der Verkürzungs-Kasten (Task 19) trennt beides (F24).
  const sentDate = formData.effective_from;
  const shown: WorkingHoursChangePreview | null = preview;
  const shownLoading = previewLoading;
  const shownError = previewError;
  const isRetroactive = sentDate < todayIso();

  // Release-Review 1.17.0: `blocked_reason` gilt für jedes Datum — der POST
  // weist unabhängig davon ab (Datum belegt, Blockfehler, …).
  const blockedReason = shown?.blocked_reason ?? null;
  const affectsBookedAbsences = !!shown && !blockedReason && shown.affected_absences > 0;
  // Spec 9.4/12.1: neu gekappte Einträge verlangen die Bestätigung — auch bei
  // Wirkungsdatum heute (Einträge von heute werden trotzdem neu gekappt).
  const affectsEntries = !!shown && !blockedReason && (shown.affected_time_entries ?? 0) > 0;
  // `round2` ist der Rundungs-, nicht der Gleichheitstest: 12,500000000000002 h
  // ist derselbe Saldo.
  const overtimeDelta = shown ? round2(shown.overtime_after - shown.overtime_before) : 0;
  const vacationDelta = shown ? round2(shown.vacation_days_after - shown.vacation_days_before) : 0;
  // Abschluss-Review #431, Fund 2: eine reine Saldo-/Urlaubswirkung (z. B. ein
  // wegfallender Wochentag ohne umgeschriebene Abwesenheits-Stunde) zählt mit.
  const affectsBalance = !!shown && !blockedReason && (overtimeDelta !== 0 || vacationDelta !== 0);
  // 9.4 ERGÄNZT die Auslöser aus 1.17.0/#431, nimmt keinen weg.
  const needsConfirmation = affectsEntries || affectsBookedAbsences || affectsBalance;
  const showImpactBox = isRetroactive || needsConfirmation || !!blockedReason;

  // #431: Was der Admin eingegeben hat — als Snapshot. Im Block-Modus über
  // dieselbe Ableitung wie der Server (`deriveTargets`, 4.1).
  const inputSchedule: ScheduleSnapshot = formData.mode === 'blocks'
    ? {
      weekly_hours: derived.weeklyHours,
      use_daily_schedule: true,
      day_hours: derived.hours,
      work_days_per_week: derived.workDays || formData.work_days_per_week,
      blocks: formData.blocks,
    }
    : {
      weekly_hours: formData.mode === 'days' ? daySum : formData.weekly_hours,
      use_daily_schedule: formData.mode === 'days',
      day_hours: dayValues,
      work_days_per_week: formData.mode === 'days'
        ? (plannedDays || formData.work_days_per_week)
        : formData.work_days_per_week,
      blocks: carriedBlocks,
    };
  // Ohne Stundenzählung bleiben die Blöcke aus dem Vergleich (P24) — außer das
  // Altfenster wird ausdrücklich entfernt: das IST die Änderung (der Server
  // vergleicht Blöcke immer), sonst bliebe „Fenster entfernen" unspeicherbar.
  const compareBlocks = trackHours || removeLegacy;
  const snapshotUnchanged =
    comparableSnapshot(inputSchedule, compareBlocks) === comparableSnapshot(baselineSchedule, compareBlocks);

  // Rückwirkend: Vorschau muss da und bestätigt sein. Ab heute sperrt nur ein
  // positiver Befund — fällt die Vorschau aus (Netzwerk, 5xx), bleibt das
  // Anlegen einer normalen zukunftsdatierten Änderung möglich.
  const saveDisabled =
    submitting ||
    !!blockedReason ||
    !!blocksError ||
    snapshotUnchanged ||
    (isRetroactive && (shownLoading || !shown || !confirmedRetroactive)) ||
    (!isRetroactive && needsConfirmation && !confirmedRetroactive);

  const setDayHours = (key: DayFieldKey, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: parseHours(value) }));
  };

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saveDisabled) return;
    setSubmitting(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, {
        effective_from: sentDate,
        note: formData.note,
        ...scheduleBody,
      });
      const freshChanges = await fetchHoursChanges();
      onChanged();
      // Fund 3: Formular aus dem frisch geladenen Verlauf, nicht aus den Props —
      // sonst spränge es auf den ALTEN Stand zurück, obwohl der Verlauf darunter
      // schon den neuen zeigt.
      setFormData(formFromSnapshot(scheduleAt(freshChanges, todayIso(), propsSchedule), todayIso(), trackHours));
      setPreview(null);
      setConfirmedRetroactive(false);
      const created: {
        adjusted_time_entries?: number; skipped_time_entries?: number; adjusted_absences?: number;
        warning?: string | null;
      } = res.data ?? {};
      toast.success(savedMessage(created));
      showResponseWarning(toast, created);
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
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
          // I3: 200 + {warning} bei berührtem abgeschlossenem Jahr, sonst 204
          // ohne Body (axios: data === '') — der Objekt-Check fängt das ab.
          const body = res?.data;
          const warning = body && typeof body === 'object' ? (body as { warning?: string }).warning : undefined;
          if (warning) {
            toast.warning(warning);
          }
        } catch (error: unknown) {
          // I4: der Grund kommt vom Backend — nicht hinter einer pauschalen Meldung verschlucken.
          toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
        }
      },
    });
  };

  // Ein zukunftsdatierter Wechsel liefert oft „12:30 → 12:30" — korrekt (der
  // Saldo-Stichtag #313 liegt vor dem Wirkungsfenster), darf aber nicht als
  // „keine Auswirkung" gelesen werden, während Abwesenheiten umgeschrieben werden.
  // Nur dann: seit 9.4 öffnen auch neu gekappte Einträge (oder ein
  // `blocked_reason`) den Kasten — ohne umgeschriebene Abwesenheit widerspräche
  // der Satz der Zeile „0 Abwesenheit(en) betroffen." direkt darüber.
  const balanceUnchangedAhead =
    !!shown && !isRetroactive && affectsBookedAbsences && overtimeDelta === 0 && vacationDelta === 0;
  const displayBlocksLine = blocksLine(displaySchedule.blocks, trackHours);
  const planNotices = preview?.block_break_notices ?? [];

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
            <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 sm:px-6 py-4 flex items-start justify-between gap-3">
              <div className="min-w-0 break-words">
                <h2 id="hours-modal-title" className="text-xl sm:text-2xl font-bold text-gray-900">
                  Arbeitszeit &amp; Wochenstunden
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  {userName} • Aktuell: {describeSchedule(displaySchedule)}
                </p>
                {displayBlocksLine && <p className="text-sm text-gray-600">{displayBlocksLine}</p>}
              </div>
              <button
                onClick={onClose}
                className="shrink-0 text-gray-500 hover:text-gray-700"
                aria-label={`Arbeitszeit & Wochenstunden für ${userName} schließen`}
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-4 sm:p-6">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 sm:p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Änderung</h3>
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
                      Vertragsänderung mit Wirkungsdatum. Spec 12.1/P24: den
                      Block-Modus gibt es nur mit Stundenzählung. */}
                  <fieldset className="border border-blue-200 rounded-lg p-3 bg-white min-w-0">
                    <legend className="px-1 text-sm font-medium text-gray-700">Ab diesem Datum gilt</legend>
                    <div className="flex flex-wrap gap-x-4 gap-y-2 mb-3">
                      {([
                        ['even', 'Gleichmäßig'],
                        ['days', 'Nach Tagen'],
                        ...(trackHours ? [['blocks', 'Nach Arbeitsblöcken']] : []),
                      ] as [Mode, string][]).map(([value, label]) => (
                        <label key={value} className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                          <input
                            type="radio"
                            name="wh-mode"
                            checked={formData.mode === value}
                            onChange={() => setFormData((prev) => ({ ...prev, mode: value }))}
                            className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                          />
                          {label}
                        </label>
                      ))}
                    </div>

                    {formData.mode === 'blocks' ? (
                      <WorkBlocksEditor
                        value={formData.blocks}
                        onChange={(blocks) => setFormData((prev) => ({ ...prev, blocks }))}
                        idPrefix="wh-blocks"
                      />
                    ) : formData.mode === 'days' ? (
                      // Handy: zwei Spalten statt fünf gequetschter Felder.
                      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                        {DAY_FIELDS.map((f) => (
                          <div key={f.key}>
                            <label htmlFor={`wh-${f.key}`} className="block text-xs font-medium text-gray-600 mb-1">
                              {f.label}
                            </label>
                            <input
                              id={`wh-${f.key}`}
                              type="number"
                              // Fund C (#431): Viertelstunden wie im Anlegeformular.
                              step="0.25"
                              min="0"
                              max="24"
                              value={formData[f.key]}
                              onChange={(e) => setDayHours(f.key, e.target.value)}
                              className="w-full px-2 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-sm"
                            />
                          </div>
                        ))}
                        {/* Die Wochensumme rechnet der Server aus denselben
                            Werten (`check_mode`) — hier in derselben Schreibweise. */}
                        <p className="col-span-full text-sm text-gray-700 mt-1">
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
                            // Fund C: derselbe Schritt wie bei den Tagesfeldern.
                            step="0.25"
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

                  {/* Spec 4.4: Altfenster — Aktionen „umwandeln" / „entfernen". */}
                  {baselineLegacy && formData.mode !== 'blocks' && (
                    <div
                      role="group"
                      aria-labelledby="wh-legacy-title"
                      className="rounded-lg border border-gray-300 bg-gray-50 p-3 text-sm break-words"
                    >
                      <p id="wh-legacy-title" className="font-medium text-gray-800">{LEGACY_BOX_TITLE}</p>
                      <p className="text-gray-700 mt-1">{formatBlocksText(baselineSchedule.blocks)}</p>
                      {/* Ohne Stundenzählung kappt das Fenster nichts
                          (`work_window_service`: track_hours_off) — wie die
                          Kopfzeile „ohne Wirkung", nie „kappt". */}
                      <p className="text-gray-600 mt-1">
                        {formData.remove_legacy_window
                          ? trackHours
                            ? `Das Fenster wird ab ${formatDate(formData.effective_from)} entfernt; danach wird nicht mehr gekappt.`
                            : `Das Fenster wird ab ${formatDate(formData.effective_from)} entfernt.`
                          : trackHours
                            ? 'Bleibt mit dieser Änderung bestehen: kappt die erfasste Zeit, ändert das Tagessoll nicht.'
                            : 'Bleibt mit dieser Änderung bestehen, ohne Wirkung (keine Stundenzählung): kappt nichts, ändert das Tagessoll nicht.'}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {trackHours && (
                          <button
                            type="button"
                            onClick={() => setFormData((prev) => ({
                              ...prev,
                              mode: 'blocks',
                              blocks: legacyToEditable(baselineSchedule.blocks ?? emptyWeek()),
                              remove_legacy_window: false,
                            }))}
                            className="px-3 py-1 rounded-lg border border-gray-300 bg-white text-gray-800 hover:bg-gray-100"
                          >
                            In Arbeitszeit-Blöcke umwandeln
                          </button>
                        )}
                        <button
                          type="button"
                          aria-pressed={formData.remove_legacy_window}
                          onClick={() => setFormData((prev) => ({ ...prev, remove_legacy_window: !prev.remove_legacy_window }))}
                          className="px-3 py-1 rounded-lg border border-gray-300 bg-white text-gray-800 hover:bg-gray-100"
                        >
                          {formData.remove_legacy_window ? 'Fenster behalten' : 'Fenster entfernen'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* P24: Moduswechsel weg von Blöcken — vor dem Speichern nennen
                      (bei track_hours=false bei JEDER Änderung, der Block-Modus
                      wird dort nicht angeboten). */}
                  {baselineNewBlocks && formData.mode !== 'blocks' && !snapshotUnchanged && (
                    <p className="text-sm font-medium text-amber-800">
                      {modeSwitchHint(formatDate(formData.effective_from))}
                    </p>
                  )}

                  {/* Spec 12.1: Rechtshinweise fest unter dem Editor. */}
                  <div className="space-y-1 text-xs text-gray-600">
                    <p className="flex gap-1"><Info size={14} className="shrink-0 mt-0.5" aria-hidden="true" />{LEGAL_HINT}</p>
                    <p className="flex gap-1"><Info size={14} className="shrink-0 mt-0.5" aria-hidden="true" />{JARBSCHG_HINT}</p>
                  </div>

                  {/* P9: Plan-Hinweise aus der Vorschau — nicht blockierend. */}
                  {planNotices.length > 0 && (
                    <ul aria-label="Hinweise zum Plan" className="list-disc pl-5 text-sm text-blue-900 space-y-0.5 break-words">
                      {planNotices.map((n) => <li key={n}>{n}</li>)}
                    </ul>
                  )}

                  {/* Auswirkungs-Box: VOR dem Speichern zeigen, was die Änderung
                      anfasst, plus Blockade-Grund bzw. Bestätigungspflicht. */}
                  {showImpactBox && (
                    <div
                      role="status"
                      className={`rounded-lg border p-3 text-sm min-w-0 ${
                        blockedReason || shownError ? 'bg-red-50 border-red-300' : 'bg-amber-50 border-amber-300'
                      }`}
                    >
                      {shownLoading ? (
                        <p className="text-gray-600">Prüfe Auswirkungen…</p>
                      ) : shown ? (
                        <>
                          {/* Fund A (#431): `blockedReason` entscheidet die
                              Überschrift vor allen anderen Gründen — gespeichert
                              wird dann ohnehin nichts. */}
                          <p className="font-semibold text-amber-900">
                            {blockedReason
                              ? 'Änderung nicht möglich'
                              : isRetroactive
                                ? 'Rückwirkende Änderung'
                                : affectsEntries
                                  ? 'Betrifft bereits erfasste Zeiteinträge'
                                  : affectsBookedAbsences
                                    ? 'Betrifft bereits gebuchte Abwesenheiten'
                                    : 'Ändert Überstunden oder Urlaubsverbrauch'}:{' '}
                            {formatDate(shown.period_start)} – {formatDate(shown.period_end)}
                          </p>
                          {!blockedReason && <WhImpactBox preview={shown} />}
                          {balanceUnchangedAhead && (
                            <p className="text-amber-800 mt-1">
                              Saldo und Urlaub stehen auf dem Stand von heute — die Änderung
                              wirkt erst ab dem {formatDate(sentDate)}. Die oben
                              genannten Abwesenheiten werden trotzdem umgeschrieben.
                            </p>
                          )}
                          {shown.closed_year_warning && (
                            <p className="text-amber-900 font-medium mt-1">{shown.closed_year_warning}</p>
                          )}
                          {blockedReason ? (
                            <p className="text-red-700 font-medium mt-2">{blockedReason}</p>
                          ) : (
                            <label className="flex items-center gap-2 mt-2 text-amber-900 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={confirmedRetroactive}
                                onChange={(e) => setConfirmedRetroactive(e.target.checked)}
                                className="w-4 h-4 shrink-0 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                              />
                              Ich habe die Auswirkungen geprüft und möchte speichern
                            </label>
                          )}
                        </>
                      ) : shownError ? (
                        <>
                          <p className="text-red-700 font-medium">{shownError}</p>
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

                  {/* Ein gesperrter Knopf ohne Begründung ist genau der Fund-4-Fehler —
                      der häufigste Grund ist der frisch geöffnete, vorbefüllte Dialog. */}
                  {snapshotUnchanged && !blockedReason && (
                    <p className="text-sm text-gray-600">
                      Noch nichts zu speichern — die Eingabe entspricht dem Stand, der
                      am {formatDate(formData.effective_from)} ohnehin gilt.
                    </p>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="flex-1 px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
                    >
                      Abbrechen
                    </button>
                    <button
                      type="submit"
                      disabled={saveDisabled}
                      className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Save size={18} />
                      <span>Speichern</span>
                    </button>
                  </div>
                </form>
              </div>

              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => {
                      const end = historyEndDates.get(change.id);
                      const rowBlocks = blocksLine(Array.isArray(change.blocks) ? change.blocks : null, trackHours);
                      return (
                        <div
                          key={change.id}
                          className="bg-gray-50 border border-gray-200 rounded-lg p-3 sm:p-4 flex items-start justify-between gap-3"
                        >
                          <div className="min-w-0 break-words">
                            <p className="font-medium text-gray-900">
                              Ab {formatDate(change.effective_from)} bis {end ? formatDate(end) : 'heute'}:{' '}
                              {describeSchedule(scheduleFromChange(change, propsSchedule.work_days_per_week))}
                            </p>
                            {rowBlocks && <p className="text-sm text-gray-700 mt-1">{rowBlocks}</p>}
                            {change.note && <p className="text-sm text-gray-600 mt-1">{change.note}</p>}
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
                            // Der Titel sitzt am umschließenden <span>: ein disabled
                            // <button> feuert keine Hover-Events.
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
                              className="shrink-0 text-red-600 hover:text-red-800"
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
                  historischen Werte — bei „Gleichmäßig", „Nach Tagen" <strong>und</strong> „Nach
                  Arbeitsblöcken", auch über einen Moduswechsel hinweg. Bei „Nach Arbeitsblöcken" ist das
                  Tagessoll die Gesamtzeit der Blöcke minus der Pause innerhalb der Blöcke; erfasste Zeit
                  wird an den Blockrändern mit dem Puffer gekappt.
                </p>
              </div>
            </div>
          </div>
        </FocusTrap>
      </div>
    </>
  );
}
