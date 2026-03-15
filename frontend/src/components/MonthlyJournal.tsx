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
  entryType: 'work' | 'sick' | 'training' | 'overtime' | 'other';
  absenceHours: string;
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
  const [editState, setEditState] = useState<EditState>({ startTime: '', endTime: '', breakMinutes: '0', entryType: 'work', absenceHours: '8' });
  const [saving, setSaving] = useState(false);
  const [submittingDate, setSubmittingDate] = useState<string | null>(null);
  const [submitReason, setSubmitReason] = useState('');
  const [savingChangeRequest, setSavingChangeRequest] = useState(false);
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
    const absence = day.absences[0] ?? null;
    const hasTimeEntry = !!entry;
    const hasAbsence = !hasTimeEntry && !!absence;
    setEditingDate(day.date);
    setEditState({
      startTime: entry?.start_time ?? '',
      endTime: entry?.end_time ?? '',
      breakMinutes: String(entry?.break_minutes ?? 0),
      entryType: hasAbsence ? (absence.type as EditState['entryType']) : 'work',
      absenceHours: hasAbsence ? String(absence.hours) : '8',
    });
  }

  function cancelEdit() {
    setEditingDate(null);
    setSubmittingDate(null);
  }

  async function handleAdminSave(day: JournalDay) {
    setSaving(true);
    try {
      if (editState.entryType === 'work') {
        const start = editState.startTime;
        const end = editState.endTime;
        if (!start || !end) {
          toast.error('Von und Bis sind Pflichtfelder');
          setSaving(false);
          return;
        }
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
      } else {
        // Absence entry
        await apiClient.post('/absences', {
          user_id: userId,
          date: day.date,
          type: editState.entryType,
          hours: parseFloat(editState.absenceHours) || 0,
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

  function startEmployeeSubmit(day: JournalDay) {
    const start = editState.startTime;
    const end = editState.endTime;
    if (!start || !end) {
      toast.error('Von und Bis sind Pflichtfelder');
      return;
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
      const existing = day.time_entries[0];
      const payload: Record<string, unknown> = {
        request_type: existing ? 'update' : 'create',
        reason: submitReason.trim(),
        proposed_date: day.date,
        proposed_start_time: editState.startTime,
        proposed_end_time: editState.endTime,
        proposed_break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
      };
      if (existing) payload.time_entry_id = existing.id;
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

                  const rowClass = isGray
                    ? 'bg-gray-50 text-gray-400'
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
                    <>
                      <tr key={day.date} className={`${rowClass} hover:bg-gray-50 transition-colors`}>
                        <td className="px-3 py-2 font-medium whitespace-nowrap">
                          {format(dateObj, 'dd.MM.', { locale: de })}
                        </td>
                        <td className="px-3 py-2 hidden sm:table-cell">
                          {format(dateObj, 'EEE', { locale: de })}
                        </td>
                        <td className={`px-3 py-2 ${TYPE_COLORS[day.type]}`}>
                          {editingDate === day.date && isAdminView && !day.time_entries.length && !day.absences.length ? (
                            <select
                              value={editState.entryType}
                              onChange={(e) => setEditState(s => ({ ...s, entryType: e.target.value as EditState['entryType'] }))}
                              className="border border-gray-300 rounded px-1 py-0.5 text-sm"
                            >
                              <option value="work">Arbeit</option>
                              <option value="sick">Krank</option>
                              <option value="training">Fortbildung</option>
                              <option value="overtime">ÜSt-Ausgleich</option>
                              <option value="other">Sonstiges</option>
                            </select>
                          ) : (
                            <>
                              {day.is_holiday && day.holiday_name
                                ? day.holiday_name
                                : TYPE_LABELS[day.type] ?? day.type}
                              {multiEntry && (
                                <span className="ml-1 text-xs text-gray-400">
                                  ({day.time_entries.length}×)
                                </span>
                              )}
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
                            ) : (
                              <input
                                type="number"
                                step="0.5"
                                min={0}
                                max={24}
                                value={editState.absenceHours}
                                onChange={(e) => setEditState(s => ({ ...s, absenceHours: e.target.value }))}
                                className="w-20 border border-gray-300 rounded px-1 py-0.5 text-sm"
                                placeholder="Stunden"
                              />
                            )
                          ) : vonBis}
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
                              className="w-16 border border-gray-300 rounded px-1 py-0.5 text-sm text-right"
                            />
                          ) : editingDate === day.date ? '' : pause}
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
                              {day.time_entries.length > 0 && (
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
                          ) : !isGray && isPastDay(day.date) ? (
                            day.time_entries.length > 1 ? (
                              <span className="text-xs text-gray-400 px-1" title="Mehrere Einträge – Bearbeitung hier nicht möglich">
                                {day.time_entries.length}×
                              </span>
                            ) : day.time_entries.length === 1 ? (
                              <button
                                onClick={() => startEdit(day)}
                                className="p-2.5 text-gray-400 hover:text-gray-600"
                                title="Bearbeiten"
                              >
                                <Pencil size={14} />
                              </button>
                            ) : (
                              <button
                                onClick={() => startEdit(day)}
                                className="p-2.5 text-blue-400 hover:text-blue-600"
                                title="Eintrag anlegen"
                              >
                                <Plus size={14} />
                              </button>
                            )
                          ) : null}
                        </td>
                      </tr>
                      {submittingDate === day.date && !isAdminView && (
                        <tr key={`${day.date}-reason`} className="bg-blue-50">
                          <td colSpan={9} className="px-3 py-2">
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
                    </>
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
