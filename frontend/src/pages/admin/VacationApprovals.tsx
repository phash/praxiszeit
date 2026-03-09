import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../../api/client';
import { Clock, CheckCircle, XCircle, AlertCircle, Check, X } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import { getErrorMessage } from '../../utils/errorMessage';

interface VacationRequest {
  id: string;
  user_id: string;
  user_first_name?: string;
  user_last_name?: string;
  date: string;
  end_date?: string;
  hours: number;
  note?: string;
  status: string;
  rejection_reason?: string;
  reviewer_first_name?: string;
  reviewer_last_name?: string;
  reviewed_at?: string;
  created_at: string;
}

const statusConfig = {
  pending: { label: 'Offen', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  approved: { label: 'Genehmigt', color: 'bg-green-100 text-green-800', icon: CheckCircle },
  rejected: { label: 'Abgelehnt', color: 'bg-red-100 text-red-800', icon: XCircle },
  withdrawn: { label: 'Zurückgezogen', color: 'bg-gray-100 text-gray-600', icon: XCircle },
};

export default function VacationApprovals() {
  const toast = useToast();
  const [requests, setRequests] = useState<VacationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [approvalRequired, setApprovalRequired] = useState<boolean | null>(null);
  const [settingLoading, setSettingLoading] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [filter]);

  const fetchSettings = async () => {
    try {
      const res = await apiClient.get('/admin/settings');
      const setting = res.data.find((s: any) => s.key === 'vacation_approval_required');
      setApprovalRequired(setting?.value === 'true');
    } catch {
      // ignore
    }
  };

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const params = filter ? `?status=${filter}` : '';
      const res = await apiClient.get(`/admin/vacation-requests${params}`);
      setRequests(res.data);
    } catch {
      toast.error('Fehler beim Laden der Urlaubsanträge');
    } finally {
      setLoading(false);
    }
  };

  const toggleApprovalRequired = async () => {
    setSettingLoading(true);
    try {
      const newValue = !approvalRequired;
      await apiClient.put('/admin/settings/vacation_approval_required', { value: String(newValue) });
      setApprovalRequired(newValue);
      toast.success(newValue ? 'Genehmigungspflicht aktiviert' : 'Genehmigungspflicht deaktiviert');
    } catch {
      toast.error('Fehler beim Aktualisieren der Einstellung');
    } finally {
      setSettingLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await apiClient.post(`/admin/vacation-requests/${id}/review`, { action: 'approve' });
      toast.success('Urlaubsantrag genehmigt');
      fetchRequests();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Genehmigen'));
    }
  };

  const handleReject = async (id: string) => {
    try {
      await apiClient.post(`/admin/vacation-requests/${id}/review`, {
        action: 'reject',
        rejection_reason: rejectionReason || undefined,
      });
      toast.success('Urlaubsantrag abgelehnt');
      setRejectingId(null);
      setRejectionReason('');
      fetchRequests();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Ablehnen'));
    }
  };

  const pendingCount = requests.filter((r) => r.status === 'pending').length;

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Urlaubsanträge</h1>
          {filter === 'pending' && pendingCount > 0 && (
            <p className="text-sm text-amber-600 mt-1">{pendingCount} offene Anträge</p>
          )}
        </div>
      </div>

      {/* Setting Toggle */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6 flex items-center justify-between">
        <div>
          <p className="font-medium text-gray-900">Urlaubsanträge genehmigungspflichtig</p>
          <p className="text-sm text-gray-500 mt-0.5">
            {approvalRequired
              ? 'Mitarbeiter müssen Urlaub beantragen – Admin-Freigabe erforderlich.'
              : 'Mitarbeiter buchen Urlaub direkt ohne Admin-Freigabe.'}
          </p>
        </div>
        <button
          onClick={toggleApprovalRequired}
          disabled={settingLoading || approvalRequired === null}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
            approvalRequired ? 'bg-primary' : 'bg-gray-200'
          } disabled:opacity-50`}
          role="switch"
          aria-checked={approvalRequired ?? false}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              approvalRequired ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex space-x-2 mb-6">
        {[
          { value: 'pending', label: 'Offen' },
          { value: 'approved', label: 'Genehmigt' },
          { value: 'rejected', label: 'Abgelehnt' },
          { value: '', label: 'Alle' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              filter === f.value
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Request Cards */}
      <div className="space-y-4">
        {loading ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 flex justify-center">
            <LoadingSpinner text="Lade Anträge..." />
          </div>
        ) : requests.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-500">
            <AlertCircle className="mx-auto mb-2 text-gray-400" size={32} />
            <p>Keine Anträge vorhanden</p>
          </div>
        ) : (
          requests.map((vr) => {
            const config =
              statusConfig[vr.status as keyof typeof statusConfig] || statusConfig.pending;
            const StatusIcon = config.icon;

            return (
              <div key={vr.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center space-x-3 mb-1">
                      <span className="font-semibold text-gray-900">
                        {vr.user_last_name}, {vr.user_first_name}
                      </span>
                      <span
                        className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${config.color}`}
                      >
                        <StatusIcon size={14} className="mr-1" />
                        {config.label}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      Erstellt: {format(new Date(vr.created_at), 'dd.MM.yyyy HH:mm')}
                    </span>
                  </div>
                </div>

                {/* Details */}
                <div className="bg-blue-50 rounded-lg p-3 mb-4">
                  <div className="text-sm space-y-1">
                    <p>
                      Zeitraum:{' '}
                      <span className="font-medium">
                        {format(new Date(vr.date + 'T00:00:00'), 'dd.MM.yyyy')}
                        {vr.end_date &&
                          ` – ${format(new Date(vr.end_date + 'T00:00:00'), 'dd.MM.yyyy')}`}
                      </span>
                    </p>
                    <p>
                      Stunden pro Tag: <span className="font-medium">{vr.hours} h</span>
                    </p>
                    {vr.note && (
                      <p>
                        Notiz: <span className="font-medium">{vr.note}</span>
                      </p>
                    )}
                  </div>
                </div>

                {/* Rejection reason */}
                {vr.status === 'rejected' && vr.rejection_reason && (
                  <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm">
                    <span className="font-medium text-red-800">Ablehnungsgrund: </span>
                    <span className="text-red-700">{vr.rejection_reason}</span>
                  </div>
                )}

                {/* Review info */}
                {vr.reviewed_at && vr.reviewer_first_name && (
                  <div className="text-xs text-gray-500 mb-4">
                    Bearbeitet von {vr.reviewer_first_name} {vr.reviewer_last_name} am{' '}
                    {format(new Date(vr.reviewed_at), 'dd.MM.yyyy HH:mm')}
                  </div>
                )}

                {/* Admin Actions */}
                {vr.status === 'pending' && (
                  <div className="border-t border-gray-200 pt-4">
                    {rejectingId === vr.id ? (
                      <div className="space-y-3">
                        <textarea
                          value={rejectionReason}
                          onChange={(e) => setRejectionReason(e.target.value)}
                          placeholder="Ablehnungsgrund (optional)"
                          rows={2}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500"
                        />
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleReject(vr.id)}
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm rounded-lg transition"
                          >
                            Ablehnen
                          </button>
                          <button
                            onClick={() => {
                              setRejectingId(null);
                              setRejectionReason('');
                            }}
                            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm rounded-lg transition"
                          >
                            Abbrechen
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex space-x-3">
                        <button
                          onClick={() => handleApprove(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                        >
                          <Check size={16} />
                          <span>Genehmigen</span>
                        </button>
                        <button
                          onClick={() => setRejectingId(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 text-sm rounded-lg transition"
                        >
                          <X size={16} />
                          <span>Ablehnen</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
