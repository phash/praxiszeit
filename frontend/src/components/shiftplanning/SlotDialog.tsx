import { useEffect, useState } from 'react';
import FocusTrap from 'focus-trap-react';
import { X, Trash2, AlertTriangle } from 'lucide-react';
import Button from '../Button';
import FormSelect from '../FormSelect';
import FormInput from '../FormInput';
import { getQualifications, WEEKDAY_LABELS, WEEKDAY_LABELS_LONG, type Workstation, type SlotInput } from '../../api/shiftPlanning';
import { Copy } from 'lucide-react';

export interface SlotEmployee {
  id: string;
  first_name: string;
  last_name: string;
  weekly_hours?: number; // #330: contract weekly hours, for the assigned-vs-contract badge
}

export interface SlotDialogInitial {
  workstation_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  min_staff: number;
  userIds: string[];
}

interface SlotDialogProps {
  isOpen: boolean;
  mode: 'create' | 'edit';
  workstations: Workstation[];
  employees: SlotEmployee[];
  initial: SlotDialogInitial;
  onSubmit: (fields: SlotInput, userIds: string[]) => Promise<void> | void;
  onDelete?: () => void;
  onClose: () => void;
  // #322: copy this slot (same workstation/time/min_staff + assignments) to other weekdays.
  onCopy?: (weekdays: number[], fields: SlotInput, userIds: string[]) => Promise<void> | void;
}

export default function SlotDialog({
  isOpen,
  mode,
  workstations,
  employees,
  initial,
  onSubmit,
  onDelete,
  onClose,
  onCopy,
}: SlotDialogProps) {
  const [workstationId, setWorkstationId] = useState(initial.workstation_id);
  const [weekday, setWeekday] = useState(initial.weekday);
  const [start, setStart] = useState(initial.start_time);
  const [end, setEnd] = useState(initial.end_time);
  const [minStaff, setMinStaff] = useState(initial.min_staff);
  const [userIds, setUserIds] = useState<string[]>(initial.userIds);
  const [submitting, setSubmitting] = useState(false);
  const [copyDays, setCopyDays] = useState<number[]>([]); // #322
  const [copying, setCopying] = useState(false);
  // #305 M2d: workstation_id -> set of qualified user_ids (for the "not trained" hint)
  const [qualifiedByWs, setQualifiedByWs] = useState<Record<string, Set<string>>>({});

  useEffect(() => {
    if (isOpen) {
      setWorkstationId(initial.workstation_id);
      setWeekday(initial.weekday);
      setStart(initial.start_time);
      setEnd(initial.end_time);
      setMinStaff(initial.min_staff);
      setUserIds(initial.userIds);
      setCopyDays([]);
      getQualifications()
        .then((m) => {
          const map: Record<string, Set<string>> = {};
          m.qualifications.forEach((q) => {
            (map[q.workstation_id] ??= new Set()).add(q.user_id);
          });
          setQualifiedByWs(map);
        })
        .catch(() => setQualifiedByWs({}));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const isQualified = (userId: string) =>
    !workstationId || (qualifiedByWs[workstationId]?.has(userId) ?? false);

  const timeInvalid = end <= start;
  const noWorkstation = !workstationId;

  const toggleUser = (id: string) =>
    setUserIds((prev) => (prev.includes(id) ? prev.filter((u) => u !== id) : [...prev, id]));

  const toggleCopyDay = (d: number) =>
    setCopyDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));

  const handleCopy = async () => {
    if (!onCopy || copyDays.length === 0 || timeInvalid || noWorkstation || copying) return;
    setCopying(true);
    try {
      await onCopy(
        copyDays,
        { workstation_id: workstationId, weekday, start_time: start, end_time: end, min_staff: minStaff },
        userIds,
      );
    } finally {
      setCopying(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (timeInvalid || noWorkstation || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(
        { workstation_id: workstationId, weekday, start_time: start, end_time: end, min_staff: minStaff },
        userIds,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: true, onDeactivate: onClose }}>
        <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between border-b border-gray-200 p-4">
            <h3 className="text-lg font-semibold text-gray-900">
              {mode === 'create' ? 'Neuer Zeitslot' : 'Zeitslot bearbeiten'}
            </h3>
            <button onClick={onClose} aria-label="Schließen" className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            <FormSelect
              label="Arbeitsplatz"
              value={workstationId}
              onChange={(e) => setWorkstationId(e.target.value)}
              required
            >
              <option value="">Bitte wählen</option>
              {workstations.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                  {ws.location_name ? ` (${ws.location_name})` : ''}
                </option>
              ))}
            </FormSelect>

            <FormSelect label="Wochentag" value={String(weekday)} onChange={(e) => setWeekday(Number(e.target.value))}>
              {WEEKDAY_LABELS_LONG.map((label, i) => (
                <option key={i} value={i}>
                  {label}
                </option>
              ))}
            </FormSelect>

            <div className="grid grid-cols-2 gap-4">
              <FormInput
                label="Von"
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
              />
              <FormInput
                label="Bis"
                type="time"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                required
                error={timeInvalid ? 'Ende muss nach dem Beginn liegen' : undefined}
              />
            </div>

            <FormInput
              label="Mindestbesetzung"
              type="number"
              min={0}
              value={minStaff}
              onChange={(e) => setMinStaff(Math.max(0, Number(e.target.value)))}
              helperText="0 = keine Mindestbesetzung; sonst wird der Slot bei Unterbesetzung markiert."
            />

            <div>
              <span className="block text-sm font-medium text-gray-700 mb-2">Zugewiesene Mitarbeiter</span>
              <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-100">
                {employees.length === 0 ? (
                  <p className="p-3 text-sm text-gray-500">Keine Mitarbeiter verfügbar.</p>
                ) : (
                  employees.map((emp) => (
                    <label
                      key={emp.id}
                      className="flex items-center gap-3 p-2 hover:bg-gray-50 cursor-pointer text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={userIds.includes(emp.id)}
                        onChange={() => toggleUser(emp.id)}
                        className="rounded border-gray-300"
                      />
                      <span className="flex items-center gap-2">
                        {emp.first_name} {emp.last_name}
                        {!isQualified(emp.id) && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">
                            <AlertTriangle size={11} /> nicht eingewiesen
                          </span>
                        )}
                      </span>
                    </label>
                  ))
                )}
              </div>
              {minStaff > 0 && userIds.length < minStaff && (
                <p className="mt-1 text-xs text-amber-600">
                  Unterbesetzt: {userIds.length}/{minStaff} zugewiesen.
                </p>
              )}
            </div>

            {mode === 'edit' && onCopy && (
              <div className="rounded-lg border border-gray-200 p-3">
                <span className="block text-sm font-medium text-gray-700 mb-2">
                  Auf Wochentage kopieren
                </span>
                <p className="text-xs text-gray-400 mb-2">
                  Legt diesen Slot (Arbeitsplatz, Zeit, Mindestbesetzung und Zuweisungen) auf den gewählten
                  Tagen zusätzlich an.
                </p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {WEEKDAY_LABELS.map((label, i) =>
                    i === weekday ? null : (
                      <button
                        type="button"
                        key={i}
                        onClick={() => toggleCopyDay(i)}
                        className={`rounded-full px-2.5 py-1 text-xs border transition-colors ${
                          copyDays.includes(i)
                            ? 'bg-primary text-white border-primary'
                            : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        {label}
                      </button>
                    ),
                  )}
                </div>
                <Button
                  variant="secondary"
                  type="button"
                  icon={Copy}
                  loading={copying}
                  disabled={copying || copyDays.length === 0 || timeInvalid || noWorkstation}
                  onClick={handleCopy}
                >
                  Auf {copyDays.length} Tag{copyDays.length === 1 ? '' : 'e'} kopieren
                </Button>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              {mode === 'edit' && onDelete ? (
                <Button variant="danger" type="button" icon={Trash2} onClick={onDelete}>
                  Löschen
                </Button>
              ) : (
                <span />
              )}
              <div className="flex gap-2">
                <Button variant="secondary" type="button" onClick={onClose}>
                  Abbrechen
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  loading={submitting}
                  disabled={submitting || timeInvalid || noWorkstation}
                >
                  Speichern
                </Button>
              </div>
            </div>
          </form>
        </div>
      </FocusTrap>
    </div>
  );
}
