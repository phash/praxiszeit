import { useEffect, useId, useState, useCallback, useMemo, useRef } from 'react';
import {
  DndContext,
  MouseSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  useDraggable,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  Plus,
  Trash2,
  Power,
  PowerOff,
  CheckCircle2,
  AlertTriangle,
  CalendarDays,
  Settings2,
  GripVertical,
  GraduationCap,
  Pencil,
  Wand2,
  Copy,
  Printer,
  Eye,
} from 'lucide-react';
import DialogFocusTrap from '../../components/DialogFocusTrap';
import apiClient from '../../api/client';
import Button from '../../components/Button';
import FormInput from '../../components/FormInput';
import EmptyState from '../../components/EmptyState';
import ConfirmDialog from '../../components/ConfirmDialog';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import { getErrorMessage } from '../../utils/errorMessage';
import { formatIsoDateDe } from '../../utils/formatters';
import { useSystemStore } from '../../stores/systemStore';
import WeekGrid from '../../components/shiftplanning/WeekGrid';
import SlotDialog, { type SlotDialogInitial, type SlotEmployee } from '../../components/shiftplanning/SlotDialog';
import LocationManager from '../../components/shiftplanning/LocationManager';
import WorkstationManager from '../../components/shiftplanning/WorkstationManager';
import QualificationMatrix from '../../components/shiftplanning/QualificationMatrix';
import PlanSettingsDialog from '../../components/shiftplanning/PlanSettingsDialog';
import YearTimeline from '../../components/shiftplanning/YearTimeline';
import GenerateDialog from '../../components/shiftplanning/GenerateDialog';
import {
  timeToMinutes,
  minutesToTime,
  movedSlotTimes,
} from '../../components/shiftplanning/weekGridUtils';
import * as api from '../../api/shiftPlanning';
import type { Location, Workstation, PlanSummary, PlanDetail, ShiftSlot, SlotInput } from '../../api/shiftPlanning';
import { assignedMinutesByUser, formatLoad, loadColor } from '../../components/shiftplanning/employeeLoad';

// ui-22: die Felder von GET /admin/users, die der Planer braucht.
interface AdminUserRow {
  id: string;
  first_name: string;
  last_name: string;
  weekly_hours?: number;
  is_active: boolean;
  is_hidden?: boolean;
}

function DraggableEmployee({ emp, assignedMinutes }: { emp: SlotEmployee; assignedMinutes: number }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `emp-${emp.id}`,
    data: { type: 'employee', userId: emp.id },
  });
  // #330: zugewiesene Schichtstunden (dieser Plan) vs. Wochenarbeitszeit.
  const weekly = emp.weekly_hours ?? 0;
  const color = loadColor(assignedMinutes, weekly);
  const loadClass =
    color === 'green' ? 'text-green-600'
    : color === 'yellow' ? 'text-amber-600'
    : color === 'red' ? 'text-red-600'
    : 'text-gray-400';
  return (
    <div
      ref={setNodeRef}
      style={{
        transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
        opacity: isDragging ? 0.5 : 1,
      }}
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm cursor-grab hover:border-primary"
      {...listeners}
      {...attributes}
    >
      <GripVertical size={14} className="text-gray-300 shrink-0" />
      <div className="min-w-0">
        <div className="truncate">{emp.first_name} {emp.last_name}</div>
        <div className={`text-xs ${loadClass}`} title="Zugewiesene Schichtstunden in diesem Plan / Wochenarbeitszeit">
          {formatLoad(assignedMinutes, weekly)}
        </div>
      </div>
    </div>
  );
}

type SlotDialogState = {
  open: boolean;
  mode: 'create' | 'edit';
  slotId?: string;
  initial: SlotDialogInitial;
};

// #443 F-1 (Prüfrunde 2, CRITICAL): baut die `PUT /slots/{id}`-Nutzlast fürs
// Verschieben eines Slots per Drag & Drop. `PUT /slots/{id}` ist ein
// Vollersatz — der Server (SlotIn) setzt jedes im Rumpf fehlende Feld auf
// seinen Default (z. B. note=None). Eine handgeschriebene, feldweise
// Nutzlast hatte genau deshalb einmal stillschweigend den Hinweis auf NULL
// gesetzt (Commit 12171aa9). Statt Felder aufzuzählen, übernimmt diese
// Funktion den unveränderten Zustand des Slots und überschreibt nur, was ein
// Verschieben tatsächlich ändert (Wochentag/Beginn/Ende) — jedes künftige
// SlotInput-Feld läuft dadurch automatisch mit; nur die reinen Anzeige-
// Extrafelder von `ShiftSlot` werden entfernt.
//
// Exportiert (statt inline in `onDragEnd`) und in `ShiftPlanning.test.tsx`
// direkt getestet — siehe F-1-Begründung dort: eine reine Funktion ist ohne
// dnd-kit-/Toast-/Store-Mocks prüfbar, eine Komponente mit echtem Drag nicht.
export function buildMovedSlotPayload(
  slot: ShiftSlot,
  targetWeekday: number,
  newStartMinutes: number,
  newEndMinutes: number,
): SlotInput {
  const {
    id: _id,
    workstation_name: _workstationName,
    color: _color,
    understaffed: _understaffed,
    unqualified: _unqualified,
    double_booked: _doubleBooked,
    assignments: _assignments,
    ...unchanged
  } = slot;
  return {
    ...unchanged,
    weekday: targetWeekday,
    start_time: minutesToTime(newStartMinutes),
    end_time: minutesToTime(newEndMinutes),
  };
}

export default function AdminShiftPlanning() {
  const duplicateTitleId = useId();
  const tabsId = useId();
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  // #371: configured planner weekdays — drive the week grid, day picker and slot dialog.
  const planningWeekdays = useSystemStore((s) => s.getShiftPlanningWeekdays());

  const [tab, setTab] = useState<'plans' | 'stations' | 'qualifications'>('plans');
  const [locations, setLocations] = useState<Location[]>([]);
  const [workstations, setWorkstations] = useState<Workstation[]>([]);
  const [employees, setEmployees] = useState<SlotEmployee[]>([]);
  // ui-22: Ladefehler der Mitarbeiterliste getrennt von „keine Mitarbeiter“.
  const [employeesError, setEmployeesError] = useState(false);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [planDetail, setPlanDetail] = useState<PlanDetail | null>(null);
  const [newPlanName, setNewPlanName] = useState('');
  const [creatingPlan, setCreatingPlan] = useState(false);
  const [slotDialog, setSlotDialog] = useState<SlotDialogState | null>(null);
  const [planSettingsOpen, setPlanSettingsOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  // #338: Duplizier-Dialog (null = zu); name = vorgeschlagener Name der Kopie.
  const [duplicateState, setDuplicateState] = useState<{ planId: string; name: string } | null>(null);
  const [duplicating, setDuplicating] = useState(false);
  // #321 Tagesansicht
  const [shiftView, setShiftView] = useState<'week' | 'day'>('week');
  // #371: default the day view to the first enabled weekday.
  const [dayWeekday, setDayWeekday] = useState(() => planningWeekdays[0] ?? 0);

  // #330: zugewiesene Minuten je MA für den aktuell offenen Plan — aktualisiert
  // sich automatisch, sobald sich planDetail (nach Zuweisung) ändert.
  const assignedByUser = useMemo(
    () => assignedMinutesByUser(planDetail?.slots ?? []),
    [planDetail],
  );

  // ui-13: Maus zieht nach 5 px; Touch erst nach 200 ms Halten, damit ein Wisch die Seite
  // weiter scrollt (kein touch-none an den Blöcken); Tastatur zieht die Mitarbeiter-Chips.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );

  // `toast` is a stable ref (memoised ToastContext value) and only used in the
  // catch branch — keeping it out of the deps keeps these loaders referentially
  // stable so the mount effect below doesn't re-run when a toast fires.
  const loadStations = useCallback(async () => {
    try {
      const [locs, ws] = await Promise.all([api.listLocations(), api.listWorkstations()]);
      setLocations(locs);
      setWorkstations(ws);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Stammdaten'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadPlans = useCallback(async () => {
    try {
      setPlans(await api.listPlans());
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Schichtpläne'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadEmployees = useCallback(async () => {
    try {
      const res = await apiClient.get<AdminUserRow[]>('/admin/users');
      setEmployees(
        res.data
          .filter((u) => u.is_active && !u.is_hidden)
          .map((u) => ({ id: u.id, first_name: u.first_name, last_name: u.last_name, weekly_hours: u.weekly_hours })),
      );
      setEmployeesError(false);
    } catch (err) {
      setEmployeesError(true);
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Mitarbeiter'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ui-04: nur die Antwort der zuletzt angefragten Ladung darf den Editor setzen;
  // bei einem Fehler zeigt der Editor nicht länger den vorher gewählten Plan.
  const planRequestSeq = useRef(0);
  const loadPlanDetail = useCallback(
    async (id: string) => {
      const seq = ++planRequestSeq.current;
      try {
        const detail = await api.getPlan(id);
        if (seq === planRequestSeq.current) setPlanDetail(detail);
      } catch (err) {
        if (seq !== planRequestSeq.current) return;
        setPlanDetail(null);
        toast.error(getErrorMessage(err, 'Fehler beim Laden des Plans'));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useEffect(() => {
    loadStations();
    loadPlans();
    loadEmployees();
  }, [loadStations, loadPlans, loadEmployees]);

  useEffect(() => {
    if (selectedPlanId) loadPlanDetail(selectedPlanId);
    else {
      planRequestSeq.current += 1; // eine noch laufende Ladung verwerfen
      setPlanDetail(null);
    }
  }, [selectedPlanId, loadPlanDetail]);

  // #371: if the weekday config resolves/changes after mount and the day-view
  // weekday is no longer enabled, snap it to the first enabled day so the picker
  // value can't diverge from its rendered <option>s.
  useEffect(() => {
    if (!planningWeekdays.includes(dayWeekday)) {
      setDayWeekday(planningWeekdays[0] ?? 0);
    }
  }, [planningWeekdays, dayWeekday]);

  // #340: beim ersten Laden den aktuell aktiven Plan automatisch öffnen (häufigster
  // Use-Case → spart einen Klick). Greift nur einmal (autoOpenedRef) und nur, wenn
  // noch keiner gewählt ist — drängt sich nach manueller Aus-/Abwahl nicht erneut auf.
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (autoOpenedRef.current || plans.length === 0) return;
    autoOpenedRef.current = true;
    if (!selectedPlanId) {
      const active = plans.find((p) => p.active_today) ?? plans.find((p) => p.is_active);
      if (active) setSelectedPlanId(active.id);
    }
  }, [plans, selectedPlanId]);

  const refreshSelected = async () => {
    await loadPlans();
    if (selectedPlanId) await loadPlanDetail(selectedPlanId);
  };

  const createPlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPlanName.trim() || creatingPlan) return;
    setCreatingPlan(true);
    try {
      const plan = await api.createPlan(newPlanName.trim());
      setNewPlanName('');
      toast.success('Schichtplan angelegt');
      await loadPlans();
      setSelectedPlanId(plan.id);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Anlegen'));
    } finally {
      setCreatingPlan(false);
    }
  };

  const runToggleActive = async (plan: PlanSummary) => {
    try {
      if (plan.is_active) await api.deactivatePlan(plan.id);
      else await api.activatePlan(plan.id);
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Umschalten'));
    }
  };

  // ui-11: Deaktivieren eines laufenden bzw. freigegebenen Plans nimmt ihn für
  // alle sofort aus der Mitarbeiteransicht → erst nachfragen.
  const toggleActive = (plan: PlanSummary) => {
    if (plan.is_active && (plan.active_today || plan.visible_to_employees)) {
      confirm({
        title: 'Schichtplan deaktivieren',
        message: `„${plan.name}" ist ${
          plan.visible_to_employees ? 'für Mitarbeitende sichtbar' : 'aktuell aktiv'
        }. Nach dem Deaktivieren sehen Mitarbeitende diesen Plan nicht mehr (sofern kein Zeitfenster ihn weiter aktiv hält). Deaktivieren?`,
        confirmLabel: 'Deaktivieren',
        variant: 'warning',
        onConfirm: () => runToggleActive(plan),
      });
      return;
    }
    void runToggleActive(plan);
  };

  // #338: Plan duplizieren — Dialog mit vorgeschlagenem Namen „… (Kopie)".
  const openDuplicate = (plan: { id: string; name: string }) =>
    setDuplicateState({ planId: plan.id, name: `${plan.name} (Kopie)` });

  const confirmDuplicate = async () => {
    if (!duplicateState || duplicating) return;
    const name = duplicateState.name.trim();
    if (!name) return;
    setDuplicating(true);
    try {
      const created = await api.duplicatePlan(duplicateState.planId, name);
      setDuplicateState(null);
      toast.success('Schichtplan dupliziert');
      await loadPlans();
      setSelectedPlanId(created.id);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Duplizieren'));
    } finally {
      setDuplicating(false);
    }
  };

  const removePlan = (plan: PlanSummary) =>
    confirm({
      title: 'Schichtplan löschen',
      message: `„${plan.name}" mit allen Slots und Zuweisungen löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.deletePlan(plan.id);
          toast.success('Schichtplan gelöscht');
          if (selectedPlanId === plan.id) setSelectedPlanId(null);
          await loadPlans();
        } catch (err) {
          toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
        }
      },
    });

  // #443: PDF-Aushang des offenen Plans.
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const downloadPdf = async () => {
    if (!planDetail || downloadingPdf) return;
    setDownloadingPdf(true);
    try {
      await api.downloadPlanPdf(planDetail.id, planDetail.name);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Erstellen des PDF'));
    } finally {
      setDownloadingPdf(false);
    }
  };

  // ─── slot dialog ───
  const openCreateSlot = (weekday: number) => {
    if (workstations.length === 0) {
      toast.warning('Bitte zuerst einen Arbeitsplatz unter „Stammdaten" anlegen.');
      setTab('stations');
      return;
    }
    setSlotDialog({
      open: true,
      mode: 'create',
      initial: {
        workstation_id: workstations[0].id,
        weekday,
        start_time: '08:00',
        end_time: '12:00',
        min_staff: 1,
        userIds: [],
        note: '',
      },
    });
  };

  const openEditSlot = (slot: ShiftSlot) => {
    setSlotDialog({
      open: true,
      mode: 'edit',
      slotId: slot.id,
      initial: {
        workstation_id: slot.workstation_id,
        weekday: slot.weekday,
        start_time: slot.start_time,
        end_time: slot.end_time,
        min_staff: slot.min_staff,
        userIds: slot.assignments.map((a) => a.user_id),
        note: slot.note ?? '',
      },
    });
  };

  const submitSlot = async (fields: SlotInput, userIds: string[]) => {
    if (!selectedPlanId || !slotDialog) return;
    let slotId = slotDialog.slotId;
    try {
      if (slotDialog.mode === 'create') {
        const created = await api.createSlot(selectedPlanId, fields);
        slotId = created.id;
        // ui-01: Der Slot existiert ab hier. Der Dialog wechselt in den
        // Bearbeiten-Modus, damit ein erneutes „Speichern“ ihn aktualisiert
        // statt einen zweiten, identischen Slot anzulegen.
        setSlotDialog({
          open: true,
          mode: 'edit',
          slotId: created.id,
          initial: {
            workstation_id: fields.workstation_id,
            weekday: fields.weekday,
            start_time: fields.start_time,
            end_time: fields.end_time,
            min_staff: fields.min_staff,
            userIds,
            note: fields.note ?? '',
          },
        });
      } else if (slotId) {
        await api.updateSlot(slotId, fields);
      }
      if (slotId) await api.setAssignments(slotId, userIds);
      setSlotDialog(null);
      toast.success('Slot gespeichert');
      await refreshSelected();
    } catch (err) {
      if (slotDialog.mode === 'create' && slotId) {
        toast.error(
          `Der Slot wurde angelegt, aber die Zuweisung konnte nicht gespeichert werden: ${getErrorMessage(err, 'Fehler beim Speichern')}`,
        );
        await refreshSelected();
      } else {
        toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
      }
    }
  };

  // #322: copy a slot (config + assignments) to additional weekdays.
  // ui-01: je Tag einzeln abgesichert; der Dialog schließt in jedem Fall (ein
  // Retry würde bereits angelegte Tage doppeln) und meldet, was fehlt.
  const copySlot = async (weekdays: number[], fields: SlotInput, userIds: string[]) => {
    if (!selectedPlanId) return;
    const copied: number[] = [];
    const withoutAssignment: number[] = [];
    const failed: { wd: number; err: unknown }[] = [];
    for (const wd of weekdays) {
      let createdId: string;
      try {
        createdId = (await api.createSlot(selectedPlanId, { ...fields, weekday: wd })).id;
      } catch (err) {
        failed.push({ wd, err });
        continue;
      }
      if (userIds.length) {
        try {
          await api.setAssignments(createdId, userIds);
        } catch {
          withoutAssignment.push(wd);
          continue;
        }
      }
      copied.push(wd);
    }
    setSlotDialog(null);
    await refreshSelected();
    const label = (list: number[]) => list.map((d) => api.WEEKDAY_LABELS[d]).join(', ');
    if (failed.length === 0 && withoutAssignment.length === 0) {
      toast.success(`Slot auf ${copied.length} Tag${copied.length === 1 ? '' : 'e'} kopiert`);
      return;
    }
    const parts: string[] = [];
    if (copied.length) parts.push(`kopiert: ${label(copied)}`);
    if (withoutAssignment.length) parts.push(`ohne Zuweisung angelegt: ${label(withoutAssignment)}`);
    if (failed.length) {
      parts.push(`nicht kopiert: ${label(failed.map((f) => f.wd))} (${getErrorMessage(failed[0].err, 'Fehler beim Kopieren')})`);
    }
    toast.error(`Slot nur teilweise kopiert – ${parts.join('; ')}`);
  };

  const runDeleteSlot = async (slotId: string) => {
    try {
      await api.deleteSlot(slotId);
      setSlotDialog(null);
      toast.success('Slot gelöscht');
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
    }
  };

  // ui-02: Löschen entfernt den Slot samt Zuweisungen sofort → vorher bestätigen.
  const deleteSlot = () => {
    const slotId = slotDialog?.slotId;
    if (!slotId) return;
    const n = planDetail?.slots.find((sl) => sl.id === slotId)?.assignments.length ?? 0;
    confirm({
      title: 'Slot löschen',
      message:
        n > 0
          ? `Slot löschen? ${n} Zuweisung${n === 1 ? '' : 'en'} ${n === 1 ? 'wird' : 'werden'} entfernt.`
          : 'Slot löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: () => runDeleteSlot(slotId),
    });
  };

  // ─── drag & drop ───
  const onDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !planDetail) return;
    const a = active.data.current as any;
    const o = over.data.current as any;

    if (a?.type === 'employee' && o?.type === 'slot') {
      const slot: ShiftSlot = o.slot;
      if (slot.assignments.some((x) => x.user_id === a.userId)) return; // already assigned
      try {
        await api.setAssignments(slot.id, [...slot.assignments.map((x) => x.user_id), a.userId]);
        await refreshSelected();
      } catch (err) {
        toast.error(getErrorMessage(err, 'Fehler beim Zuweisen'));
      }
      return;
    }

    if (a?.type === 'block') {
      const slot: ShiftSlot = a.slot;
      const targetWeekday = o?.type === 'day' ? o.weekday : o?.type === 'slot' ? o.slot.weekday : slot.weekday;
      // ui-06: reiner Tageswechsel behält die Zeiten, Klemmung nur bei echter Verschiebung
      const { start: newStart, end: newEnd } = movedSlotTimes(slot.start_time, slot.end_time, event.delta.y);
      if (targetWeekday === slot.weekday && newStart === timeToMinutes(slot.start_time)) return; // no-op
      try {
        await api.updateSlot(slot.id, buildMovedSlotPayload(slot, targetWeekday, newStart, newEnd));
        await refreshSelected();
      } catch (err) {
        toast.error(getErrorMessage(err, 'Fehler beim Verschieben'));
      }
    }
  };

  return (
    <div>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Schichtplanung</h1>
      </div>

      {/* Tabs (ui-12: ARIA-Tabs, auf schmalen Bildschirmen scrollbar) */}
      <div role="tablist" aria-label="Schichtplanung" className="flex gap-2 mb-6 border-b border-gray-200 overflow-x-auto">
        {([
          ['plans', CalendarDays, 'Schichtpläne'],
          ['stations', Settings2, 'Stammdaten'],
          ['qualifications', GraduationCap, 'Einweisungen'],
        ] as const).map(([key, Icon, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`${tabsId}-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`${tabsId}-panel-${key}`}
            tabIndex={tab === key ? 0 : -1}
            onClick={() => setTab(key)}
            onKeyDown={(e) => {
              const order = ['plans', 'stations', 'qualifications'] as const;
              const idx = order.indexOf(key);
              const next =
                e.key === 'ArrowRight' ? order[(idx + 1) % order.length]
                : e.key === 'ArrowLeft' ? order[(idx + order.length - 1) % order.length]
                : null;
              if (next) {
                e.preventDefault();
                setTab(next);
                document.getElementById(`${tabsId}-tab-${next}`)?.focus();
              }
            }}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${
              tab === key ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>

      {tab === 'stations' && (
        <div
          role="tabpanel"
          id={`${tabsId}-panel-stations`}
          aria-labelledby={`${tabsId}-tab-stations`}
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
        >
          <LocationManager locations={locations} onChanged={loadStations} />
          <WorkstationManager workstations={workstations} locations={locations} onChanged={loadStations} />
        </div>
      )}

      {tab === 'qualifications' && (
        <div role="tabpanel" id={`${tabsId}-panel-qualifications`} aria-labelledby={`${tabsId}-tab-qualifications`}>
          <QualificationMatrix />
        </div>
      )}

      {tab === 'plans' && (
        <div role="tabpanel" id={`${tabsId}-panel-plans`} aria-labelledby={`${tabsId}-tab-plans`}>
        <YearTimeline plans={plans} />
        <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] gap-6">
          {/* Plan list */}
          <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4 h-fit">
            <form onSubmit={createPlan} className="flex items-end gap-2 mb-4">
              <div className="flex-1">
                <FormInput
                  label="Neuer Plan"
                  value={newPlanName}
                  onChange={(e) => setNewPlanName(e.target.value)}
                  placeholder="z. B. Normalzustand"
                />
              </div>
              <Button type="submit" variant="primary" icon={Plus} loading={creatingPlan} disabled={!newPlanName.trim()}>
                <span className="sr-only">Plan anlegen</span>
              </Button>
            </form>
            {plans.length === 0 ? (
              <EmptyState icon={CalendarDays} title="Keine Pläne" description="Legen Sie einen Schichtplan an." />
            ) : (
              <ul className="space-y-1">
                {plans.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedPlanId(p.id)}
                      aria-current={selectedPlanId === p.id ? 'true' : undefined}
                      className={`w-full text-left rounded-lg px-3 py-2 text-sm flex items-center justify-between gap-2 ${
                        selectedPlanId === p.id ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                      }`}
                    >
                      <span className="flex items-center gap-2 truncate">
                        {p.active_today ? (
                          <span
                            className="h-2 w-2 rounded-full bg-green-500"
                            title={p.is_active ? 'Aktiv' : 'Heute aktiv (Zeitraum)'}
                          >
                            <span className="sr-only">{p.is_active ? 'Aktiv' : 'Heute aktiv (Zeitraum)'}</span>
                          </span>
                        ) : (
                          <span className="h-2 w-2 rounded-full bg-gray-300" title="Inaktiv">
                            <span className="sr-only">Inaktiv</span>
                          </span>
                        )}
                        <span className="truncate">{p.name}</span>
                      </span>
                      <span className="flex items-center gap-1.5 shrink-0">
                        {/* #443 F-3: Freigabe war bisher nur im "Bearbeiten"-Dialog sichtbar. */}
                        {p.visible_to_employees && (
                          <span title="Für Mitarbeitende sichtbar">
                            <Eye size={14} className="text-blue-500" />
                          </span>
                        )}
                        {p.is_valid ? (
                          <CheckCircle2 size={14} className="text-green-500" />
                        ) : (
                          <AlertTriangle size={14} className="text-amber-500" />
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Plan editor */}
          <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4 min-w-0">
            {!planDetail ? (
              <EmptyState
                icon={CalendarDays}
                title="Kein Plan ausgewählt"
                description="Wählen Sie links einen Plan oder legen Sie einen neuen an."
              />
            ) : (
              <DndContext sensors={sensors} onDragEnd={onDragEnd}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
                      {planDetail.name}
                      {/* #443 F-3: Freigabe war bisher nur im "Bearbeiten"-Dialog erkennbar — beim
                          Umräumen eines freigegebenen Plans sah der Admin sonst nicht, dass die
                          Belegschaft live zuschaut. */}
                      {planDetail.visible_to_employees && (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700"
                          title="Für Mitarbeitende sichtbar"
                        >
                          <Eye size={12} /> Sichtbar
                        </span>
                      )}
                    </h2>
                    {planDetail.description && <p className="text-sm text-gray-500">{planDetail.description}</p>}
                    {(planDetail.active_from_date || planDetail.active_until_date) && (
                      <p className="mt-1 text-xs text-gray-500">
                        Automatisch aktiv {planDetail.active_from_date ? `ab ${formatIsoDateDe(planDetail.active_from_date)}` : ''}
                        {planDetail.active_until_date ? ` bis ${formatIsoDateDe(planDetail.active_until_date)}` : ''}
                        {planDetail.active_today && !planDetail.is_active && (
                          <span className="ml-2 rounded-full bg-green-100 px-1.5 py-0.5 text-green-700">heute aktiv</span>
                        )}
                      </p>
                    )}
                    {!planDetail.validation.is_valid && (
                      <p className="mt-1 text-xs text-amber-600 flex items-center gap-1">
                        <AlertTriangle size={12} /> Unterbesetzte Slots — Plan ist aktivierbar, aber prüfen Sie die
                        Besetzung.
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant={planDetail.is_active ? 'secondary' : 'primary'}
                      icon={planDetail.is_active ? PowerOff : Power}
                      title={
                        !planDetail.is_active && planDetail.active_today
                          ? 'Der Plan gilt heute bereits über sein Zeitfenster. „Dauerhaft aktiv schalten“ setzt zusätzlich die manuelle Aktivierung, sodass er auch nach dem Fenster-Ende aktiv bleibt.'
                          : undefined
                      }
                      onClick={() => toggleActive({ ...planDetail, slot_count: 0, is_valid: planDetail.validation.is_valid })}
                    >
                      {planDetail.is_active
                        ? 'Deaktivieren'
                        : planDetail.active_today
                          ? 'Dauerhaft aktiv schalten'
                          : 'Aktiv schalten'}
                    </Button>
                    <Button
                      variant="primary"
                      icon={Plus}
                      onClick={() =>
                        openCreateSlot(shiftView === 'day' ? dayWeekday : (planningWeekdays[0] ?? 0))
                      }
                    >
                      Slot
                    </Button>
                    <Button variant="secondary" icon={Wand2} onClick={() => setGenerateOpen(true)}>
                      Automatisch füllen
                    </Button>
                    <Button variant="secondary" icon={Pencil} onClick={() => setPlanSettingsOpen(true)}>
                      Bearbeiten
                    </Button>
                    <Button variant="secondary" icon={Printer} loading={downloadingPdf} onClick={downloadPdf}>
                      PDF
                    </Button>
                    <Button variant="secondary" icon={Copy} onClick={() => openDuplicate(planDetail)}>
                      Duplizieren
                    </Button>
                    <Button
                      variant="ghost"
                      icon={Trash2}
                      onClick={() => removePlan({ ...planDetail, slot_count: 0, is_valid: planDetail.validation.is_valid })}
                      aria-label="Plan löschen"
                    >
                      <span className="sr-only">Plan löschen</span>
                    </Button>
                  </div>
                </div>

                {/* #321: Woche/Tag-Umschalter */}
                <div className="flex items-center gap-2 mb-3">
                  <div className="inline-flex rounded-lg border border-gray-300 overflow-hidden text-sm">
                    <button
                      type="button"
                      aria-pressed={shiftView === 'week'}
                      onClick={() => setShiftView('week')}
                      className={`px-3 py-1 ${shiftView === 'week' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                    >
                      Woche
                    </button>
                    <button
                      type="button"
                      aria-pressed={shiftView === 'day'}
                      onClick={() => setShiftView('day')}
                      className={`px-3 py-1 border-l border-gray-300 ${shiftView === 'day' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                    >
                      Tag
                    </button>
                  </div>
                  {shiftView === 'day' && (
                    <select
                      value={dayWeekday}
                      onChange={(e) => setDayWeekday(Number(e.target.value))}
                      className="rounded-lg border border-gray-300 text-sm py-1"
                    >
                      {/* #371: only enabled weekdays are selectable */}
                      {planningWeekdays.map((i) => (
                        <option key={i} value={i}>{api.WEEKDAY_LABELS_LONG[i]}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_200px] gap-4">
                  <WeekGrid
                    slots={planDetail.slots}
                    editable
                    onSlotClick={openEditSlot}
                    onEmptyClick={openCreateSlot}
                    singleDay={shiftView === 'day' ? dayWeekday : undefined}
                    weekdays={planningWeekdays}
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Mitarbeiter</h3>
                    <p className="text-xs text-gray-400 mb-2">Auf einen Slot ziehen zum Zuweisen.</p>
                    <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
                      {employeesError ? (
                        <p role="alert" className="text-xs text-red-600">
                          Mitarbeiter konnten nicht geladen werden.{' '}
                          <button type="button" className="underline" onClick={loadEmployees}>
                            Erneut laden
                          </button>
                        </p>
                      ) : employees.length === 0 ? (
                        <p className="text-xs text-gray-400">Keine Mitarbeiter.</p>
                      ) : (
                        employees.map((emp) => (
                          <DraggableEmployee key={emp.id} emp={emp} assignedMinutes={assignedByUser.get(emp.id) ?? 0} />
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </DndContext>
            )}
          </div>
        </div>
        </div>
      )}

      {slotDialog && (
        <SlotDialog
          isOpen={slotDialog.open}
          mode={slotDialog.mode}
          workstations={workstations}
          employees={employees}
          employeesError={employeesError}
          initial={slotDialog.initial}
          onSubmit={submitSlot}
          onDelete={slotDialog.mode === 'edit' ? deleteSlot : undefined}
          onCopy={slotDialog.mode === 'edit' ? copySlot : undefined}
          onClose={() => setSlotDialog(null)}
          weekdays={planningWeekdays}
        />
      )}

      {planSettingsOpen && planDetail && (
        <PlanSettingsDialog
          isOpen={planSettingsOpen}
          plan={planDetail}
          onSaved={refreshSelected}
          onClose={() => setPlanSettingsOpen(false)}
        />
      )}

      {generateOpen && planDetail && (
        <GenerateDialog
          planId={planDetail.id}
          assignmentCount={planDetail.slots.reduce((n, sl) => n + sl.assignments.length, 0)}
          onGenerated={refreshSelected}
          onClose={() => setGenerateOpen(false)}
        />
      )}

      {/* #338: Plan duplizieren — Name der Kopie (Focus-Trap + Enter/Escape wie die
          übrigen Dialoge, ADM round2 #4) */}
      {duplicateState && (
        <DialogFocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: true, onDeactivate: () => setDuplicateState(null) }}>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <form
              role="dialog"
              aria-modal="true"
              aria-labelledby={duplicateTitleId}
              onSubmit={(e) => { e.preventDefault(); confirmDuplicate(); }}
              className="bg-white rounded-xl shadow-lg w-full max-w-md p-5"
            >
              <h3 id={duplicateTitleId} className="text-lg font-semibold text-gray-900 mb-2">Schichtplan duplizieren</h3>
              <p className="text-sm text-gray-500 mb-3">
                Kopiert alle Zeitslots und Zuweisungen. Die Kopie ist zunächst <strong>inaktiv</strong>.
              </p>
              <FormInput
                label="Name der Kopie"
                autoFocus
                value={duplicateState.name}
                onChange={(e) => setDuplicateState({ ...duplicateState, name: e.target.value })}
                maxLength={255}  /* #461 K-9: Server-Grenze aus #450 */
              />
              <div className="flex justify-end gap-2 mt-4">
                <Button type="button" variant="secondary" onClick={() => setDuplicateState(null)}>
                  Abbrechen
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  icon={Copy}
                  disabled={duplicating || !duplicateState.name.trim()}
                >
                  Duplizieren
                </Button>
              </div>
            </form>
          </div>
        </DialogFocusTrap>
      )}
    </div>
  );
}
