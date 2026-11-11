import { useEffect, useState, useCallback, useRef } from 'react';
import apiClient from '../../api/client';
import { downloadBlob } from '../../utils/downloadBlob';
import { Database, Download, Trash2, Play, Save, Clock, HardDrive, AlertTriangle } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import { getBlobErrorMessage, getErrorMessage } from '../../utils/errorMessage';
import PasswordConfirmDialog from '../../components/PasswordConfirmDialog';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import { formatFixedDe } from '../../utils/formatters';

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
  /** Nur der gespeicherte Override ('' = Standard); `location` ist der wirksame Pfad. */
  location_override?: string;
}

/** Ältester noch unauffälliger Stand der letzten Sicherung (Stunden). */
const STALE_BACKUP_HOURS = 36;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${formatFixedDe(n / 1024, 1)} KB`;
  return `${formatFixedDe(n / (1024 * 1024), 1)} MB`;
}

export default function Backups() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [downloadingFile, setDownloadingFile] = useState<string | null>(null);
  // Audit 2026-11-07 (S1-02): Download nur nach Passwort-Rückfrage.
  const [downloadPrompt, setDownloadPrompt] = useState<string | null>(null);
  const [backups, setBackups] = useState<BackupFile[]>([]);
  const [config, setConfig] = useState<BackupConfig>({
    enabled: false, hour: 2, retention_days: 30, location: '', location_override: '',
  });
  // Zahlenfelder als Text halten (ops-12): ein geleertes Feld wird nicht still zu 0.
  const [hourInput, setHourInput] = useState('2');
  const [retentionInput, setRetentionInput] = useState('30');
  const [locationInput, setLocationInput] = useState('');
  const [configError, setConfigError] = useState<string | null>(null);
  // Spinner nur beim ersten Laden (ops-12), danach aktualisiert die Seite still.
  const firstLoad = useRef(true);

  const applyConfig = (c: BackupConfig) => {
    setConfig(c);
    setHourInput(String(c.hour));
    setRetentionInput(String(c.retention_days));
    setLocationInput(c.location_override ?? '');
  };

  const load = useCallback(async () => {
    if (firstLoad.current) setLoading(true);
    try {
      const res = await apiClient.get('/admin/backups');
      applyConfig(res.data.config);
      setBackups(res.data.backups);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Fehler beim Laden der Backups'));
    } finally {
      firstLoad.current = false;
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
    const hour = Number(hourInput);
    const retention = Number(retentionInput);
    if (hourInput.trim() === '' || !Number.isInteger(hour) || hour < 0 || hour > 23) {
      setConfigError('Bitte für die Uhrzeit eine ganze Zahl von 0 bis 23 eingeben.');
      return;
    }
    if (retentionInput.trim() === '' || !Number.isInteger(retention) || retention < 1 || retention > 3650) {
      setConfigError('Bitte für die Aufbewahrung eine ganze Zahl von 1 bis 3650 Tagen eingeben.');
      return;
    }
    setConfigError(null);
    setSavingConfig(true);
    try {
      const loc = locationInput.trim();
      const res = await apiClient.put('/admin/backups/config', {
        enabled: config.enabled,
        hour,
        retention_days: retention,
        // ops-02: nur senden, wenn geändert; '' setzt auf den Standard zurück.
        ...(loc !== (config.location_override ?? '') ? { location: loc } : {}),
      });
      applyConfig(res.data);
      toast.success('Backup-Einstellungen gespeichert');
      await load();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    } finally {
      setSavingConfig(false);
    }
  };

  const handleDownload = async (filename: string, password: string): Promise<boolean> => {
    setDownloadingFile(filename);
    try {
      const res = await apiClient.post(
        `/admin/backups/${filename}/download`, { password }, { responseType: 'blob' },
      );
      downloadBlob(res.data, filename, 'application/gzip');
      setDownloadPrompt(null);
      return true;
    } catch (error) {
      toast.error(await getBlobErrorMessage(error, 'Download fehlgeschlagen'));
      return false;
    } finally {
      setDownloadingFile(null);
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

  const newest = backups.reduce<number | null>((acc, b) => {
    const t = new Date(b.created_at).getTime();
    return acc === null || t > acc ? t : acc;
  }, null);
  const staleHours = newest === null ? null : (Date.now() - newest) / 3_600_000;
  const stale = staleHours !== null && staleHours > STALE_BACKUP_HOURS;

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-6">
      <div className="flex items-center gap-2">
        <Database className="w-6 h-6 text-blue-600" />
        <h1 className="text-2xl font-bold">Datensicherung</h1>
      </div>

      {stale && (
        <div role="alert" data-testid="backup-stale-warning"
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            Die letzte Sicherung ist älter als {STALE_BACKUP_HOURS} Stunden
            ({new Date(newest as number).toLocaleString('de-DE')}). Bitte prüfen Sie den Zeitplan
            oder sichern Sie jetzt.
          </span>
        </div>
      )}

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
        <p className="text-xs text-gray-500" data-testid="backup-schedule-hint">
          Gilt für die <strong>Docker</strong>-Installation. Eine <strong>native</strong> Installation sichert
          über den Zeitplan des Betriebssystems (Linux täglich 02:00, Windows und macOS täglich 03:00,
          Aufbewahrung 31 Tage laut <span className="font-mono">praxiszeit.conf</span>) im Standardordner
          <span className="font-mono"> data/backups</span>; Uhrzeit, Aufbewahrung und Speicherort unten
          wirken dort nicht (der Speicherort gilt nur für „Jetzt sichern“).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="backup-hour" className="block text-sm font-medium mb-1">Uhrzeit (Stunde, 0–23)</label>
            <input
              id="backup-hour" type="number" min={0} max={23} value={hourInput}
              onChange={(e) => setHourInput(e.target.value)}
              className="w-full border rounded px-3 py-2"
            />
            <p className="text-xs text-gray-500 mt-1">Nur Docker: lokale Zeit (Europe/Berlin), Sicherung läuft um HH:30.</p>
          </div>
          <div>
            <label htmlFor="backup-retention" className="block text-sm font-medium mb-1">Aufbewahrung (Tage)</label>
            <input
              id="backup-retention" type="number" min={1} max={3650} value={retentionInput}
              onChange={(e) => setRetentionInput(e.target.value)}
              className="w-full border rounded px-3 py-2"
            />
            <p className="text-xs text-gray-500 mt-1">Ältere Sicherungen werden automatisch gelöscht.</p>
          </div>
        </div>
        <div>
          <label htmlFor="backup-location" className="block text-sm font-medium mb-1 flex items-center gap-1">
            <HardDrive className="w-4 h-4" /> Speicherort (optional)
          </label>
          <input
            id="backup-location" type="text" value={locationInput}
            placeholder={`Standard verwenden (${config.location})`}
            onChange={(e) => setLocationInput(e.target.value)}
            className="w-full border rounded px-3 py-2 font-mono text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">
            Leer = Standardverzeichnis. Bitte einen absoluten Pfad angeben, der für den Dienst
            beschreibbar ist. Aktuell genutzt: <span className="font-mono">{config.location}</span>
          </p>
        </div>
        {configError && (
          <p role="alert" data-testid="backup-config-error" className="text-sm text-red-600">{configError}</p>
        )}
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
                      onClick={() => setDownloadPrompt(b.filename)}
                      disabled={downloadingFile === b.filename}
                      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Herunterladen"
                      aria-label={`${b.filename} herunterladen`}
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(b.filename)}
                      className="inline-flex items-center gap-1 text-red-600 hover:text-red-800"
                      title="Löschen"
                      aria-label={`${b.filename} löschen`}
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

      <PasswordConfirmDialog
        isOpen={downloadPrompt !== null}
        title="Sicherung herunterladen"
        message={`Die Datei „${downloadPrompt ?? ''}“ enthält die gesamte Datenbank mit allen Gesundheitsdaten. Bitte bestätigen Sie den Download mit Ihrem Passwort. Der Download wird unter „Konto-Vorgänge“ protokolliert.`}
        confirmLabel="Herunterladen"
        onSubmit={(pw) => (downloadPrompt ? handleDownload(downloadPrompt, pw) : Promise.resolve(false))}
        onCancel={() => setDownloadPrompt(null)}
      />
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
