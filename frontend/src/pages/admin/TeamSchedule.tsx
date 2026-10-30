// 1.21 Teamübersicht der Arbeitszeiten: wer arbeitet laut Vertrag wann.
//
// Lesend für alle Personen, gefiltert nach Abteilung. Mit dem Schieber
// „Bearbeiten" lassen sich Blöcke ziehen (Maus) bzw. mit den Pfeiltasten
// verschieben; das ergibt nur einen ENTWURF je Person. Wirksam wird er erst im
// Dialog „Arbeitszeit anpassen…" — mit Stichtag, Vorschau und
// Verkürzungsschutz, dem einzigen Schreibweg für Arbeitszeiten.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { CalendarClock, Info } from 'lucide-react';
import apiClient from '../../api/client';
import { getErrorMessage } from '../../utils/errorMessage';
import { deHoursExact } from '../../utils/formatters';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import { blocksOf, formatWeekBlocks, hhmmToMinutes, validateWeekBlocks, WEEKDAY_LABELS } from '../../utils/workBlocks';
import {
  axisRange, compactSpan, coverage, departmentsOf, DRAG_SNAP_MINUTES, moveBlock, resizeBlock, sameWeek, snapMinutes,
} from '../../utils/teamSchedule';
import type { WeekBlocks } from '../../types/workBlocks';
import type { ScheduleToday } from '../../types/user';
import WorkingHoursModal from './users/WorkingHoursModal';

interface TeamRow {
  user_id: string;
  first_name: string;
  last_name: string;
  department: string | null;
  calendar_color: string;
  track_hours: boolean;
  use_fixed_monthly_target: boolean;
  blocks: WeekBlocks | null;
  legacy: boolean;
  schedule: ScheduleToday;
  next_change: { effective_from: string; blocks: WeekBlocks | null } | null;
}

type Drag = {
  userId: string; day: number; idx: number; mode: 'move' | 'start' | 'end';
  // Achsenspanne beim Greifen: wächst die Achse während des Ziehens, liefe der
  // Block sonst dem Zeiger davon (Release-Review 1.21).
  x0: number; width: number; span: number; base: WeekBlocks;
};

const ALL = '';
const SLOT = 30;

function todayIso(): string {
  return format(new Date(), 'yyyy-MM-dd');
}

function hhmm(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

function personName(r: TeamRow): string {
  return `${r.last_name}, ${r.first_name}`;
}

/** Ziehbar sind nur neue Blöcke mit Stundenzählung (Altfenster und Personen
 * ohne Blöcke ändern sich nur im Dialog). */
function draggable(r: TeamRow): boolean {
  return r.track_hours && !r.legacy && Array.isArray(r.blocks);
}

export default function TeamSchedule() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [onDate, setOnDate] = useState(todayIso());
  const [rows, setRows] = useState<TeamRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState<string>(ALL);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, WeekBlocks>>({});
  const [modalRow, setModalRow] = useState<TeamRow | null>(null);
  const drag = useRef<Drag | null>(null);
  // Nur die jüngste Anfrage zählt — eine verspätete Antwort auf ein schon
  // verlassenes Datum überschriebe sonst die Liste (Release-Review 1.21).
  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    try {
      const res = await apiClient.get('/admin/team-schedule', { params: { date: onDate } });
      if (seq !== loadSeq.current) return;
      const next: TeamRow[] = Array.isArray(res.data) ? res.data : [];
      setRows(next);
      // Entwürfe gehören zu Personen der Liste; wer fehlt, verliert seinen Entwurf.
      setDrafts((d) => Object.fromEntries(
        Object.entries(d).filter(([id]) => next.some((r) => r.user_id === id))));
    } catch (err) {
      if (seq === loadSeq.current) toast.error(getErrorMessage(err, 'Arbeitszeiten konnten nicht geladen werden'));
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onDate]);

  useEffect(() => { load(); }, [load]);

  const departments = useMemo(() => departmentsOf(rows), [rows]);
  // Fehlt die gewählte Abteilung nach dem Neuladen, gilt wieder „Alle".
  const activeDepartment = departments.includes(department) ? department : ALL;
  const shown = useMemo(
    () => rows.filter((r) => activeDepartment === ALL || (r.department ?? '').trim() === activeDepartment),
    [rows, activeDepartment],
  );
  const weekOf = (r: TeamRow): WeekBlocks | null => drafts[r.user_id] ?? r.blocks;
  // Altfenster (nur Kappung, oft 00:00/23:59-Platzhalter) sind keine Planung:
  // sie zählen weder für die Zeitachse noch für die Besetzung.
  const planned = useMemo(
    () => shown.filter((r) => !r.legacy).map((r) => drafts[r.user_id] ?? r.blocks),
    [shown, drafts],
  );
  const axis = useMemo(() => axisRange(planned), [planned]);
  const span = axis.end - axis.start;
  const dirtyCount = Object.keys(drafts).length;

  const setDraft = (r: TeamRow, week: WeekBlocks) => {
    setDrafts((d) => {
      const next = { ...d };
      if (sameWeek(week, r.blocks)) delete next[r.user_id];
      else next[r.user_id] = week;
      return next;
    });
  };

  const discard = (userId: string) => setDrafts((d) => {
    const next = { ...d };
    delete next[userId];
    return next;
  });

  const toggleEditing = () => {
    if (!editing) { setEditing(true); return; }
    const stop = () => { setDrafts({}); setEditing(false); };
    if (dirtyCount === 0) { stop(); return; }
    confirm({
      title: 'Bearbeiten beenden?',
      message: `${dirtyCount === 1 ? 'Eine Änderung ist' : `${dirtyCount} Änderungen sind`} noch nicht gespeichert und gehen verloren.`,
      confirmLabel: 'Verwerfen',
      variant: 'warning',
      onConfirm: stop,
    });
  };

  // Maus/Touch: Ziehen auf dem Block verschiebt, an den Rändern ändert es Beginn bzw. Ende.
  const onPointerDown = (e: React.PointerEvent<HTMLElement>, r: TeamRow, day: number, idx: number) => {
    if (!editing || !draggable(r)) return;
    const track = e.currentTarget.parentElement;
    if (!track) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // Randzone höchstens ein Viertel des Blocks — auch kurze Blöcke bleiben verschiebbar.
    const edge = Math.min(6, rect.width / 4);
    const mode = e.clientX - rect.left < edge ? 'start' : rect.right - e.clientX < edge ? 'end' : 'move';
    drag.current = {
      userId: r.user_id, day, idx, mode, x0: e.clientX, span,
      width: track.getBoundingClientRect().width || 1, base: weekOf(r) as WeekBlocks,
    };
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  };

  const onPointerMove = (e: React.PointerEvent<HTMLElement>, r: TeamRow) => {
    const d = drag.current;
    if (!d || d.userId !== r.user_id) return;
    const delta = snapMinutes(((e.clientX - d.x0) / d.width) * d.span);
    const week = d.mode === 'move'
      ? moveBlock(d.base, d.day, d.idx, delta)
      : resizeBlock(d.base, d.day, d.idx, d.mode, delta);
    setDraft(r, week);
  };

  const onPointerUp = () => { drag.current = null; };

  // Tastatur: Pfeil links/rechts verschiebt um 15 Min., mit Umschalt ändert er das Ende.
  const onKeyDown = (e: React.KeyboardEvent<HTMLElement>, r: TeamRow, day: number, idx: number) => {
    if (!editing || !draggable(r)) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const delta = e.key === 'ArrowRight' ? DRAG_SNAP_MINUTES : -DRAG_SNAP_MINUTES;
    const base = weekOf(r) as WeekBlocks;
    setDraft(r, e.shiftKey ? resizeBlock(base, day, idx, 'end', delta) : moveBlock(base, day, idx, delta));
  };

  // Nach einem Tastendruck den Fokus auf dem (neu beschrifteten) Block halten.
  const focusKey = useRef<string | null>(null);
  useEffect(() => {
    if (!focusKey.current) return;
    const key = focusKey.current;
    focusKey.current = null;   // nur einmal — sonst stähle jedes Rendern den Fokus
    document.querySelector<HTMLElement>(`[data-block-key="${key}"]`)?.focus();
  });

  const ticks = useMemo(() => {
    const out: number[] = [];
    for (let t = axis.start; t <= axis.end; t += 120) out.push(t);
    return out;
  }, [axis]);

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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            <CalendarClock className="w-7 h-7 text-primary" aria-hidden="true" />
            Arbeitszeiten im Team
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            Wer arbeitet laut hinterlegten Arbeitszeit-Blöcken wann – Stand am gewählten Tag.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="team-schedule-date" className="block text-sm font-medium text-gray-700 mb-1">Stand am</label>
            <input
              id="team-schedule-date"
              type="date"
              value={onDate}
              disabled={dirtyCount > 0}
              title={dirtyCount > 0 ? 'Erst Änderungen speichern oder verwerfen' : undefined}
              onChange={(e) => e.target.value && setOnDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary disabled:opacity-50"
            />
          </div>
          <div className="flex items-center gap-2 pb-2">
            <span id="team-schedule-edit-label" className="text-sm font-medium text-gray-700">Bearbeiten</span>
            <button
              type="button"
              role="switch"
              aria-checked={editing}
              aria-labelledby="team-schedule-edit-label"
              onClick={toggleEditing}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-hidden focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                editing ? 'bg-primary' : 'bg-gray-200'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                editing ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Abteilung">
        {[ALL, ...departments].map((d) => (
          <button
            key={d || 'all'}
            type="button"
            onClick={() => setDepartment(d)}
            aria-pressed={activeDepartment === d}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              activeDepartment === d
                ? 'bg-primary text-white border-primary'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {d || 'Alle'}
          </button>
        ))}
      </div>

      {editing && (
        <div className="flex gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          <Info className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <p>
            Block ziehen verschiebt ihn, an den Rändern ziehen ändert Beginn bzw. Ende (15-Minuten-Raster;
            per Tastatur: Pfeiltasten, mit Umschalt das Ende). Wirksam wird eine Änderung erst über
            „Änderung speichern…“ – mit Stichtag, Vorschau und den üblichen Schutzregeln.
          </p>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
        <div className="min-w-[56rem]">
          {/* Kopf: Wochentage mit Stundenmarken */}
          <div className="grid grid-cols-[14rem_repeat(5,minmax(0,1fr))] border-b border-gray-200 bg-gray-50 text-xs text-gray-500">
            <div className="px-3 py-2 font-medium text-gray-700">Person</div>
            {WEEKDAY_LABELS.map((label) => (
              <div key={label} className="px-2 py-2 border-l border-gray-200">
                <div className="font-semibold text-gray-700 text-sm">{label}</div>
                <div className="relative h-4">
                  {ticks.map((t) => (
                    <span key={t} className="absolute -translate-x-1/2" style={{ left: `${((t - axis.start) / span) * 100}%` }}>
                      {t / 60}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Besetzung je Tag */}
          <div className="grid grid-cols-[14rem_repeat(5,minmax(0,1fr))] border-b border-gray-200">
            <div className="px-3 py-2 text-xs font-medium text-gray-600">Besetzung</div>
            {WEEKDAY_LABELS.map((label, day) => {
              const counts = coverage(planned, day, axis.start, axis.end, SLOT);
              return (
                <div key={label} className="flex items-center gap-px px-2 py-2 border-l border-gray-200">
                  {counts.map((n, i) => {
                    const from = axis.start + i * SLOT;
                    const who = n === 0 ? 'niemand' : n === 1 ? '1 Person' : `${n} Personen`;
                    const shade = n === 0 ? 'bg-gray-100' : n === 1 ? 'bg-primary/25' : n === 2 ? 'bg-primary/50' : 'bg-primary/80';
                    return (
                      <span
                        key={from}
                        title={`${label} ${hhmm(from)}–${hhmm(from + SLOT)}: ${who}`}
                        className={`h-3 flex-1 rounded-sm ${shade}`}
                      />
                    );
                  })}
                </div>
              );
            })}
          </div>

          {loading && rows.length === 0 && (
            <p className="px-3 py-6 text-sm text-gray-500">Lade Arbeitszeiten…</p>
          )}
          {!loading && shown.length === 0 && (
            <p className="px-3 py-6 text-sm text-gray-500">Keine Personen in dieser Auswahl.</p>
          )}

          {shown.map((r) => {
            const week = weekOf(r);
            const dirty = !!drafts[r.user_id];
            const error = dirty ? validateWeekBlocks(week) : null;
            const canDrag = editing && !loading && draggable(r);
            return (
              <div
                key={r.user_id}
                data-testid={`team-row-${r.user_id}`}
                className={`grid grid-cols-[14rem_repeat(5,minmax(0,1fr))] border-b border-gray-100 last:border-b-0 ${dirty ? 'bg-amber-50' : ''}`}
              >
                <div className="px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: r.calendar_color }} aria-hidden="true" />
                    <span className="font-medium text-gray-900 truncate">{personName(r)}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap gap-x-2">
                    {r.department && <span>{r.department}</span>}
                    {r.track_hours
                      ? <span>{deHoursExact(r.schedule.weekly_hours)} h/Woche</span>
                      : <span>ohne Stundenzählung</span>}
                  </div>
                  {!Array.isArray(r.blocks) && <div className="text-xs text-gray-500">keine Arbeitszeit-Blöcke</div>}
                  {r.legacy && <div className="text-xs text-gray-500">übernommenes Arbeitszeit-Fenster (nur Kappung)</div>}
                  {r.next_change && (
                    <span
                      className="inline-block mt-1 rounded-sm bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900"
                      title={formatWeekBlocks(r.next_change.blocks) ?? 'ohne Arbeitszeit-Blöcke'}
                    >
                      ab {format(parseISO(r.next_change.effective_from), 'dd.MM.yyyy')} neu
                    </span>
                  )}
                  {error && <p role="alert" className="text-xs text-red-700 mt-1">{error}</p>}
                  {editing && (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {dirty ? (
                        <>
                          <button
                            type="button"
                            disabled={!!error}
                            onClick={() => setModalRow(r)}
                            className="text-xs font-medium text-primary hover:underline disabled:opacity-50 disabled:no-underline"
                          >
                            Änderung speichern…
                          </button>
                          <button type="button" onClick={() => discard(r.user_id)} className="text-xs text-gray-600 hover:underline">
                            Verwerfen
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={() => setModalRow(r)} className="text-xs font-medium text-primary hover:underline">
                          Ändern…
                        </button>
                      )}
                    </div>
                  )}
                </div>
                {WEEKDAY_LABELS.map((label, day) => (
                  <div key={label} className="relative border-l border-gray-100 h-14">
                    <div className="absolute inset-x-2 inset-y-3">
                      {blocksOf(week?.[day]).map((b, idx) => {
                        // Auf die Achse begrenzt (Altfenster reichen bis 00:00/23:59).
                        const s = Math.max(axis.start, hhmmToMinutes(b.start));
                        const e = Math.min(axis.end, hhmmToMinutes(b.end));
                        if (e <= s) return null;
                        const text = `${personName(r)} · ${label} ${b.start}–${b.end}`;
                        const key = `${r.user_id}-${day}-${idx}`;
                        const style = {
                          left: `${((s - axis.start) / span) * 100}%`,
                          width: `${((e - s) / span) * 100}%`,
                          backgroundColor: r.legacy || !r.track_hours ? undefined : r.calendar_color,
                        };
                        const cls = `absolute inset-y-0 rounded-md text-[11px] leading-tight text-gray-900 px-1 overflow-hidden whitespace-nowrap flex items-center ${
                          r.legacy || !r.track_hours ? 'bg-gray-200 border border-dashed border-gray-400' : 'border border-black/10'
                        }`;
                        return canDrag ? (
                          <button
                            key={key}
                            type="button"
                            data-block-key={key}
                            title={text}
                            aria-label={`${text} (Pfeiltasten verschieben, mit Umschalt das Ende ändern)`}
                            style={style}
                            className={`${cls} cursor-grab active:cursor-grabbing touch-none ring-offset-1 focus:outline-hidden focus:ring-2 focus:ring-primary`}
                            onPointerDown={(ev) => onPointerDown(ev, r, day, idx)}
                            onPointerMove={(ev) => onPointerMove(ev, r)}
                            onPointerUp={onPointerUp}
                            onPointerCancel={onPointerUp}
                            onKeyDown={(ev) => { focusKey.current = key; onKeyDown(ev, r, day, idx); }}
                          >
                            <span className="pointer-events-none">{compactSpan(b.start, b.end)}</span>
                          </button>
                        ) : (
                          <div key={key} title={text} style={style} className={cls}>
                            <span>{compactSpan(b.start, b.end)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {modalRow && (
        <WorkingHoursModal
          userId={modalRow.user_id}
          userName={`${modalRow.first_name} ${modalRow.last_name}`}
          currentWeeklyHours={modalRow.schedule.weekly_hours}
          currentUseDailySchedule={modalRow.schedule.use_daily_schedule}
          currentDayHours={[
            modalRow.schedule.hours_monday ?? null,
            modalRow.schedule.hours_tuesday ?? null,
            modalRow.schedule.hours_wednesday ?? null,
            modalRow.schedule.hours_thursday ?? null,
            modalRow.schedule.hours_friday ?? null,
          ]}
          currentWorkDays={modalRow.schedule.work_days_per_week}
          currentBlocks={modalRow.blocks}
          trackHours={modalRow.track_hours}
          fixedMonthlyTarget={modalRow.use_fixed_monthly_target}
          initialBlocks={drafts[modalRow.user_id] ?? null}
          initialEffectiveFrom={onDate}
          onClose={() => setModalRow(null)}
          onChanged={() => { discard(modalRow.user_id); load(); }}
        />
      )}
    </div>
  );
}
