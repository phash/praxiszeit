import { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { Save } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import { getErrorMessage } from '../../utils/errorMessage';

interface StatesResponse {
  states: string[];
  current_state: string;
}

interface SettingRow {
  key: string;
  value: string;
}

export default function Settings() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Holiday state
  const [states, setStates] = useState<string[]>([]);
  const [selectedState, setSelectedState] = useState('');
  const [originalState, setOriginalState] = useState('');

  // Vacation approval
  const [approvalRequired, setApprovalRequired] = useState(false);
  const [originalApproval, setOriginalApproval] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const [statesRes, settingsRes] = await Promise.all([
        apiClient.get<StatesResponse>('/holidays/states'),
        apiClient.get<SettingRow[]>('/admin/settings'),
      ]);

      // Holiday states
      setStates(statesRes.data.states);
      setSelectedState(statesRes.data.current_state);
      setOriginalState(statesRes.data.current_state);

      // Vacation approval
      const approvalSetting = settingsRes.data.find((s) => s.key === 'vacation_approval_required');
      const val = approvalSetting?.value?.toLowerCase() === 'true';
      setApprovalRequired(val);
      setOriginalApproval(val);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const saveHolidayState = async () => {
    setSaving(true);
    try {
      await apiClient.put('/admin/settings/holiday_state', { value: selectedState });
      setOriginalState(selectedState);
      toast.success('Bundesland aktualisiert. Feiertage wurden neu berechnet.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const saveApproval = async () => {
    setSaving(true);
    try {
      await apiClient.put('/admin/settings/vacation_approval_required', {
        value: String(approvalRequired),
      });
      setOriginalApproval(approvalRequired);
      toast.success('Urlaubsgenehmigung-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Einstellungen</h1>

      {/* Feiertage */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Feiertage</h2>
        <p className="text-sm text-gray-500 mb-4">
          Wählen Sie das Bundesland aus, dessen gesetzliche Feiertage verwendet werden sollen.
          Bei Änderung werden alle Feiertage automatisch neu berechnet.
        </p>
        <div className="flex items-end gap-4">
          <div className="flex-1 max-w-sm">
            <label htmlFor="holiday-state" className="block text-sm font-medium text-gray-700 mb-1">
              Bundesland
            </label>
            <select
              id="holiday-state"
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            >
              {states.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={saveHolidayState}
            disabled={saving || selectedState === originalState}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Urlaubsgenehmigung */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Urlaubsgenehmigung</h2>
        <p className="text-sm text-gray-500 mb-4">
          Wenn aktiviert, müssen Urlaubsanträge von einem Admin genehmigt werden, bevor sie wirksam
          werden.
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="approval-toggle" className="text-sm font-medium text-gray-700">
            Genehmigung erforderlich
          </label>
          <button
            id="approval-toggle"
            role="switch"
            aria-checked={approvalRequired}
            onClick={() => setApprovalRequired(!approvalRequired)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              approvalRequired ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                approvalRequired ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveApproval}
            disabled={saving || approvalRequired === originalApproval}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}
