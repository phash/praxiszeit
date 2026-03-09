import { useState, useEffect } from 'react';
import { format, parseISO, isBefore, startOfDay } from 'date-fns';
import { de } from 'date-fns/locale';
import { Pencil, Plus, Trash2, Check, X } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from './ConfirmDialog';
import MonthSelector from './MonthSelector';
import LoadingSpinner from './LoadingSpinner';
import SubmitChangesModal from './SubmitChangesModal';

// ---- Types ----------------------------------------------------------------

interface TimeEntryItem {
  id: string;
  start_time: string | null;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
}

interface AbsenceItem {
  id: string;
  type: string;
  hours: number;
}

interface JournalDay {
  date: string;
  weekday: string;
  type: 'work' | 'vacation' | 'sick' | 'overtime' | 'training' | 'other' | 'holiday' | 'weekend' | 'empty';
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
}

interface EditState {
  startTime: string;    // "HH:mm"
  endTime: string;      // "HH:mm"
  breakMinutes: string; // string for <input> binding
}

export interface DraftChange {
  type: 'create' | 'update' | 'delete';
  date: string;           // "YYYY-MM-DD"
  entryId?: string;       // for update/delete
  startTime?: string;     // for create/update
  endTime?: string;       // for create/update
  breakMinutes?: number;  // for create/update
}

// ---- Helper functions -----------------------------------------------------

const TYPE_LABELS: Record<string, string> = {
  work: 'Arbeitszeit',
  vacation: 'Urlaub',
  sick: 'Krank',
  overtime: 'Überstundenausgleich',
  training: 'Fortbildung',
  other: 'Sonstiges',
  holiday: 'Feiertag',
  weekend: '',
  empty: '–',
};

const TYPE_COLORS: Record<string, string> = {
  work: 'text-gray-900',
  vacation: 'text-blue-600',
  sick: 'text-orange-600',
  overtime: 'text-purple-600',
  training: 'text-green-600',
  other: 'text-gray-600',
  holiday: 'text-red-600',
  weekend: 'text-gray-400',
  empty: 'text-gray-400',
};

function formatHours(h: number): string {
  if (h === 0) return '–';
  const sign = h < 0 ? '-' : '+';
  const abs = Math.abs(h);
  const hours = Math.floor(abs);
  const mins = Math.round((abs - hours) * 60);
  return mins > 0 ? `${sign}${hours}h ${mins}min` : `${sign}${hours}h`;
}

function formatHoursSimple(h: number): string {
  if (h === 0) return '–';
  const hours = Math.floor(h);
  const mins = Math.round((h - hours) * 60);
  return mins > 0 ? `${hours}h ${mins}min` : `${hours}h`;
}

function isPastDay(dateStr: string): boolean {
  return isBefore(parseISO(dateStr), startOfDay(new Date()));
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [editingDate, setEditingDate] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState>({ startTime: '', endTime: '', breakMinutes: '0' });
  const [saving, setSaving] = useState(false);
  const [draftChanges, setDraftChanges] = useState<DraftChange[]>([]);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const [year, month] = selectedMonth.split('-').map(Number);
    const url = isAdminView
      ? `/admin/users/${userId}/journal?year=${year}&month=${month}`
      : `/journal/me?year=${year}&month=${month}`;

    setLoading(true);
    setError(null);

    apiClient
      .get(url, { signal: controller.signal })
      .then((res) => setData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED') return;
        setError(getErrorMessage(err, 'Journal konnte nicht geladen werden.'));
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [selectedMonth, userId, isAdminView, reloadKey]);

  const isNonWorkDay = (day: JournalDay) =>
    day.type === 'weekend' || day.type === 'holiday';

  function startEdit(day: JournalDay) {
    const entry = day.time_entries[0] ?? null;
    setEditingDate(day.date);
    setEditState({
      startTime: entry?.start_time ?? '',
      endTime: entry?.end_time ?? '',
      breakMinutes: String(entry?.break_minutes ?? 0),
    });
  }

  function cancelEdit() {
    setEditingDate(null);
  }

  async function handleAdminSave(day: JournalDay) {
    const start = editState.startTime;
    const end = editState.endTime;
    if (!start || !end) {
      toast.error('Von und Bis sind Pflichtfelder');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        start_time: start,
        end_time: end,
        break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
      };
      const existing = day.time_entries[0];
      if (existing) {
        await apiClient.put(`/admin/time-entries/${existing.id}`, payload);
      } else {
        await apiClient.post(`/admin/users/${userId}/time-entries`, {
          date: day.date,
          ...payload,
        });
      }
      toast.success('Gespeichert');
      cancelEdit();
      setReloadKey(k => k + 1);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSaving(false);
    }
  }

  function handleAdminDelete(day: JournalDay) {
    const entry = day.time_entries[0];
    if (!entry) return;
    confirm({
      title: 'Eintrag löschen',
      message: 'Soll dieser Eintrag wirklich gelöscht werden?',
      variant: 'danger',
      confirmLabel: 'Löschen',
      onConfirm: () => {
        setSaving(true);
        apiClient.delete(`/admin/time-entries/${entry.id}`)
          .then(() => {
            toast.success('Eintrag gelöscht');
            cancelEdit();
            setReloadKey(k => k + 1);
          })
          .catch((err: unknown) => {
            toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
          })
          .finally(() => {
            setSaving(false);
          });
      },
    });
  }

  function handleEmployeeSave(day: JournalDay) {
    const start = editState.startTime;
    const end = editState.endTime;
    if (!start || !end) {
      toast.error('Von und Bis sind Pflichtfelder');
      return;
    }
    const existing = day.time_entries[0];
    const change: DraftChange = {
      type: existing ? 'update' : 'create',
      date: day.date,
      entryId: existing?.id,
      startTime: start,
      endTime: end,
      breakMinutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
    };
    setDraftChanges(prev => {
      const filtered = prev.filter(c => c.date !== day.date);
      return [...filtered, change];
    });
    cancelEdit();
  }

  function handleEmployeeDelete(day: JournalDay) {
    const entry = day.time_entries[0];
    if (!entry) return;
    const change: DraftChange = {
      type: 'delete',
      date: day.date,
      entryId: entry.id,
    };
    setDraftChanges(prev => {
      const filtered = prev.filter(c => c.date !== day.date);
      return [...filtered, change];
    });
    cancelEdit();
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
          setDraftChanges([]);
          cancelEdit();
        }}
      />

      {loading && <LoadingSpinner />}
      {error && <p className="text-red-600">{error}</p>}

      {data && !loading && (
        <>
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
                  <th className="px-3 py-2 text-right">Soll</th>
                  <th className="px-3 py-2 text-right">Saldo</th>
                  <th className="px-3 py-2 text-right w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.days.map((day) => {
                  const dateObj = parseISO(day.date);
                  const isGray = isNonWorkDay(day);
                  const draft = draftChanges.find(c => c.date === day.date);
                  const isDraft = !!draft;
                  const isDraftDelete = draft?.type === 'delete';
                  const rowClass = isGray
                    ? 'bg-gray-50 text-gray-400'
                    : isDraft
                    ? 'bg-amber-50'
                    : 'bg-white';

                  const entry = day.time_entries[0] ?? null;
                  const vonBis =
                    entry && entry.start_time && entry.end_time
                      ? `${entry.start_time}–${entry.end_time}`
                      : '–';
                  const pause =
                    entry && entry.break_minutes > 0
                      ? `${entry.break_minutes} min`
                      : '–';

                  const multiEntry = day.time_entries.length > 1;

                  const balanceColor =
                    isGray || day.type === 'empty'
                      ? 'text-gray-400'
                      : day.balance > 0
                      ? 'text-green-600 font-medium'
                      : day.balance < 0
                      ? 'text-red-600 font-medium'
                      : 'text-gray-600';

                  return (
                    <tr key={day.date} className={`${rowClass} hover:bg-gray-50 transition-colors`}>
                      <td className="px-3 py-2 font-medium whitespace-nowrap">
                        {format(dateObj, 'dd.MM.', { locale: de })}
                      </td>
                      <td className="px-3 py-2 hidden sm:table-cell">
                        {format(dateObj, 'EEE', { locale: de })}
                      </td>
                      <td className={`px-3 py-2 ${TYPE_COLORS[day.type]}`}>
                        {day.is_holiday && day.holiday_name
                          ? day.holiday_name
                          : TYPE_LABELS[day.type] ?? day.type}
                        {multiEntry && (
                          <span className="ml-1 text-xs text-gray-400">
                            ({day.time_entries.length}×)
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 hidden md:table-cell text-gray-600 whitespace-nowrap">
                        {isGray ? '–' : editingDate === day.date ? (
                          <div className="flex items-center gap-1">
                            <input
                              type="time"
                              value={editState.startTime}
                              onChange={(e) => setEditState(s => ({ ...s, startTime: e.target.value }))}
                              className="w-[5.5rem] border border-gray-300 rounded px-1 py-0.5 text-sm"
                            />
                            <span className="text-gray-400">–</span>
                            <input
                              type="time"
                              value={editState.endTime}
                              onChange={(e) => setEditState(s => ({ ...s, endTime: e.target.value }))}
                              className="w-[5.5rem] border border-gray-300 rounded px-1 py-0.5 text-sm"
                            />
                          </div>
                        ) : isDraft && draft!.type !== 'delete' ? (
                          <span className="text-amber-700">{draft!.startTime}–{draft!.endTime}</span>
                        ) : isDraftDelete ? (
                          <span className="line-through text-gray-400">{vonBis}</span>
                        ) : vonBis}
                      </td>
                      <td className="px-3 py-2 hidden md:table-cell text-right text-gray-500">
                        {isGray ? '' : editingDate === day.date ? (
                          <input
                            type="number"
                            min={0}
                            max={480}
                            value={editState.breakMinutes}
                            onChange={(e) => setEditState(s => ({ ...s, breakMinutes: e.target.value }))}
                            className="w-16 border border-gray-300 rounded px-1 py-0.5 text-sm text-right"
                          />
                        ) : pause}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-700">
                        {isGray ? '' : formatHoursSimple(day.actual_hours)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-500">
                        {isGray ? '' : formatHoursSimple(day.target_hours)}
                      </td>
                      <td className={`px-3 py-2 text-right ${balanceColor}`}>
                        {isGray ? '' : formatHours(day.balance)}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {editingDate === day.date ? (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => isAdminView ? void handleAdminSave(day) : handleEmployeeSave(day)}
                              disabled={saving}
                              className="p-1 text-green-600 hover:text-green-800 disabled:opacity-50"
                              title="Speichern"
                            >
                              <Check size={15} />
                            </button>
                            <button
                              onClick={cancelEdit}
                              disabled={saving}
                              className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                              title="Abbrechen"
                            >
                              <X size={15} />
                            </button>
                            {day.time_entries.length > 0 && (
                              <button
                                onClick={() => isAdminView ? void handleAdminDelete(day) : handleEmployeeDelete(day)}
                                disabled={saving}
                                className="p-1 text-red-400 hover:text-red-600 disabled:opacity-50"
                                title="Löschen"
                              >
                                <Trash2 size={15} />
                              </button>
                            )}
                          </div>
                        ) : !isGray && isPastDay(day.date) ? (
                          day.time_entries.length > 1 ? (
                            <span className="text-xs text-gray-400 px-1" title="Mehrere Einträge – Bearbeitung hier nicht möglich">
                              {day.time_entries.length}×
                            </span>
                          ) : day.time_entries.length === 1 ? (
                            <button
                              onClick={() => startEdit(day)}
                              className="p-1 text-gray-400 hover:text-gray-600"
                              title="Bearbeiten"
                            >
                              <Pencil size={14} />
                            </button>
                          ) : (
                            <button
                              onClick={() => startEdit(day)}
                              className="p-1 text-blue-400 hover:text-blue-600"
                              title="Eintrag anlegen"
                            >
                              <Plus size={14} />
                            </button>
                          )
                        ) : null}
                      </td>
                    </tr>
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

          {/* Employee: pending changes footer */}
          {!isAdminView && draftChanges.length > 0 && (
            <div className="sticky bottom-4 bg-amber-50 border border-amber-200 rounded-lg shadow-md p-3 flex items-center justify-between">
              <span className="text-sm text-amber-800">
                <strong>{draftChanges.length}</strong> Änderung{draftChanges.length > 1 ? 'en' : ''} ausstehend
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setDraftChanges([])}
                  className="text-sm text-amber-700 hover:text-amber-900 underline"
                >
                  Verwerfen
                </button>
                <button
                  onClick={() => setShowSubmitModal(true)}
                  className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700"
                >
                  Absenden
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {showSubmitModal && (
        <SubmitChangesModal
          changes={draftChanges}
          onSuccess={() => {
            setShowSubmitModal(false);
            setDraftChanges([]);
            setReloadKey(k => k + 1);
          }}
          onClose={() => setShowSubmitModal(false)}
        />
      )}
    </div>
  );
}
