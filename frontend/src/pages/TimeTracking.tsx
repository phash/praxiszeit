import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import apiClient from '../api/client';
import Journal from './Journal';
import ChangeRequests from './ChangeRequests';
import { Plus, Edit2, Trash2, Save, X, Lock, FileEdit } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import { useAuthStore } from '../stores/authStore';
import ConfirmDialog from '../components/ConfirmDialog';
import ChangeRequestForm from '../components/ChangeRequestForm';
import LoadingSpinner from '../components/LoadingSpinner';
import MonthSelector from '../components/MonthSelector';
import Button from '../components/Button';
import EmptyState from '../components/EmptyState';
import { getErrorMessage, formatHoursHM } from '../utils/errorMessage';

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
  note?: string;
  is_editable: boolean;
  warnings: string[];
  is_sunday_or_holiday: boolean;
  is_night_work: boolean;
  sunday_exception_reason?: string | null;
}

interface DailyScheduleUser {
  use_daily_schedule: boolean;
  hours_monday: number | null;
  hours_tuesday: number | null;
  hours_wednesday: number | null;
  hours_thursday: number | null;
  hours_friday: number | null;
  weekly_hours: number;
  work_days_per_week: number;
}

/** Returns the user's daily target hours for a given date string "YYYY-MM-DD". */
function getDailyTargetHours(user: DailyScheduleUser | null, dateStr: string): number {
  if (!user) return 8;
  if (user.use_daily_schedule) {
    const weekday = new Date(dateStr + 'T00:00:00').getDay(); // 0=Sun,1=Mon,...
    const map: Record<number, number | null | undefined> = {
      1: user.hours_monday,
      2: user.hours_tuesday,
      3: user.hours_wednesday,
      4: user.hours_thursday,
      5: user.hours_friday,
    };
    return map[weekday] ?? 0;
  }
  // No daily schedule: distribute weekly_hours over work_days
  const weekday = new Date(dateStr + 'T00:00:00').getDay();
  if (weekday === 0 || weekday === 6) return 0; // weekend
  return user.work_days_per_week > 0 ? user.weekly_hours / user.work_days_per_week : 8;
}

/** Adds `hours` to a "HH:mm" start time and returns the result as "HH:mm". */
function addHoursToTime(startTime: string, hours: number): string {
  const [h, m] = startTime.split(':').map(Number);
  const totalMins = h * 60 + m + Math.round(hours * 60);
  const endH = Math.floor(totalMins / 60) % 24;
  const endM = totalMins % 60;
  return `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;
}

function TimeBar({ startTime, endTime }: { startTime: string; endTime: string | null }) {
  if (!endTime) return null;
  const dayStart = 6 * 60;
  const dayEnd = 20 * 60;
  const range = dayEnd - dayStart;
  const [sh, sm] = startTime.split(':').map(Number);
  const [eh, em] = endTime.split(':').map(Number);
  const startMin = sh * 60 + sm;
  const endMin = eh * 60 + em;
  const left = Math.max(0, ((startMin - dayStart) / range) * 100);
  const width = Math.min(100 - left, Math.max(0, ((endMin - startMin) / range) * 100));
  return (
    <div className="my-3">
      <div className="relative h-2 bg-muted rounded-full">
        <div
          className="absolute h-full bg-gradient-to-r from-primary to-primary-dark rounded-full"
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-text-secondary tabular-nums">{startTime.substring(0, 5)}</span>
        <span className="text-[10px] text-text-secondary tabular-nums">{endTime.substring(0, 5)}</span>
      </div>
    </div>
  );
}

function WeekDots({
  entries,
  weekOffset,
  onWeekChange,
  onDotClick,
}: {
  entries: { date: string }[];
  weekOffset: number;
  onWeekChange: (dir: -1 | 1) => void;
  onDotClick: (date: string) => void;
}) {
  const now = new Date();
  const day = now.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(now);
  monday.setDate(monday.getDate() + mondayOffset + weekOffset * 7);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(d.getDate() + i);
    return format(d, 'yyyy-MM-dd');
  });
  const today = format(new Date(), 'yyyy-MM-dd');
  const entryDates = new Set(entries.map(e => e.date));
  return (
    <div className="flex items-center gap-1 px-1 py-3 md:hidden">
      <button onClick={() => onWeekChange(-1)} className="p-1 rounded-lg hover:bg-muted transition" aria-label="Vorherige Woche">
        <ChevronLeft size={16} className="text-text-secondary" />
      </button>
      <div className="flex-1 flex items-center justify-between">
        {days.map(dateStr => {
          const hasEntry = entryDates.has(dateStr);
          const isToday = dateStr === today;
          return (
            <button key={dateStr} onClick={() => onDotClick(dateStr)} className="flex flex-col items-center gap-1">
              <span className="text-[10px] text-text-secondary uppercase">
                {format(new Date(dateStr + 'T00:00:00'), 'EEEEEE', { locale: de })}
              </span>
              <span className="text-xs tabular-nums text-text-secondary">
                {new Date(dateStr + 'T00:00:00').getDate()}
              </span>
              <div className={`w-2 h-2 rounded-full transition-colors ${hasEntry ? 'bg-primary' : 'bg-muted'} ${isToday ? 'ring-2 ring-primary ring-offset-1' : ''}`} />
            </button>
          );
        })}
      </div>
      <button onClick={() => onWeekChange(1)} className="p-1 rounded-lg hover:bg-muted transition" aria-label="Nächste Woche">
        <ChevronRight size={16} className="text-text-secondary" />
      </button>
    </div>
  );
}

export default function TimeTracking() {
  const toast = useToast();
  const { user } = useAuthStore();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    start_time: '08:00',
    end_time: '17:00',
    break_minutes: 0,
    note: '',
    sunday_exception_reason: '',
  });
  const [errors, setErrors] = useState<{
    start_time?: string;
    end_time?: string;
    overlap?: string;
    break_time?: string;
  }>({});
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [weekOffset, setWeekOffset] = useState(0);

  // Change request modal
  const [crModalOpen, setCrModalOpen] = useState(false);
  const [crEntry, setCrEntry] = useState<TimeEntry | null>(null);
  const [crType, setCrType] = useState<'create' | 'update' | 'delete'>('update');

  // Tab navigation
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') ?? 'eintraege';

  const setTab = (tab: string) => {
    setSearchParams(tab === 'eintraege' ? {} : { tab });
  };

  useEffect(() => {
    fetchEntries();
  }, [currentMonth]);

  const fetchEntries = async () => {
    try {
      const response = await apiClient.get(`/time-entries?month=${currentMonth}`);
      setEntries(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Zeiteinträge');
    } finally {
      setLoading(false);
    }
  };

  const validateTimeEntry = (): boolean => {
    const newErrors: typeof errors = {};

    if (formData.start_time >= formData.end_time) {
      newErrors.end_time = 'Endzeit muss nach Startzeit liegen';
    }

    // Check for overlapping entries on the same day (skip open entries)
    const sameDay = entries.filter(
      (entry) => entry.date === formData.date && entry.id !== editingId && entry.end_time
    );

    const newStart = formData.start_time;
    const newEnd = formData.end_time;

    for (const entry of sameDay) {
      const existingStart = entry.start_time.substring(0, 5);
      const existingEnd = entry.end_time!.substring(0, 5);

      if (newStart < existingEnd && newEnd > existingStart) {
        newErrors.overlap = `Überschneidung mit bestehendem Eintrag (${existingStart} - ${existingEnd})`;
        break;
      }
    }

    // Client-side break validation
    const startParts = formData.start_time.split(':').map(Number);
    const endParts = formData.end_time.split(':').map(Number);
    const grossMinutes = (endParts[0] * 60 + endParts[1]) - (startParts[0] * 60 + startParts[1]);
    const netMinutes = grossMinutes - formData.break_minutes;

    if (netMinutes > 360 && formData.break_minutes < 30) {
      // Also count gaps between other entries on same day (skip open entries)
      const allBlocks = sameDay.filter(e => e.end_time).map(e => ({
        start: parseInt(e.start_time.substring(0, 2)) * 60 + parseInt(e.start_time.substring(3, 5)),
        end: parseInt(e.end_time!.substring(0, 2)) * 60 + parseInt(e.end_time!.substring(3, 5)),
        brk: e.break_minutes,
      }));
      allBlocks.push({
        start: startParts[0] * 60 + startParts[1],
        end: endParts[0] * 60 + endParts[1],
        brk: formData.break_minutes,
      });
      allBlocks.sort((a, b) => a.start - b.start);

      let totalDeclared = allBlocks.reduce((s, b) => s + b.brk, 0);
      let totalGap = 0;
      for (let i = 1; i < allBlocks.length; i++) {
        const gap = allBlocks[i].start - allBlocks[i - 1].end;
        if (gap > 0) totalGap += gap;
      }
      const totalGross = allBlocks.reduce((s, b) => s + (b.end - b.start), 0);
      const totalNet = totalGross - totalDeclared;
      const totalEffBreak = totalDeclared + totalGap;

      if (totalNet > 360 && totalEffBreak < 30) {
        newErrors.break_time = 'Bei >6h Arbeitszeit sind mind. 30 Min. Pause erforderlich (ArbZG §4)';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateTimeEntry()) {
      return;
    }

    // Smart break default: auto-set 30 min when creating entry >6h with no break
    let submitData = { ...formData };
    if (!editingId && submitData.break_minutes === 0) {
      const [sh, sm] = submitData.start_time.split(':').map(Number);
      const [eh, em] = submitData.end_time.split(':').map(Number);
      const grossMinutes = (eh * 60 + em) - (sh * 60 + sm);
      if (grossMinutes > 360) {
        submitData = { ...submitData, break_minutes: 30 };
      }
    }

    try {
      let response;
      if (editingId) {
        response = await apiClient.put(`/time-entries/${editingId}`, submitData);
        toast.success('Zeiteintrag erfolgreich aktualisiert');
      } else {
        response = await apiClient.post('/time-entries', submitData);
        toast.success('Zeiteintrag erfolgreich erstellt');
      }
      const saved: TimeEntry = response.data;
      if (saved.warnings?.includes('DAILY_HOURS_WARNING')) {
        toast.warning('Tagesarbeitszeit über 8 Stunden');
      }
      if (saved.warnings?.includes('WEEKLY_HOURS_WARNING')) {
        toast.warning('Wochenarbeitszeit über 48 Stunden');
      }
      if (saved.warnings?.includes('SUNDAY_WORK')) {
        toast.warning('Sonntagsarbeit eingetragen – bitte Ausnahmegrund angeben');
      }
      if (saved.warnings?.includes('HOLIDAY_WORK')) {
        toast.warning('Feiertagsarbeit eingetragen – bitte Ausnahmegrund angeben');
      }
      fetchEntries();
      resetForm();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    }
  };

  const handleEdit = (entry: TimeEntry) => {
    setEditingId(entry.id);
    setFormData({
      date: entry.date,
      start_time: entry.start_time.substring(0, 5),
      end_time: entry.end_time ? entry.end_time.substring(0, 5) : '17:00',
      break_minutes: entry.break_minutes,
      note: entry.note || '',
      sunday_exception_reason: entry.sunday_exception_reason || '',
    });
    setErrors({});
    setShowForm(true);
  };

  const handleDelete = (id: string) => {
    confirm({
      title: 'Eintrag löschen',
      message: 'Möchten Sie diesen Zeiteintrag wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/time-entries/${id}`);
          toast.success('Zeiteintrag erfolgreich gelöscht');
          fetchEntries();
        } catch (error) {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  const openChangeRequest = (entry: TimeEntry, type: 'update' | 'delete') => {
    setCrEntry(entry);
    setCrType(type);
    setCrModalOpen(true);
  };

  const openCreateChangeRequest = () => {
    setCrEntry(null);
    setCrType('create');
    setCrModalOpen(true);
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    const today = format(new Date(), 'yyyy-MM-dd');
    const targetHours = getDailyTargetHours(user, today);
    const defaultEnd = targetHours > 0 ? addHoursToTime('08:00', targetHours) : '17:00';
    setFormData({
      date: today,
      start_time: '08:00',
      end_time: defaultEnd,
      break_minutes: 0,
      note: '',
      sunday_exception_reason: '',
    });
    setErrors({});
  };

  const totalNet = entries.reduce((sum, entry) => sum + entry.net_hours, 0);
  const weekdayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const isAdmin = user?.role === 'admin';

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

      {crModalOpen && (
        <ChangeRequestForm
          entry={crEntry}
          requestType={crType}
          onClose={() => setCrModalOpen(false)}
          onSuccess={() => {
            setCrModalOpen(false);
            toast.success('Änderungsantrag erfolgreich erstellt');
          }}
        />
      )}

      <div className="flex items-center justify-between gap-2 mb-6 min-w-0">
        <h1 className="text-2xl sm:text-3xl font-bold text-text-primary truncate">Zeiterfassung</h1>
        {activeTab === 'eintraege' && (
          <div className="flex items-center gap-2 shrink-0">
            {!isAdmin && (
              <Button
                variant="secondary"
                size="md"
                icon={FileEdit}
                onClick={openCreateChangeRequest}
                title="Antrag für vergangenen Tag stellen"
                className="bg-amber-500 hover:bg-amber-600 text-white focus:ring-amber-400"
              >
                <span className="hidden sm:inline">Antrag</span>
              </Button>
            )}
            <Button
              variant={showForm ? 'ghost' : 'primary'}
              size="md"
              icon={showForm ? X : Plus}
              onClick={() => setShowForm(!showForm)}
            >
              <span className="hidden sm:inline">{showForm ? 'Abbrechen' : 'Neuer Eintrag'}</span>
            </Button>
          </div>
        )}
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-muted rounded-xl p-1 mb-6">
        {[
          { id: 'eintraege', label: 'Einträge' },
          { id: 'journal', label: 'Journal' },
          { id: 'requests', label: 'Anträge' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setTab(tab.id)}
            className={`flex-1 px-4 py-2 text-sm font-medium rounded-xl transition-all ${
              activeTab === tab.id
                ? 'bg-primary text-white shadow-soft'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'journal' && <Journal />}
      {activeTab === 'requests' && <ChangeRequests />}
      {activeTab === 'eintraege' && <>

      {/* Entry Form */}
      <style>{`
        @keyframes slideUpSheet {
          from { transform: translateY(100%); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
      {showForm && (
        <>
          {/* Mobile backdrop */}
          <div
            className="md:hidden fixed inset-0 bg-black/40 z-40"
            onClick={resetForm}
          />
          <div
            className="bg-white fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl shadow-2xl border-t border-gray-200 md:static md:rounded-xl md:shadow-sm md:border md:p-6 md:mb-6"
            style={{ animation: 'slideUpSheet 0.25s ease-out' }}
          >
            {/* Mobile handle bar */}
            <div className="md:hidden flex justify-center pt-3 pb-1">
              <div className="w-10 h-1 bg-gray-300 rounded-full" />
            </div>
            {/* Mobile header with close button */}
            <div className="md:hidden flex items-center justify-between px-4 pb-3 border-b border-gray-100">
              <h3 className="text-base font-semibold text-gray-900">
                {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
              </h3>
              <button onClick={resetForm} className="p-2 text-gray-500 hover:text-gray-700">
                <X size={20} />
              </button>
            </div>
            {/* Desktop title */}
            <h3 className="hidden md:block text-lg font-semibold mb-4">
              {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
            </h3>
          {errors.overlap && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg" role="alert">
              <p className="text-sm text-red-800 font-medium">{errors.overlap}</p>
            </div>
          )}
          {errors.break_time && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg" role="alert">
              <p className="text-sm text-amber-800 font-medium">{errors.break_time}</p>
            </div>
          )}

          <form id="time-entry-form" onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 p-4 md:p-0 pb-4 md:pb-0 overflow-y-auto max-h-[65vh] md:max-h-none md:overflow-visible">
            <div>
              <label htmlFor="tt-date" className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
              <input
                id="tt-date"
                type="date"
                value={formData.date}
                onChange={(e) => {
                  const newDate = e.target.value;
                  const targetHours = getDailyTargetHours(user, newDate);
                  const newEndTime = targetHours > 0
                    ? addHoursToTime(formData.start_time, targetHours)
                    : formData.end_time;
                  setFormData({ ...formData, date: newDate, end_time: newEndTime });
                  setErrors({});
                }}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label htmlFor="start-time" className="block text-sm font-medium text-gray-700 mb-1">Von</label>
              <input
                id="start-time"
                type="time"
                value={formData.start_time}
                onChange={(e) => {
                  setFormData({ ...formData, start_time: e.target.value });
                  setErrors({});
                }}
                required
                aria-invalid={errors.start_time ? 'true' : 'false'}
                aria-describedby={errors.start_time ? 'start-time-error' : undefined}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                  errors.start_time ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.start_time && (
                <p id="start-time-error" className="text-sm text-red-600 mt-1" role="alert">
                  {errors.start_time}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="end-time" className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
              <input
                id="end-time"
                type="time"
                value={formData.end_time}
                onChange={(e) => {
                  setFormData({ ...formData, end_time: e.target.value });
                  setErrors({});
                }}
                required
                aria-invalid={errors.end_time ? 'true' : 'false'}
                aria-describedby={errors.end_time ? 'end-time-error' : undefined}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                  errors.end_time ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.end_time && (
                <p id="end-time-error" className="text-sm text-red-600 mt-1" role="alert">
                  {errors.end_time}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="break-minutes" className="block text-sm font-medium text-gray-700 mb-1">Pause (Min.)</label>
              <input
                id="break-minutes"
                type="number"
                inputMode="numeric"
                min="0"
                max="480"
                value={formData.break_minutes}
                onChange={(e) => {
                  setFormData({ ...formData, break_minutes: parseInt(e.target.value) || 0 });
                  setErrors({});
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="hidden md:block">
              <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
              <Button type="submit" variant="primary" size="md" icon={Save} fullWidth>
                Speichern
              </Button>
            </div>
            <div className="md:col-span-2 lg:col-span-5">
              <label htmlFor="tt-note" className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                id="tt-note"
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-gray-400 mt-1">Bitte keine Gesundheitsangaben oder sensiblen Daten eintragen.</p>
            </div>
            {(new Date(formData.date + 'T12:00:00').getDay() === 0 ||
              (editingId && entries.find(e => e.id === editingId)?.is_sunday_or_holiday)) && (
              <div className="md:col-span-2 lg:col-span-5">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Ausnahmegrund <span className="text-gray-400 font-normal">– Sonn-/Feiertagsarbeit</span>
                </label>
                <input
                  type="text"
                  value={formData.sunday_exception_reason}
                  onChange={(e) => setFormData({ ...formData, sunday_exception_reason: e.target.value })}
                  placeholder="z. B. Notdienst, Patientenversorgung"
                  className="w-full px-3 py-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-amber-400 bg-amber-50"
                />
              </div>
            )}
          </form>
            {/* Sticky save button for mobile */}
            <div className="md:hidden px-4 py-3 border-t border-gray-100 bg-white">
              <Button
                type="button"
                variant="primary"
                size="md"
                fullWidth
                onClick={() => {
                  const formEl = document.querySelector<HTMLFormElement>('#time-entry-form');
                  formEl?.requestSubmit();
                }}
              >
                Speichern
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Month Selector */}
      <MonthSelector
        value={currentMonth}
        onChange={setCurrentMonth}
        className="mb-6"
      />

      {/* Entries Table/Cards */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* Desktop Table */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Von</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bis</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pause</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Netto</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center">
                    <LoadingSpinner text="Lade Einträge..." />
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <EmptyState title="Keine Einträge für diesen Monat" />
                  </td>
                </tr>
              ) : (
                entries.map((entry) => {
                  const entryDate = new Date(entry.date + 'T00:00:00');
                  const weekday = weekdayNames[entryDate.getDay()];
                  return (
                    <tr key={entry.id} className={`hover:bg-gray-50 ${!entry.is_editable ? 'bg-gray-50/50' : ''} ${entry.is_sunday_or_holiday ? 'bg-orange-50/40' : ''}`}>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        <div className="flex flex-col gap-1">
                          <span>{format(entryDate, 'dd.MM.yyyy')}</span>
                          <div className="flex gap-1 flex-wrap">
                            {entry.is_sunday_or_holiday && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800" title="Sonn- oder Feiertagsarbeit">
                                So/FT
                              </span>
                            )}
                            {entry.is_night_work && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800" title="Nachtarbeit (23–6 Uhr)">
                                Nacht
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{weekday}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.start_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {entry.end_time ? entry.end_time.substring(0, 5) : <span className="text-green-600 font-medium">offen</span>}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.break_minutes} min</td>
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {formatHoursHM(entry.net_hours)} h
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.note || '-'}</td>
                      <td className="px-6 py-4 text-right text-sm space-x-1">
                        {entry.is_editable ? (
                          <>
                            <button
                              onClick={() => handleEdit(entry)}
                              className="text-primary hover:text-primary-dark"
                              aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} bearbeiten`}
                            >
                              <Edit2 size={16} />
                            </button>
                            <button
                              onClick={() => handleDelete(entry.id)}
                              className="text-red-600 hover:text-red-800"
                              aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} löschen`}
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        ) : (
                          <>
                            <span title="Gesperrt"><Lock size={14} className="inline text-gray-400 mr-1" /></span>
                            <button
                              onClick={() => openChangeRequest(entry, 'update')}
                              className="text-amber-600 hover:text-amber-800"
                              aria-label={`Änderungsantrag für ${format(entryDate, 'dd.MM.yyyy')}`}
                              title="Änderungsantrag stellen"
                            >
                              <FileEdit size={16} />
                            </button>
                            <button
                              onClick={() => openChangeRequest(entry, 'delete')}
                              className="text-red-400 hover:text-red-600"
                              aria-label={`Löschantrag für ${format(entryDate, 'dd.MM.yyyy')}`}
                              title="Löschantrag stellen"
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
              {entries.length > 0 && (
                <tr className="bg-gray-50 font-semibold">
                  <td colSpan={5} className="px-6 py-4 text-sm text-gray-900">Summe</td>
                  <td className="px-6 py-4 text-sm text-gray-900">{formatHoursHM(totalNet)} h</td>
                  <td colSpan={2}></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards */}
        <div className="md:hidden">
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="skeleton h-32 rounded-2xl" />)}
            </div>
          ) : entries.length === 0 ? (
            <EmptyState title="Keine Einträge für diesen Monat" />
          ) : (
            <>
              <WeekDots
                entries={entries}
                weekOffset={weekOffset}
                onWeekChange={(dir) => setWeekOffset(prev => prev + dir)}
                onDotClick={(date) => {
                  document.getElementById(`entry-${date}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }}
              />
              <div className="space-y-3">
                {entries.map((entry, i) => {
                  const entryDate = new Date(entry.date + 'T00:00:00');
                  return (
                    <div
                      key={entry.id}
                      id={`entry-${entry.date}`}
                      className="bg-surface rounded-2xl shadow-soft p-4"
                      style={{ animation: `fadeSlideIn 200ms ease-out ${i * 50}ms both` }}
                    >
                      <div className="flex justify-between items-start">
                        <div className="font-semibold text-text-primary">
                          {format(entryDate, 'EEEE, d. MMMM', { locale: de })}
                          {!entry.is_editable && <Lock size={12} className="inline ml-1 text-text-secondary" />}
                        </div>
                        <span className="text-lg font-bold tabular-nums text-primary">{formatHoursHM(entry.net_hours)}h</span>
                      </div>
                      <TimeBar startTime={entry.start_time} endTime={entry.end_time} />
                      <div className="grid grid-cols-2 gap-2 text-sm mb-3">
                        <div className="flex justify-between">
                          <span className="text-text-secondary">Arbeitszeit</span>
                          <span className="font-medium tabular-nums">{formatHoursHM(entry.net_hours)}h</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary">Pause</span>
                          <span className="font-medium tabular-nums">{entry.break_minutes} min</span>
                        </div>
                      </div>
                      {entry.note && <p className="text-sm text-text-secondary mb-3">{entry.note}</p>}
                      {entry.is_editable ? (
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleEdit(entry)}
                            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-text-secondary hover:bg-muted transition"
                          >
                            <Edit2 size={14} /> Bearbeiten
                          </button>
                          <button
                            onClick={() => handleDelete(entry.id)}
                            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-danger hover:bg-red-50 transition"
                          >
                            <Trash2 size={14} /> Löschen
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            onClick={() => openChangeRequest(entry, 'update')}
                            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-amber-600 hover:bg-amber-50 transition"
                          >
                            <FileEdit size={14} /> Ändern
                          </button>
                          <button
                            onClick={() => openChangeRequest(entry, 'delete')}
                            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-danger hover:bg-red-50 transition"
                          >
                            <Trash2 size={14} /> Löschen
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {entries.length > 0 && (
                <div className="p-4 bg-muted rounded-2xl mt-3">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-text-primary">Summe</span>
                    <span className="text-lg font-bold tabular-nums text-primary">{formatHoursHM(totalNet)} h</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      </>}
    </div>
  );
}
