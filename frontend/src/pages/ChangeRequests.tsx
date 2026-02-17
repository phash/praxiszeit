import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../api/client';
import { Trash2, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from '../components/ConfirmDialog';

interface ChangeRequest {
  id: string;
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

export default function ChangeRequests() {
  const toast = useToast();
  const [requests, setRequests] = useState<ChangeRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  useEffect(() => {
    fetchRequests();
  }, [filter]);

  const fetchRequests = async () => {
    try {
      const params = filter ? `?status=${filter}` : '';
      const response = await apiClient.get(`/change-requests${params}`);
      setRequests(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Änderungsanträge');
    } finally {
      setLoading(false);
    }
  };

  const handleWithdraw = (id: string) => {
    confirm({
      title: 'Antrag zurückziehen',
      message: 'Möchten Sie diesen Änderungsantrag wirklich zurückziehen?',
      confirmLabel: 'Zurückziehen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/change-requests/${id}`);
          toast.success('Antrag zurückgezogen');
          fetchRequests();
        } catch (error) {
          toast.error('Fehler beim Zurückziehen');
        }
      },
    });
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

      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Änderungsanträge</h1>
      </div>

      {/* Filter */}
      <div className="flex space-x-2 mb-6">
        {[
          { value: '', label: 'Alle' },
          { value: 'pending', label: 'Offen' },
          { value: 'approved', label: 'Genehmigt' },
          { value: 'rejected', label: 'Abgelehnt' },
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

      {/* Requests List */}
      <div className="space-y-4">
        {loading ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-500">
            Lade Anträge...
          </div>
        ) : requests.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-500">
            <AlertCircle className="mx-auto mb-2 text-gray-400" size={32} />
            <p>Keine Änderungsanträge vorhanden</p>
          </div>
        ) : (
          requests.map((cr) => {
            const config = statusConfig[cr.status as keyof typeof statusConfig] || statusConfig.pending;
            const StatusIcon = config.icon;

            return (
              <div key={cr.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${config.color}`}>
                      <StatusIcon size={14} className="mr-1" />
                      {config.label}
                    </span>
                    <span className="text-sm font-medium text-gray-700">
                      {typeLabels[cr.request_type] || cr.request_type}
                    </span>
                    <span className="text-xs text-gray-500">
                      {format(new Date(cr.created_at), 'dd.MM.yyyy HH:mm')}
                    </span>
                  </div>
                  {cr.status === 'pending' && (
                    <button
                      onClick={() => handleWithdraw(cr.id)}
                      className="text-red-500 hover:text-red-700 p-1"
                      title="Zurückziehen"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>

                {/* Values comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                  {(cr.request_type === 'update' || cr.request_type === 'delete') && cr.original_date && (
                    <div className="bg-gray-50 rounded-lg p-3">
                      <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Aktuell</h4>
                      <div className="text-sm space-y-1">
                        <p>Datum: {cr.original_date}</p>
                        <p>Von: {cr.original_start_time?.substring(0, 5)} - Bis: {cr.original_end_time?.substring(0, 5)}</p>
                        <p>Pause: {cr.original_break_minutes} min</p>
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
                        <p>Datum: {cr.proposed_date}</p>
                        <p>Von: {cr.proposed_start_time?.substring(0, 5)} - Bis: {cr.proposed_end_time?.substring(0, 5)}</p>
                        <p>Pause: {cr.proposed_break_minutes} min</p>
                        {cr.proposed_note && <p>Notiz: {cr.proposed_note}</p>}
                      </div>
                    </div>
                  )}
                </div>

                {/* Reason */}
                <div className="text-sm">
                  <span className="font-medium text-gray-700">Begründung: </span>
                  <span className="text-gray-600">{cr.reason}</span>
                </div>

                {/* Rejection reason */}
                {cr.status === 'rejected' && cr.rejection_reason && (
                  <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm">
                    <span className="font-medium text-red-800">Ablehnungsgrund: </span>
                    <span className="text-red-700">{cr.rejection_reason}</span>
                  </div>
                )}

                {/* Review info */}
                {cr.reviewed_at && cr.reviewer_first_name && (
                  <div className="mt-2 text-xs text-gray-500">
                    Bearbeitet von {cr.reviewer_first_name} {cr.reviewer_last_name} am{' '}
                    {format(new Date(cr.reviewed_at), 'dd.MM.yyyy HH:mm')}
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
