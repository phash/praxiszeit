import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import { Plus, X, Trash2, Clock, CheckCircle, XCircle, ChevronLeft, ChevronRight, Pencil } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from '../components/ConfirmDialog';
import { AbsenceType, ABSENCE_TYPE_LABELS, ABSENCE_TYPE_COLORS } from '../constants/absenceTypes';
import AbsenceBadge from '../components/AbsenceBadge';
import { useTypeColorsStore } from '../stores/typeColorsStore';

// Label helper that tolerates the DSGVO-masked "absent" pseudo-type.
const absenceTypeLabel = (t: string): string =>
  t === 'absent' ? 'Abwesend' : (ABSENCE_TYPE_LABELS[t as AbsenceType] ?? t);
import Badge from '../components/Badge';
import { getErrorMessage } from '../utils/errorMessage';
import { parseHours } from '../utils/formatters';
import MonthSelector from '../components/MonthSelector';
import EmptyState from '../components/EmptyState';
import { useAuthStore } from '../stores/authStore';
import VacationRequestEditModal from '../components/VacationRequestEditModal';

interface VacationRequest {
  id: string;
  user_id?: string;
  date: string;
  end_date?: string;
  hours: number;
  days?: number;
  absence_type?: string;
  note?: string;
  status: string;
  rejection_reason?: string;
  created_at: string;
  last_modified_by?: string;
  last_modified_at?: string;
  last_modifier_first_name?: string;
  last_modifier_last_name?: string;
}

const vrStatusConfig = {
  pending: { label: 'Offen', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  approved: { label: 'Genehmigt', color: 'bg-green-100 text-green-800', icon: CheckCircle },
  rejected: { label: 'Abgelehnt', color: 'bg-red-100 text-red-800', icon: XCircle },
  withdrawn: { label: 'Zurückgezogen', color: 'bg-gray-100 text-gray-600', icon: XCircle },
};

interface CalendarEntry {
  date: string;
  user_first_name: string;
  user_last_name: string;
  user_color: string;
  // May be a masked value ("absent") for non-admins viewing others' sick days.
  type: string;
  hours: number;
}

interface Absence {
  id: string;
  date: string;
  end_date?: string;
  type: 'vacation' | 'sick' | 'training' | 'overtime' | 'other';
  hours: number;
  note?: string;
}

interface PublicHoliday {
  date: string;
  name: string;
}

interface AuthUser {
  use_daily_schedule?: boolean;
  hours_monday?: number | null;
  hours_tuesday?: number | null;
  hours_wednesday?: number | null;
  hours_thursday?: number | null;
  hours_friday?: number | null;
}

function getHoursForDate(user: AuthUser | null | undefined, dateStr: string): number {
  if (!user || !user.use_daily_schedule) return 8;
  const weekday = new Date(dateStr + 'T00:00:00').getDay(); // 0=Sun, 1=Mon...
  const dayMap: Record<number, number | null | undefined> = {
    1: user.hours_monday,
    2: user.hours_tuesday,
    3: user.hours_wednesday,
    4: user.hours_thursday,
    5: user.hours_friday,
  };
  return dayMap[weekday] ?? 0;
}

export default function AbsenceCalendarPage() {
  const toast = useToast();
  const { user: currentUser } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'calendar' | 'requests'>('calendar');
  const [vacationApprovalRequired, setVacationApprovalRequired] = useState(false);
  const [myVacationRequests, setMyVacationRequests] = useState<VacationRequest[]>([]);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [viewMode, setViewMode] = useState<'month' | 'year'>('month');
  const [calendarEntries, setCalendarEntries] = useState<CalendarEntry[]>([]);
  const [myAbsences, setMyAbsences] = useState<Absence[]>([]);
  const [holidays, setHolidays] = useState<PublicHoliday[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [isDateRange, setIsDateRange] = useState(false);
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    end_date: '',
    type: 'vacation' as 'vacation' | 'sick' | 'training' | 'overtime' | 'other',
    hours: getHoursForDate(currentUser, format(new Date(), 'yyyy-MM-dd')) || 8,
    note: '',
  });
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [editingRequest, setEditingRequest] = useState<VacationRequest | null>(null);
  // Guards against double-submit (fast double-click would create duplicate absences/requests).
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiClient.get('/settings').then((res) => {
      setVacationApprovalRequired(res.data.vacation_approval_required === true);
    }).catch(() => {});
    fetchMyVacationRequests();
  }, []);

  // Pre-fill hours from daily-target endpoint when type is "overtime"
  useEffect(() => {
    if (formData.type === 'overtime' && formData.date) {
      apiClient.get(`/absences/daily-target?date=${formData.date}`)
        .then((res) => {
          if (res.data.hours > 0) {
            setFormData(prev => ({ ...prev, hours: res.data.hours }));
          }
        })
        .catch(() => {});
    }
  }, [formData.type, formData.date]);

  useEffect(() => {
    fetchData();
  }, [currentMonth, currentYear, viewMode]);

  const fetchMyVacationRequests = async () => {
    try {
      const res = await apiClient.get('/vacation-requests');
      setMyVacationRequests(res.data);
    } catch {
      // ignore – endpoint may not exist if feature is off
    }
  };

  const fetchData = async () => {
    try {
      const year = viewMode === 'month' ? parseInt(currentMonth.split('-')[0]) : currentYear;
      
      if (viewMode === 'month') {
        const [calendarRes, absencesRes, holidaysRes] = await Promise.all([
          apiClient.get(`/absences/calendar?month=${currentMonth}`),
          apiClient.get(`/absences?year=${year}`),
          apiClient.get(`/holidays?year=${year}`),
        ]);
        setCalendarEntries(calendarRes.data);
        setMyAbsences(absencesRes.data);
        setHolidays(holidaysRes.data);
      } else {
        // Fetch all months for the year
        const promises = Array.from({ length: 12 }, (_, i) => {
          const month = `${currentYear}-${String(i + 1).padStart(2, '0')}`;
          return apiClient.get(`/absences/calendar?month=${month}`);
        });
        const results = await Promise.all(promises);
        const allEntries = results.flatMap(r => r.data);
        setCalendarEntries(allEntries);

        // Fetch user absences and holidays for the year
        const [absencesRes, holidaysRes] = await Promise.all([
          apiClient.get(`/absences?year=${currentYear}`),
          apiClient.get(`/holidays?year=${currentYear}`),
        ]);
        setMyAbsences(absencesRes.data);
        setHolidays(holidaysRes.data);
      }
    } catch (error) {
      toast.error('Fehler beim Laden des Kalenders');
    }
  };

  const doSubmit = async (refundVacation: boolean) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      // If approval required and not sick leave: create an absence request instead
      if (formData.type !== 'sick' && vacationApprovalRequired) {
        await apiClient.post('/vacation-requests', {
          date: formData.date,
          end_date: isDateRange && formData.end_date ? formData.end_date : null,
          hours: formData.hours,
          absence_type: formData.type,
          note: formData.note || null,
        });
        toast.success('Antrag gestellt – wartet auf Genehmigung');
        fetchMyVacationRequests();
        setShowForm(false);
        setIsDateRange(false);
        setFormData({ date: format(new Date(), 'yyyy-MM-dd'), end_date: '', type: 'vacation', hours: getHoursForDate(currentUser, format(new Date(), 'yyyy-MM-dd')) || 8, note: '' });
        setActiveTab('requests');
        return;
      }

      const submitData = {
        date: formData.date,
        end_date: isDateRange && formData.end_date ? formData.end_date : null,
        type: formData.type,
        hours: formData.hours,
        note: formData.note || null,
        refund_vacation: refundVacation,
      };
      await apiClient.post('/absences', submitData);
      const msg = refundVacation
        ? 'Krankmeldung eingetragen und Urlaubstage zurückerstattet'
        : 'Abwesenheit erfolgreich eingetragen';
      toast.success(msg);
      fetchData();
      setShowForm(false);
      setIsDateRange(false);
      setFormData({ date: format(new Date(), 'yyyy-MM-dd'), end_date: '', type: 'vacation', hours: getHoursForDate(currentUser, format(new Date(), 'yyyy-MM-dd')) || 8, note: '' });
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // If sick leave: check for overlapping vacation entries
    if (formData.type === 'sick') {
      const startDate = formData.date;
      const endDate = isDateRange && formData.end_date ? formData.end_date : formData.date;
      const overlappingVacation = myAbsences.filter(a => {
        const absDate = a.date;
        return a.type === 'vacation' && absDate >= startDate && absDate <= endDate;
      });
      if (overlappingVacation.length > 0) {
        confirm({
          title: 'Krankmeldung im Urlaub',
          message: `Sie sind an ${overlappingVacation.length} Tag(en) im Urlaub. Sollen diese Urlaubstage zurückerstattet werden?`,
          confirmLabel: 'Urlaub zurückerstatten',
          variant: 'info',
          onConfirm: () => doSubmit(true),
        });
        return;
      }
    }
    await doSubmit(false);
  };

  const handleDelete = (id: string) => {
    confirm({
      title: 'Abwesenheit löschen',
      message: 'Möchten Sie diese Abwesenheit wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/absences/${id}`);
          toast.success('Abwesenheit erfolgreich gelöscht');
          fetchData();
        } catch (error) {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  // Use shared constants
  const typeLabels = ABSENCE_TYPE_LABELS;
  const typeColors = ABSENCE_TYPE_COLORS;
  const absColors = useTypeColorsStore((s) => s.colors);

  // Generate calendar days
  const [year, month] = currentMonth.split('-').map(Number);
  const monthStart = startOfMonth(new Date(year, month - 1));
  const monthEnd = endOfMonth(new Date(year, month - 1));
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

  // Monday-first calendar (consistent with year view)
  const weekdayNames = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const firstDayOffset = (monthStart.getDay() + 6) % 7; // 0=Mo, 1=Di, ..., 6=So

  return (
    <div>
      {editingRequest && (
        <VacationRequestEditModal
          request={editingRequest}
          mode="self"
          onClose={() => setEditingRequest(null)}
          onSaved={() => {
            setEditingRequest(null);
            fetchMyVacationRequests();
          }}
        />
      )}
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div className="flex items-center justify-between gap-2 mb-6 min-w-0">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 truncate">Abwesenheiten</h1>
        {activeTab === 'calendar' && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="shrink-0 bg-primary hover:bg-primary-dark text-white px-3 sm:px-4 py-2 rounded-lg flex items-center gap-2 transition"
          >
            {showForm ? <X size={20} /> : <Plus size={20} />}
            <span className="hidden sm:inline">{showForm ? 'Abbrechen' : 'Abwesenheit eintragen'}</span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6">
        <button
          onClick={() => setActiveTab('calendar')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'calendar'
              ? 'border-primary text-primary'
              : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
          }`}
        >
          Kalender
        </button>
        {vacationApprovalRequired && (
          <button
            onClick={() => { setActiveTab('requests'); fetchMyVacationRequests(); }}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center space-x-2 ${
              activeTab === 'requests'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
            }`}
          >
            <span>Meine Anträge</span>
            {myVacationRequests.filter((r) => r.status === 'pending').length > 0 && (
              <span className="bg-amber-500 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
                {myVacationRequests.filter((r) => r.status === 'pending').length}
              </span>
            )}
          </button>
        )}
      </div>

      {/* ── My Vacation Requests Tab ── */}
      {activeTab === 'requests' && (
        <div className="space-y-4">
          {myVacationRequests.length === 0 ? (
            <div className="bg-white rounded-xl shadow-xs border border-gray-200">
              <EmptyState icon={Clock} title="Keine Anträge vorhanden" />
            </div>
          ) : (
            myVacationRequests.map((vr) => {
              const cfg = vrStatusConfig[vr.status as keyof typeof vrStatusConfig] || vrStatusConfig.pending;
              const StatusIcon = cfg.icon;
              return (
                <div key={vr.id} className="bg-white rounded-xl shadow-xs border border-gray-200 p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center space-x-3 mb-1">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${cfg.color}`}>
                          <StatusIcon size={14} className="mr-1" />
                          {cfg.label}
                        </span>
                        {vr.absence_type && (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${ABSENCE_TYPE_COLORS[vr.absence_type as AbsenceType] || 'bg-gray-100 text-gray-800'}`}>
                            {ABSENCE_TYPE_LABELS[vr.absence_type as AbsenceType] || vr.absence_type}
                          </span>
                        )}
                        <span className="text-xs text-gray-500">
                          Gestellt: {format(new Date(vr.created_at), 'dd.MM.yyyy HH:mm')}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-gray-900 mt-1">
                        {format(new Date(vr.date + 'T00:00:00'), 'dd.MM.yyyy')}
                        {vr.end_date && ` – ${format(new Date(vr.end_date + 'T00:00:00'), 'dd.MM.yyyy')}`}
                        {' · '}{vr.days != null ? `${vr.days} Tag${vr.days !== 1 ? 'e' : ''}` : `${vr.hours} h/Tag`}
                      </p>
                      {vr.note && <p className="text-sm text-gray-500 mt-0.5">{vr.note}</p>}
                      {vr.last_modified_by && vr.user_id && vr.last_modified_by !== vr.user_id && vr.last_modified_at && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-2 inline-block">
                          Bearbeitet von {vr.last_modifier_first_name ?? 'Admin'}
                          {vr.last_modifier_last_name ? ` ${vr.last_modifier_last_name}` : ''}
                          {' am '}
                          {format(new Date(vr.last_modified_at), 'dd.MM.yyyy HH:mm')}
                        </p>
                      )}
                    </div>
                    {(() => {
                      const todayStr = format(new Date(), 'yyyy-MM-dd');
                      const isPending = vr.status === 'pending';
                      const isApprovedFuture = vr.status === 'approved' && vr.date > todayStr;
                      if (!isPending && !isApprovedFuture) return null;
                      const dialog = isApprovedFuture
                        ? {
                            title: 'Urlaub stornieren',
                            message: 'Genehmigten Urlaub wirklich stornieren? Die zugehörigen Abwesenheitstage werden gelöscht.',
                            confirmLabel: 'Stornieren',
                            successMsg: 'Urlaub storniert',
                            buttonTitle: 'Urlaub stornieren',
                          }
                        : {
                            title: 'Antrag zurückziehen',
                            message: 'Antrag wirklich zurückziehen?',
                            confirmLabel: 'Zurückziehen',
                            successMsg: 'Antrag zurückgezogen',
                            buttonTitle: 'Antrag zurückziehen',
                          };
                      return (
                        <div className="flex items-center space-x-1">
                          {isPending && (
                            <button
                              onClick={() => setEditingRequest(vr)}
                              className="p-3 text-blue-600 hover:bg-blue-50 rounded-lg transition"
                              title="Antrag bearbeiten"
                            >
                              <Pencil size={16} />
                            </button>
                          )}
                          <button
                            onClick={() =>
                              confirm({
                                title: dialog.title,
                                message: dialog.message,
                                confirmLabel: dialog.confirmLabel,
                                variant: 'danger',
                                onConfirm: async () => {
                                  try {
                                    await apiClient.delete(`/vacation-requests/${vr.id}`);
                                    toast.success(dialog.successMsg);
                                    fetchMyVacationRequests();
                                  } catch (error) {
                                    toast.error(getErrorMessage(error, 'Fehler beim Zurückziehen'));
                                  }
                                },
                              })
                            }
                            className="p-3 text-red-600 hover:bg-red-50 rounded-lg transition"
                            title={dialog.buttonTitle}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      );
                    })()}
                  </div>
                  {vr.status === 'rejected' && vr.rejection_reason && (
                    <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm">
                      <span className="font-medium text-red-800">Ablehnungsgrund: </span>
                      <span className="text-red-700">{vr.rejection_reason}</span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ── Calendar Tab ── */}
      {activeTab === 'calendar' && <>

      {/* Absence Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Abwesenheit eintragen</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Zeitraum-Checkbox */}
            <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
              <input
                type="checkbox"
                id="isDateRange"
                checked={isDateRange}
                onChange={(e) => {
                  setIsDateRange(e.target.checked);
                  if (!e.target.checked) {
                    setFormData({ ...formData, end_date: '' });
                  }
                }}
                className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
              />
              <label htmlFor="isDateRange" className="text-sm font-medium text-gray-700 cursor-pointer">
                Zeitraum (mehrere Tage)
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {isDateRange ? 'Von' : 'Datum'}
                </label>
                <input
                  type="date"
                  value={formData.date}
                  onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>

              {isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={formData.end_date}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                    required={isDateRange}
                    min={formData.date}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value as any })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="vacation">Urlaub</option>
                  <option value="sick">Krank</option>
                  <option value="training">Fortbildung (außer Haus)</option>
                  <option value="overtime">Überstundenausgleich</option>
                  <option value="other">Sonstiges</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Stunden {isDateRange && '(pro Tag)'}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  step="0.5"
                  value={formData.hours}
                  onChange={(e) => setFormData({ ...formData, hours: parseHours(e.target.value) })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formData.type === 'vacation'
                    ? 'Stunden = Regelarbeitszeit pro Tag (für Urlaubsberechnung)'
                    : formData.type === 'overtime'
                    ? 'Vorausgefüllt mit Ihren Sollstunden des Tages'
                    : currentUser?.use_daily_schedule
                    ? 'Stunden werden aus Ihrem Tagesplan übernommen'
                    : 'Stunden, die als Abwesenheit angerechnet werden'}
                </p>
              </div>
              {!isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Speichern
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-gray-400 mt-1">Bitte keine Gesundheitsangaben oder sensiblen Daten eintragen.</p>
            </div>

            {isDateRange && (
              <div>
                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Speichern
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* View Mode Toggle and Selector */}
      <div className="mb-4 flex items-center space-x-4">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
          <button
            onClick={() => setViewMode('month')}
            className={`px-3 py-1.5 font-medium transition-colors ${
              viewMode === 'month' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            Monat
          </button>
          <button
            onClick={() => setViewMode('year')}
            className={`px-3 py-1.5 font-medium transition-colors border-l border-gray-200 ${
              viewMode === 'year' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            Jahr
          </button>
        </div>
        {viewMode === 'month' ? (
          <MonthSelector
            value={currentMonth}
            onChange={setCurrentMonth}
          />
        ) : (
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setCurrentYear(y => y - 1)}
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition"
              aria-label="Vorheriges Jahr"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="font-medium text-gray-800 w-16 text-center">{currentYear}</span>
            <button
              onClick={() => setCurrentYear(y => y + 1)}
              disabled={currentYear >= new Date().getFullYear() + 1}
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition disabled:opacity-40"
              aria-label="Nächstes Jahr"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>

      {/* Calendar */}
      {viewMode === 'month' ? (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 mb-6">
          {/* Desktop Calendar Grid */}
          <div className="hidden sm:block p-6">
            <div className="grid grid-cols-7 gap-2">
              {/* Weekday headers */}
              {weekdayNames.map((day) => (
                <div key={day} className="text-center font-semibold text-gray-600 py-2">
                  {day}
                </div>
              ))}

              {/* Offset cells for first day of month */}
              {Array.from({ length: firstDayOffset }).map((_, i) => (
                <div key={`offset-${i}`} />
              ))}

              {/* Calendar days */}
              {days.map((day) => {
                const dateStr = format(day, 'yyyy-MM-dd');
                const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
                const dayHoliday = holidays.find((h) => h.date === dateStr);
                const isWeekend = day.getDay() === 0 || day.getDay() === 6;

                return (
                  <div
                    key={dateStr}
                    onClick={() => {
                      setFormData(prev => ({ ...prev, date: dateStr, hours: getHoursForDate(currentUser, dateStr) || prev.hours }));
                      setShowForm(true);
                      setIsDateRange(false);
                    }}
                    className={`min-h-24 border rounded-lg p-2 cursor-pointer transition hover:border-primary hover:shadow-xs ${
                      isWeekend || dayHoliday ? 'bg-gray-50' : 'bg-white'
                    }`}
                    title="Klicken um Abwesenheit einzutragen"
                  >
                    <div className="text-sm font-medium text-gray-600 mb-1">
                      {format(day, 'd')}
                    </div>
                    <div className="space-y-1">
                      {/* Holiday Badge */}
                      {dayHoliday && (
                        <div className="text-xs px-2 py-1 rounded-sm bg-gray-200 text-gray-700 border border-gray-300 font-medium">
                          {dayHoliday.name}
                        </div>
                      )}
                      {/* Absence Entries — per-employee badge (ring = MA-Farbe, Mitte = Typ) */}
                      {dayEntries.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {dayEntries.map((entry, idx) => (
                            <AbsenceBadge
                              key={idx}
                              type={entry.type}
                              userColor={entry.user_color}
                              initials={`${entry.user_first_name?.[0] ?? ''}${entry.user_last_name?.[0] ?? ''}`.toUpperCase()}
                              title={`${entry.user_first_name} ${entry.user_last_name} – ${absenceTypeLabel(entry.type)}`}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Mobile List View */}
          <div className="sm:hidden">
            {days
              .filter((day) => day.getDay() !== 0 && day.getDay() !== 6) // show all weekdays
              .map((day) => {
                const dateStr = format(day, 'yyyy-MM-dd');
                const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
                const dayHoliday = holidays.find((h) => h.date === dateStr);
                const hasContent = dayEntries.length > 0 || !!dayHoliday;

                return (
                  <div key={dateStr} className="border-b border-gray-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="font-semibold text-gray-900">
                          {format(day, 'EEEE, dd. MMMM', { locale: de })}
                        </p>
                      </div>
                      {!dayHoliday && (
                        <button
                          onClick={() => {
                            setFormData(prev => ({ ...prev, date: dateStr, hours: getHoursForDate(currentUser, dateStr) || prev.hours }));
                            setShowForm(true);
                            setIsDateRange(false);
                          }}
                          className="p-2 text-gray-400 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
                          aria-label={`Abwesenheit für ${format(day, 'dd. MMMM', { locale: de })} eintragen`}
                        >
                          <Plus size={18} />
                        </button>
                      )}
                    </div>
                    <div className="space-y-2">
                      {/* Holiday */}
                      {dayHoliday && (
                        <div className="px-3 py-2 rounded-lg bg-gray-100 border border-gray-200">
                          <p className="text-sm font-medium text-gray-700">
                            🎉 {dayHoliday.name}
                          </p>
                        </div>
                      )}
                      {/* Absence Entries */}
                      {dayEntries.map((entry, idx) => (
                        <div
                          key={idx}
                          className="px-3 py-2 rounded-lg border border-gray-200 flex items-center gap-2"
                        >
                          <AbsenceBadge
                            type={entry.type}
                            userColor={entry.user_color}
                            initials={`${entry.user_first_name?.[0] ?? ''}${entry.user_last_name?.[0] ?? ''}`.toUpperCase()}
                            title={`${entry.user_first_name} ${entry.user_last_name}`}
                          />
                          <div>
                            <p className="text-sm font-medium">
                              {entry.user_first_name} {entry.user_last_name}
                            </p>
                            <p className="text-xs text-gray-600 mt-0.5">
                              {absenceTypeLabel(entry.type)}
                            </p>
                          </div>
                        </div>
                      ))}
                      {/* Placeholder for days without content */}
                      {!hasContent && (
                        <p className="text-sm text-gray-400 italic">Keine Abwesenheit</p>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[0,1,2,3,4,5,6,7,8,9,10,11].map(monthIndex => {
              const monthDate = new Date(currentYear, monthIndex, 1);
              const monthStart = startOfMonth(monthDate);
              const monthEnd = endOfMonth(monthDate);
              const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

              // Get absences for this month
              const monthAbsences = calendarEntries.filter(entry => {
                const entryDate = parseISO(entry.date);
                return entryDate >= monthStart && entryDate <= monthEnd;
              });

              // Get first day offset for calendar grid
              const firstDayOfWeek = monthStart.getDay();
              const paddingDays = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1; // Monday = 0

              return (
                <div key={monthIndex} className="bg-white rounded-lg border border-gray-200 p-3">
                  <h3 className="text-sm font-semibold text-gray-900 mb-2 text-center">
                    {format(monthDate, 'MMMM', { locale: de })}
                  </h3>
                  <div className="grid grid-cols-7 gap-1 text-xs">
                    {['M', 'D', 'M', 'D', 'F', 'S', 'S'].map((day, i) => (
                      <div key={i} className="text-center font-medium text-gray-400 py-1">
                        {day}
                      </div>
                    ))}

                    {/* Empty cells for offset */}
                    {Array.from({ length: paddingDays }).map((_, i) => (
                      <div key={`empty-${i}`} />
                    ))}

                    {days.map(day => {
                      const dateStr = format(day, 'yyyy-MM-dd');
                      const dayAbsences = monthAbsences.filter(e => e.date === dateStr);
                      const dayHoliday = holidays.find((h) => h.date === dateStr);
                      const isWeekend = day.getDay() === 0 || day.getDay() === 6;

                      return (
                        <div
                          key={dateStr}
                          onClick={() => {
                            setFormData(prev => ({ ...prev, date: dateStr }));
                            setShowForm(true);
                            setIsDateRange(false);
                          }}
                          className={`aspect-square flex flex-col items-center justify-center rounded text-xs cursor-pointer hover:ring-1 hover:ring-primary ${
                            isWeekend || dayHoliday ? 'bg-gray-100' : 'bg-white'
                          }`}
                          title={dayHoliday ? dayHoliday.name : 'Klicken um Abwesenheit einzutragen'}
                        >
                          <div className={`font-medium ${dayHoliday ? 'text-gray-500' : 'text-gray-700'}`}>
                            {format(day, 'd')}
                          </div>
                          {dayAbsences.length > 0 && (
                            <div className="flex space-x-0.5 mt-0.5">
                              {dayAbsences.slice(0, 3).map((_, idx) => (
                                <div key={idx} className="w-1 h-1 rounded-full bg-blue-500"></div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6" key="legend">
        <h3 className="font-semibold mb-3">Legende</h3>
        <p className="text-xs text-gray-500 mb-3">
          Im Kalender: <strong>Ring</strong> = Mitarbeiterfarbe, <strong>Mitte</strong> = Art der Abwesenheit.
        </p>
        <div className="flex flex-wrap gap-4">
          {Object.entries(typeLabels).map(([key, label]) => (
            <div key={key} className="flex items-center space-x-2">
              <div
                className="w-4 h-4 rounded-full border border-gray-300"
                style={{ backgroundColor: (absColors as Record<string, string>)[key] ?? '#6B7280' }}
              ></div>
              <span className="text-sm">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* My Absences */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold">Meine Abwesenheiten ({viewMode === 'month' ? currentMonth.split('-')[0] : currentYear})</h3>
        </div>

        {/* Desktop Table */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stunden</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {myAbsences.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <EmptyState title="Keine Abwesenheiten" />
                  </td>
                </tr>
              ) : (
                myAbsences.map((absence) => (
                  <tr key={absence.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {absence.end_date ? (
                        <>
                          {format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')} - {format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}
                        </>
                      ) : (
                        format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded-sm text-xs ${typeColors[absence.type]}`}>
                        {typeLabels[absence.type]}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{absence.hours} h</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{absence.note || '-'}</td>
                    <td className="px-6 py-4 text-right text-sm">
                      <button
                        onClick={() => handleDelete(absence.id)}
                        className="text-red-600 hover:text-red-800"
                      >
                        Löschen
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards */}
        <div className="md:hidden">
          {myAbsences.length === 0 ? (
            <EmptyState title="Keine Abwesenheiten" />
          ) : (
            <div className="divide-y divide-gray-200">
              {myAbsences.map((absence) => (
                <div key={absence.id} className="p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <p className="font-medium text-gray-900">
                        {absence.end_date ? (
                          <>
                            {format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')} - {format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}
                          </>
                        ) : (
                          format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')
                        )}
                      </p>
                      <div className="mt-2">
                        <Badge variant={absence.type} size="sm">
                          {typeLabels[absence.type]}
                        </Badge>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(absence.id)}
                      className="p-3 text-red-600 hover:bg-red-50 rounded-lg transition"
                      aria-label="Abwesenheit löschen"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Stunden:</span>
                      <span className="font-medium">{absence.hours} h</span>
                    </div>
                    {absence.note && (
                      <div>
                        <span className="text-gray-600 block mb-1">Notiz:</span>
                        <p className="text-gray-900">{absence.note}</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      </>}
    </div>
  );
}
