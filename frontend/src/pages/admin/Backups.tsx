import { useEffect, useState, useCallback } from 'react';
import apiClient from '../../api/client';
import { downloadBlob } from '../../utils/downloadBlob';
import { Database, Download, Trash2, Play, Save, Clock, HardDrive } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import { getErrorMessage } from '../../utils/errorMessage';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';

interface BackupFile {
  filename: string;
  size_bytes: number;
  created_at: string;
}

interface BackupConfig {
  enabled: boolean;
  hour: number;
  retention_days: number;
  location: string;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Backups() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [backups, setBackups] = useState<BackupFile[]>([]);
  const [config, setConfig] = useState<BackupConfig>({
    enabled: false, hour: 2, retention_days: 30, location: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/admin/backups');
      setConfig(res.data.config);
      setBackups(res.data.backups);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Fehler beim Laden der Backups'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const res = await apiClient.post('/admin/backups');
      toast.success(`Backup erstellt: ${res.data.filename}`);
      await load();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Backup fehlgeschlagen'));
    } finally {
      setCreating(false);
    }
  };

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    try {
      const res = await apiClient.put('/admin/backups/config', {
        enabled: config.enabled,
        hour: config.hour,
        retention_days: config.retention_days,
        location: config.location || null,
      });
      setConfig(res.data);
      toast.success('Backup-Einstellungen gespeichert');
      await load();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    } finally {
      setSavingConfig(false);
    }
  };

  const handleDownload = async (filename: string) => {
    try {
      const res = await apiClient.get(`/admin/backups/${filename}/download`, { responseType: 'blob' });
      downloadBlob(res.data, filename, 'application/gzip');
    } catch (error) {
      toast.error(getErrorMessage(error, 'Download fehlgeschlagen'));
    }
  };

  const handleDelete = (filename: string) => {
    confirm({
      title: 'Backup löschen?',
      message: `"${filename}" wird unwiderruflich gelöscht.`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/backups/${filename}`);
          toast.success('Backup gelöscht');
          await load();
        } catch (error) {
          toast.error(getErrorMessage(error, 'Löschen fehlgeschlagen'));
        }
      },
    });
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-6">
      <div className="flex items-center gap-2">
        <Database className="w-6 h-6 text-blue-600" />
        <h1 className="text-2xl font-bold">Datensicherung</h1>
      </div>

      {/* Manueller Trigger */}
      <div className="bg-white rounded-lg shadow p-5">
        <h2 className="text-lg font-semibold mb-2">Sofort sichern</h2>
        <p className="text-sm text-gray-600 mb-4">
          Erstellt umgehend eine vollständige, komprimierte Datenbank-Sicherung
          (Plain-SQL, mit <code>--clean --if-exists</code> wiederherstellbar).
        </p>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          <Play className="w-4 h-4" />
          {creating ? 'Sichere…' : 'Jetzt sichern'}
        </button>
      </div>

      {/* Zeitplan / Konfiguration */}
      <div className="bg-white rounded-lg shadow p-5 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Clock className="w-5 h-5 text-gray-500" /> Geplante Sicherung
        </h2>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
          />
          <span>Tägliche automatische Sicherung aktivieren</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Uhrzeit (Stunde, 0–23)</label>
            <input
              type="number" min={0} max={23} value={config.hour}
              onChange={(e) => setConfig({ ...config, hour: Number(e.target.value) })}
              className="w-full border rounded px-3 py-2"
            />
            <p className="text-xs text-gray-500 mt-1">Lokale Zeit (Europe/Berlin), Sicherung läuft um HH:30.</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Aufbewahrung (Tage)</label>
            <input
              type="number" min={1} max={3650} value={config.retention_days}
              onChange={(e) => setConfig({ ...config, retention_days: Number(e.target.value) })}
              className="w-full border rounded px-3 py-2"
            />
            <p className="text-xs text-gray-500 mt-1">Ältere Sicherungen werden automatisch gelöscht.</p>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 flex items-center gap-1">
            <HardDrive className="w-4 h-4" /> Speicherort (optional)
          </label>
          <input
            type="text" value={config.location}
            placeholder="Standard verwenden"
            onChange={(e) => setConfig({ ...config, location: e.target.value })}
            className="w-full border rounded px-3 py-2 font-mono text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">
            Leer = Standardverzeichnis. Pfad muss für den Dienst beschreibbar sein.
          </p>
        </div>
        <button
          onClick={handleSaveConfig}
          disabled={savingConfig}
          className="inline-flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {savingConfig ? 'Speichere…' : 'Einstellungen speichern'}
        </button>
      </div>

      {/* Liste */}
      <div className="bg-white rounded-lg shadow p-5">
        <h2 className="text-lg font-semibold mb-3">Vorhandene Sicherungen ({backups.length})</h2>
        {backups.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Sicherungen vorhanden.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2">Datei</th>
                <th className="py-2">Größe</th>
                <th className="py-2">Erstellt</th>
                <th className="py-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.filename} className="border-b last:border-0">
                  <td className="py-2 font-mono text-xs">{b.filename}</td>
                  <td className="py-2">{formatBytes(b.size_bytes)}</td>
                  <td className="py-2">{new Date(b.created_at).toLocaleString('de-DE')}</td>
                  <td className="py-2 text-right space-x-2 whitespace-nowrap">
                    <button
                      onClick={() => handleDownload(b.filename)}
                      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800"
                      title="Herunterladen"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(b.filename)}
                      className="inline-flex items-center gap-1 text-red-600 hover:text-red-800"
                      title="Löschen"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
}
