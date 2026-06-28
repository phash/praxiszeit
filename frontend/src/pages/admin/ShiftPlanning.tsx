import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  DndContext,
  PointerSensor,
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
} from 'lucide-react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../api/client';
import Button from '../../components/Button';
import FormInput from '../../components/FormInput';
import EmptyState from '../../components/EmptyState';
import ConfirmDialog from '../../components/ConfirmDialog';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import { getErrorMessage } from '../../utils/errorMessage';
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
  snap,
  pxDeltaToMinutes,
  GRID_START_HOUR,
  GRID_END_HOUR,
} from '../../components/shiftplanning/weekGridUtils';
import * as api from '../../api/shiftPlanning';
import type { Location, Workstation, PlanSummary, PlanDetail, ShiftSlot, SlotInput } from '../../api/shiftPlanning';
import { assignedMinutesByUser, formatLoad, loadColor } from '../../components/shiftplanning/employeeLoad';

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
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm cursor-grab touch-none hover:border-primary"
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

export default function AdminShiftPlanning() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  const [tab, setTab] = useState<'plans' | 'stations' | 'qualifications'>('plans');
  const [locations, setLocations] = useState<Location[]>([]);
  const [workstations, setWorkstations] = useState<Workstation[]>([]);
  const [employees, setEmployees] = useState<SlotEmployee[]>([]);
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
  const [dayWeekday, setDayWeekday] = useState(0);

  // #330: zugewiesene Minuten je MA für den aktuell offenen Plan — aktualisiert
  // sich automatisch, sobald sich planDetail (nach Zuweisung) ändert.
  const assignedByUser = useMemo(
    () => assignedMinutesByUser(planDetail?.slots ?? []),
    [planDetail],
  );

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const loadStations = useCallback(async () => {
    try {
      const [locs, ws] = await Promise.all([api.listLocations(), api.listWorkstations()]);
      setLocations(locs);
      setWorkstations(ws);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Stammdaten'));
    }
  }, [toast]);

  const loadPlans = useCallback(async () => {
    try {
      setPlans(await api.listPlans());
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Schichtpläne'));
    }
  }, [toast]);

  const loadEmployees = useCallback(async () => {
    try {
      const res = await apiClient.get('/admin/users');
      setEmployees(
        res.data
          .filter((u: any) => u.is_active && !u.is_hidden)
          .map((u: any) => ({ id: u.id, first_name: u.first_name, last_name: u.last_name, weekly_hours: u.weekly_hours })),
      );
    } catch {
      /* employees are optional for the grid; ignore */
    }
  }, []);

  const loadPlanDetail = useCallback(
    async (id: string) => {
      try {
        setPlanDetail(await api.getPlan(id));
      } catch (err) {
        toast.error(getErrorMessage(err, 'Fehler beim Laden des Plans'));
      }
    },
    [toast],
  );

  useEffect(() => {
    loadStations();
    loadPlans();
    loadEmployees();
  }, [loadStations, loadPlans, loadEmployees]);

  useEffect(() => {
    if (selectedPlanId) loadPlanDetail(selectedPlanId);
    else setPlanDetail(null);
  }, [selectedPlanId, loadPlanDetail]);

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

  const toggleActive = async (plan: PlanSummary) => {
    try {
      if (plan.is_active) await api.deactivatePlan(plan.id);
      else await api.activatePlan(plan.id);
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Umschalten'));
    }
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
      },
    });
  };

  const submitSlot = async (fields: SlotInput, userIds: string[]) => {
    if (!selectedPlanId || !slotDialog) return;
    try {
      let slotId = slotDialog.slotId;
      if (slotDialog.mode === 'create') {
        const created = await api.createSlot(selectedPlanId, fields);
        slotId = created.id;
      } else if (slotId) {
        await api.updateSlot(slotId, fields);
      }
      if (slotId) await api.setAssignments(slotId, userIds);
      setSlotDialog(null);
      toast.success('Slot gespeichert');
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    }
  };

  // #322: copy a slot (config + assignments) to additional weekdays.
  const copySlot = async (weekdays: number[], fields: SlotInput, userIds: string[]) => {
    if (!selectedPlanId) return;
    try {
      for (const wd of weekdays) {
        const created = await api.createSlot(selectedPlanId, { ...fields, weekday: wd });
        if (userIds.length) await api.setAssignments(created.id, userIds);
      }
      setSlotDialog(null);
      toast.success(`Slot auf ${weekdays.length} Tag${weekdays.length === 1 ? '' : 'e'} kopiert`);
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Kopieren'));
    }
  };

  const deleteSlot = async () => {
    if (!slotDialog?.slotId) return;
    try {
      await api.deleteSlot(slotDialog.slotId);
      setSlotDialog(null);
      toast.success('Slot gelöscht');
      await refreshSelected();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
    }
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
      const duration = timeToMinutes(slot.end_time) - timeToMinutes(slot.start_time);
      let newStart = snap(timeToMinutes(slot.start_time) + pxDeltaToMinutes(event.delta.y));
      // clamp inside the visible grid
      newStart = Math.max(GRID_START_HOUR * 60, Math.min(GRID_END_HOUR * 60 - duration, newStart));
      const newEnd = newStart + duration;
      if (targetWeekday === slot.weekday && newStart === timeToMinutes(slot.start_time)) return; // no-op
      try {
        await api.updateSlot(slot.id, {
          workstation_id: slot.workstation_id,
          weekday: targetWeekday,
          start_time: minutesToTime(newStart),
          end_time: minutesToTime(newEnd),
          min_staff: slot.min_staff,
        });
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

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-gray-200">
        <button
          onClick={() => setTab('plans')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'plans' ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <CalendarDays size={16} /> Schichtpläne
        </button>
        <button
          onClick={() => setTab('stations')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'stations' ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Settings2 size={16} /> Stammdaten
        </button>
        <button
          onClick={() => setTab('qualifications')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'qualifications' ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <GraduationCap size={16} /> Einweisungen
        </button>
      </div>

      {tab === 'stations' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <LocationManager locations={locations} onChanged={loadStations} />
          <WorkstationManager workstations={workstations} locations={locations} onChanged={loadStations} />
        </div>
      )}

      {tab === 'qualifications' && <QualificationMatrix />}

      {tab === 'plans' && (
        <>
        <YearTimeline plans={plans} />
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
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
                      onClick={() => setSelectedPlanId(p.id)}
                      className={`w-full text-left rounded-lg px-3 py-2 text-sm flex items-center justify-between gap-2 ${
                        selectedPlanId === p.id ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                      }`}
                    >
                      <span className="flex items-center gap-2 truncate">
                        {p.active_today ? (
                          <span
                            className="h-2 w-2 rounded-full bg-green-500"
                            title={p.is_active ? 'Aktiv' : 'Heute aktiv (Zeitraum)'}
                          />
                        ) : (
                          <span className="h-2 w-2 rounded-full bg-gray-300" title="Inaktiv" />
                        )}
                        <span className="truncate">{p.name}</span>
                      </span>
                      {p.is_valid ? (
                        <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                      ) : (
                        <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                      )}
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
                    <h2 className="text-xl font-semibold text-gray-900">{planDetail.name}</h2>
                    {planDetail.description && <p className="text-sm text-gray-500">{planDetail.description}</p>}
                    {(planDetail.active_from_date || planDetail.active_until_date) && (
                      <p className="mt-1 text-xs text-gray-500">
                        Automatisch aktiv {planDetail.active_from_date ? `ab ${planDetail.active_from_date}` : ''}
                        {planDetail.active_until_date ? ` bis ${planDetail.active_until_date}` : ''}
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
                  <div className="flex items-center gap-2">
                    <Button
                      variant={planDetail.is_active ? 'secondary' : 'primary'}
                      icon={planDetail.is_active ? PowerOff : Power}
                      onClick={() => toggleActive({ ...planDetail, slot_count: 0, is_valid: planDetail.validation.is_valid })}
                    >
                      {planDetail.is_active ? 'Deaktivieren' : 'Aktiv schalten'}
                    </Button>
                    <Button variant="primary" icon={Plus} onClick={() => openCreateSlot(0)}>
                      Slot
                    </Button>
                    <Button variant="secondary" icon={Wand2} onClick={() => setGenerateOpen(true)}>
                      Automatisch füllen
                    </Button>
                    <Button variant="secondary" icon={Pencil} onClick={() => setPlanSettingsOpen(true)}>
                      Bearbeiten
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
                      onClick={() => setShiftView('week')}
                      className={`px-3 py-1 ${shiftView === 'week' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
                    >
                      Woche
                    </button>
                    <button
                      type="button"
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
                      className="rounded-lg border-gray-300 text-sm py-1"
                    >
                      {api.WEEKDAY_LABELS_LONG.map((label, i) => (
                        <option key={i} value={i}>{label}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-[1fr_200px] gap-4">
                  <WeekGrid
                    slots={planDetail.slots}
                    editable
                    onSlotClick={openEditSlot}
                    onEmptyClick={openCreateSlot}
                    singleDay={shiftView === 'day' ? dayWeekday : undefined}
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Mitarbeiter</h3>
                    <p className="text-xs text-gray-400 mb-2">Auf einen Slot ziehen zum Zuweisen.</p>
                    <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
                      {employees.length === 0 ? (
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
        </>
      )}

      {slotDialog && (
        <SlotDialog
          isOpen={slotDialog.open}
          mode={slotDialog.mode}
          workstations={workstations}
          employees={employees}
          initial={slotDialog.initial}
          onSubmit={submitSlot}
          onDelete={slotDialog.mode === 'edit' ? deleteSlot : undefined}
          onCopy={slotDialog.mode === 'edit' ? copySlot : undefined}
          onClose={() => setSlotDialog(null)}
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
          onGenerated={refreshSelected}
          onClose={() => setGenerateOpen(false)}
        />
      )}

      {/* #338: Plan duplizieren — Name der Kopie (Focus-Trap + Enter/Escape wie die
          übrigen Dialoge, ADM round2 #4) */}
      {duplicateState && (
        <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: true, onDeactivate: () => setDuplicateState(null) }}>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <form
              onSubmit={(e) => { e.preventDefault(); confirmDuplicate(); }}
              className="bg-white rounded-xl shadow-lg w-full max-w-md p-5"
            >
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Schichtplan duplizieren</h3>
              <p className="text-sm text-gray-500 mb-3">
                Kopiert alle Zeitslots und Zuweisungen. Die Kopie ist zunächst <strong>inaktiv</strong>.
              </p>
              <FormInput
                label="Name der Kopie"
                autoFocus
                value={duplicateState.name}
                onChange={(e) => setDuplicateState({ ...duplicateState, name: e.target.value })}
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
        </FocusTrap>
      )}
    </div>
  );
}
