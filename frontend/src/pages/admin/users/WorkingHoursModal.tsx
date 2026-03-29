import { useState, useEffect } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Plus, X, Trash2 } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useConfirm } from '../../../hooks/useConfirm';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { getErrorMessage } from '../../../utils/errorMessage';

interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  note?: string;
  created_at: string;
}

interface WorkingHoursModalProps {
  userId: string;
  userName: string;
  currentWeeklyHours: number;
  onClose: () => void;
  onChanged: () => void;
}

export default function WorkingHoursModal({ userId, userName, currentWeeklyHours, onClose, onChanged }: WorkingHoursModalProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  const [formData, setFormData] = useState({
    effective_from: new Date().toISOString().split('T')[0],
    weekly_hours: currentWeeklyHours,
    note: '',
  });

  useEffect(() => {
    fetchHoursChanges();
  }, [userId]);

  const fetchHoursChanges = async () => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      setHoursChanges(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Stundenhistorie');
    }
  };

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiClient.post(`/admin/users/${userId}/working-hours-changes`, formData);
      await fetchHoursChanges();
      onChanged();
      setFormData({
        effective_from: new Date().toISOString().split('T')[0],
        weekly_hours: currentWeeklyHours,
        note: '',
      });
      toast.success('Stundenänderung erfolgreich hinzugefügt');
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Hinzufügen'));
    }
  };

  const handleDeleteHoursChange = (changeId: string) => {
    confirm({
      title: 'Stundenänderung löschen',
      message: 'Möchten Sie diese Stundenänderung wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/users/${userId}/working-hours-changes/${changeId}`);
          await fetchHoursChanges();
          onChanged();
          toast.success('Stundenänderung erfolgreich gelöscht');
        } catch (error) {
          toast.error('Fehler beim Löschen der Stundenänderung');
        }
      },
    });
  };

  return (
    <>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div
        className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
        onClick={onClose}
      >
        <FocusTrap
          focusTrapOptions={{
            allowOutsideClick: true,
            escapeDeactivates: true,
            onDeactivate: onClose,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="hours-modal-title"
            className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 id="hours-modal-title" className="text-2xl font-bold text-gray-900">Stundenverlauf</h2>
                <p className="text-sm text-gray-600 mt-1">
                  {userName} • Aktuell: {currentWeeklyHours} Std/Woche
                </p>
              </div>
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700"
                aria-label={`Stundenverlauf für ${userName} schließen`}
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-6">
              {/* Add New Change Form */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Stundenänderung</h3>
                <form onSubmit={handleAddHoursChange} className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Gültig ab
                    </label>
                    <input
                      type="date"
                      value={formData.effective_from}
                      onChange={(e) => setFormData({ ...formData, effective_from: e.target.value })}
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Wochenstunden
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      value={formData.weekly_hours}
                      onChange={(e) => setFormData({ ...formData, weekly_hours: parseFloat(e.target.value) })}
                      required
                      min="0"
                      max="60"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Notiz (optional)
                    </label>
                    <input
                      type="text"
                      value={formData.note}
                      onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                      placeholder="z.B. Teilzeitänderung"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <button
                      type="submit"
                      className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
                    >
                      <Plus size={18} />
                      <span>Hinzufügen</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* History List */}
              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => (
                      <div
                        key={change.id}
                        className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                      >
                        <div>
                          <p className="font-medium text-gray-900">
                            Ab {new Date(change.effective_from).toLocaleDateString('de-DE', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                            })}: {change.weekly_hours} Std/Woche
                          </p>
                          {change.note && (
                            <p className="text-sm text-gray-600 mt-1">{change.note}</p>
                          )}
                          <p className="text-xs text-gray-500 mt-1">
                            Erstellt: {new Date(change.created_at).toLocaleDateString('de-DE', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                        </div>
                        <button
                          onClick={() => handleDeleteHoursChange(change.id)}
                          className="text-red-600 hover:text-red-800"
                          title="Löschen"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Hinweis:</strong> Die Berechnungen von Soll-Stunden berücksichtigen automatisch die
                  historischen Werte. Wenn z.B. jemand ab 15.03. von 20h auf 30h wechselt, werden für den
                  März die ersten 14 Tage mit 20h und ab dem 15. mit 30h berechnet.
                </p>
              </div>
            </div>
          </div>
        </FocusTrap>
      </div>
    </>
  );
}
