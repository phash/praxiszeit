import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../../api/client';
import { Clock, CheckCircle, XCircle, AlertCircle, Check, X } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';

interface ChangeRequest {
  id: string;
  user_id: string;
  user_first_name?: string;
  user_last_name?: string;
  request_type: string;
  status: string;
  proposed_date?: string;
  proposed_start_time?: string;
  proposed_end_time?: string;
  proposed_break_minutes?: number;
  proposed_note?: string;
  original_date?: string;
  original_start_time?: string;
  original_end_time?: string;
  original_break_minutes?: number;
  original_note?: string;
  reason: string;
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
};

const typeLabels: Record<string, string> = {
  create: 'Neuer Eintrag',
  update: 'Änderung',
  delete: 'Löschung',
};

export default function AdminChangeRequests() {
  const toast = useToast();
  const [requests, setRequests] = useState<ChangeRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');

  useEffect(() => {
    fetchRequests();
  }, [filter]);

  const fetchRequests = async () => {
    try {
      const params = filter ? `?status=${filter}` : '';
      const response = await apiClient.get(`/admin/change-requests${params}`);
      setRequests(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Änderungsanträge');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await apiClient.post(`/admin/change-requests/${id}/review`, {
        action: 'approve',
      });
      toast.success('Antrag genehmigt');
      fetchRequests();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Genehmigen');
    }
  };

  const handleReject = async (id: string) => {
    try {
      await apiClient.post(`/admin/change-requests/${id}/review`, {
        action: 'reject',
        rejection_reason: rejectionReason || undefined,
      });
      toast.success('Antrag abgelehnt');
      setRejectingId(null);
      setRejectionReason('');
      fetchRequests();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Ablehnen');
    }
  };

  const pendingCount = requests.filter(r => r.status === 'pending').length;

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Änderungsanträge</h1>
          {filter === 'pending' && pendingCount > 0 && (
            <p className="text-sm text-amber-600 mt-1">{pendingCount} offene Anträge</p>
          )}
        </div>
      </div>

      {/* Filter */}
      <div className="flex space-x-2 mb-6">
        {[
          { value: 'pending', label: 'Offen' },
          { value: 'approved', label: 'Genehmigt' },
          { value: 'rejected', label: 'Abgelehnt' },
          { value: '', label: 'Alle' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setLoading(true); }}
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

      {/* Requests */}
      <div className="space-y-4">
        {loading ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-500">
            Lade Anträge...
          </div>
        ) : requests.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-500">
            <AlertCircle className="mx-auto mb-2 text-gray-400" size={32} />
            <p>Keine Anträge vorhanden</p>
          </div>
        ) : (
          requests.map((cr) => {
            const config = statusConfig[cr.status as keyof typeof statusConfig] || statusConfig.pending;
            const StatusIcon = config.icon;

            return (
              <div key={cr.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center space-x-3 mb-1">
                      <span className="font-semibold text-gray-900">
                        {cr.user_last_name}, {cr.user_first_name}
                      </span>
                      <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${config.color}`}>
                        <StatusIcon size={14} className="mr-1" />
                        {config.label}
                      </span>
                      <span className="text-sm text-gray-600">{typeLabels[cr.request_type]}</span>
                    </div>
                    <span className="text-xs text-gray-500">
                      Erstellt: {format(new Date(cr.created_at), 'dd.MM.yyyy HH:mm')}
                    </span>
                  </div>
                </div>

                {/* Values comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                  {(cr.request_type === 'update' || cr.request_type === 'delete') && cr.original_date && (
                    <div className="bg-gray-50 rounded-lg p-3">
                      <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Aktuell</h4>
                      <div className="text-sm space-y-1">
                        <p>Datum: <span className="font-medium">{cr.original_date}</span></p>
                        <p>Zeit: <span className="font-medium">{cr.original_start_time?.substring(0, 5)} - {cr.original_end_time?.substring(0, 5)}</span></p>
                        <p>Pause: <span className="font-medium">{cr.original_break_minutes} min</span></p>
                        {cr.original_note && <p>Notiz: {cr.original_note}</p>}
                      </div>
                    </div>
                  )}
                  {cr.request_type !== 'delete' && cr.proposed_date && (
                    <div className="bg-amber-50 rounded-lg p-3">
                      <h4 className="text-xs font-semibold text-amber-700 uppercase mb-2">
                        {cr.request_type === 'create' ? 'Neuer Eintrag' : 'Gewünscht'}
                      </h4>
                      <div className="text-sm space-y-1">
                        <p>Datum: <span className="font-medium">{cr.proposed_date}</span></p>
                        <p>Zeit: <span className="font-medium">{cr.proposed_start_time?.substring(0, 5)} - {cr.proposed_end_time?.substring(0, 5)}</span></p>
                        <p>Pause: <span className="font-medium">{cr.proposed_break_minutes} min</span></p>
                        {cr.proposed_note && <p>Notiz: {cr.proposed_note}</p>}
                      </div>
                    </div>
                  )}
                </div>

                {/* Reason */}
                <div className="text-sm mb-4">
                  <span className="font-medium text-gray-700">Begründung: </span>
                  <span className="text-gray-600">{cr.reason}</span>
                </div>

                {/* Rejection reason */}
                {cr.status === 'rejected' && cr.rejection_reason && (
                  <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm">
                    <span className="font-medium text-red-800">Ablehnungsgrund: </span>
                    <span className="text-red-700">{cr.rejection_reason}</span>
                  </div>
                )}

                {/* Review info */}
                {cr.reviewed_at && cr.reviewer_first_name && (
                  <div className="text-xs text-gray-500 mb-4">
                    Bearbeitet von {cr.reviewer_first_name} {cr.reviewer_last_name} am{' '}
                    {format(new Date(cr.reviewed_at), 'dd.MM.yyyy HH:mm')}
                  </div>
                )}

                {/* Admin Actions */}
                {cr.status === 'pending' && (
                  <div className="border-t border-gray-200 pt-4">
                    {rejectingId === cr.id ? (
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
                            onClick={() => handleReject(cr.id)}
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm rounded-lg transition"
                          >
                            Ablehnen
                          </button>
                          <button
                            onClick={() => { setRejectingId(null); setRejectionReason(''); }}
                            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm rounded-lg transition"
                          >
                            Abbrechen
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex space-x-3">
                        <button
                          onClick={() => handleApprove(cr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                        >
                          <Check size={16} />
                          <span>Genehmigen</span>
                        </button>
                        <button
                          onClick={() => setRejectingId(cr.id)}
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
