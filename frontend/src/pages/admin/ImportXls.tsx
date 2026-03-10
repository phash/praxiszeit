import { useState, useRef } from 'react';
import { Upload, CheckCircle, AlertTriangle, XCircle, RotateCcw } from 'lucide-react';
import apiClient from '../../api/client';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';

// ── Typen ────────────────────────────────────────────────────────────────────

interface ImportedEntry {
  date: string;           // "2026-01-12"
  start_time: string;     // "07:15:00"
  end_time: string;       // "12:45:00"
  break_minutes: number;
  note: string | null;
  has_conflict: boolean;
  arbzg_warnings: string[];
}

interface PreviewResponse {
  entries: ImportedEntry[];
  total: number;
  conflicts: number;
  arbzg_warnings: number;
}

interface ImportResult {
  imported: number;
  skipped: number;
  overwritten: number;
  warnings: string[];
}

interface User {
  id: string;
  first_name: string;
  last_name: string;
  username: string;
  is_active: boolean;
}

type WizardStep = 'upload' | 'preview' | 'result';

// ── Konstanten ────────────────────────────────────────────────────────────────

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB

// ── Hilfsfunktionen ──────────────────────────────────────────────────────────

function formatTime(t: string): string {
  return t.slice(0, 5); // "07:15:00" → "07:15"
}

function formatDate(d: string): string {
  const [y, m, day] = d.split('-');
  return `${day}.${m}.${y}`;
}

function calcNetHours(start: string, end: string, breakMin: number): string {
  const [sh, sm] = start.split(':').map(Number);
  const [eh, em] = end.split(':').map(Number);
  const gross = (eh * 60 + em) - (sh * 60 + sm);
  const net = gross - breakMin;
  const h = Math.floor(net / 60);
  const m = net % 60;
  return `${h}:${String(m).padStart(2, '0')}`;
}

// ── StepIndicator ─────────────────────────────────────────────────────────────

const WIZARD_STEPS = [
  { key: 'upload' as WizardStep, label: 'Hochladen' },
  { key: 'preview' as WizardStep, label: 'Vorschau' },
  { key: 'result' as WizardStep, label: 'Ergebnis' },
];

interface StepIndicatorProps {
  step: WizardStep;
}

function StepIndicator({ step }: StepIndicatorProps) {
  return (
    <div className="flex items-center mb-8">
      {WIZARD_STEPS.map((s, idx) => {
        const isActive = step === s.key;
        const isDone =
          (s.key === 'upload' && (step === 'preview' || step === 'result')) ||
          (s.key === 'preview' && step === 'result');
        return (
          <div key={s.key} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                  ${isActive ? 'bg-primary text-white' : isDone ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}`}
              >
                {isDone ? '✓' : idx + 1}
              </div>
              <span className={`text-sm font-medium ${isActive ? 'text-primary' : 'text-gray-500'}`}>
                {s.label}
              </span>
            </div>
            {idx < WIZARD_STEPS.length - 1 && (
              <div className="h-0.5 w-10 bg-gray-200 mx-3" />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Komponente ───────────────────────────────────────────────────────────────

export default function ImportXls() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  const [step, setStep] = useState<WizardStep>('upload');
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [warningsExpanded, setWarningsExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Benutzer laden beim ersten Fokus auf das Select
  const loadUsers = async () => {
    if (usersLoaded) return;
    try {
      const res = await apiClient.get('/admin/users');
      setUsers((res.data as User[]).filter((u) => u.is_active));
      setUsersLoaded(true);
    } catch {
      toast.error('Benutzer konnten nicht geladen werden');
    }
  };

  // ── Schritt 1: Datei hochladen und analysieren ──────────────────────────

  const handleAnalyze = async () => {
    if (!selectedUserId || !selectedFile) return;
    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('user_id', selectedUserId);
      const res = await apiClient.post('/admin/import/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreview(res.data);
      setStep('preview');
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Fehler beim Analysieren der Datei';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Schritt 2: Import durchführen (nach optionaler Bestätigung) ─────────

  const doImport = async () => {
    if (!preview || !selectedUserId) return;
    setIsLoading(true);
    try {
      const res = await apiClient.post('/admin/import/confirm', {
        user_id: selectedUserId,
        overwrite,
        entries: preview.entries,
        filename: selectedFile?.name,
      });
      setResult(res.data);
      setStep('result');
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Fehler beim Import';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmImport = () => {
    if (!preview || !selectedUserId) return;

    if (overwrite && preview.conflicts > 0) {
      confirm({
        title: 'Einträge überschreiben?',
        message: `${preview.conflicts} vorhandene Einträge werden überschrieben. Fortfahren?`,
        confirmLabel: 'Überschreiben',
        variant: 'danger',
        onConfirm: doImport,
      });
    } else {
      doImport();
    }
  };

  // ── Zurücksetzen ────────────────────────────────────────────────────────

  const handleReset = () => {
    setStep('upload');
    setSelectedFile(null);
    setPreview(null);
    setResult(null);
    setOverwrite(false);
    setWarningsExpanded(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // ── Render: Schritt 1 ───────────────────────────────────────────────────

  const renderUpload = () => (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-6">Datei hochladen</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Benutzer <span className="text-red-500">*</span>
          </label>
          <select
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            onFocus={loadUsers}
          >
            <option value="">Benutzer auswählen…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.first_name} {u.last_name} ({u.username})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            XLS-Datei <span className="text-red-500">*</span>
          </label>
          <div
            className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f && f.name.toLowerCase().endsWith('.xls')) {
                if (f.size > MAX_FILE_SIZE) {
                  toast.error('Datei zu groß (max. 5 MB)');
                  return;
                }
                setSelectedFile(f);
              } else {
                toast.error('Nur .xls-Dateien werden unterstützt');
              }
            }}
          >
            <Upload size={24} className="mx-auto text-gray-400 mb-2" />
            {selectedFile ? (
              <p className="text-sm text-primary font-medium">{selectedFile.name}</p>
            ) : (
              <>
                <p className="text-sm text-gray-500">Datei hierher ziehen oder klicken</p>
                <p className="text-xs text-gray-400 mt-1">.xls (TimeRec-Format, max. 5 MB)</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".xls"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  if (f.size > MAX_FILE_SIZE) {
                    toast.error('Datei zu groß (max. 5 MB)');
                    return;
                  }
                  setSelectedFile(f);
                }
              }}
            />
          </div>
        </div>
      </div>

      <button
        onClick={handleAnalyze}
        disabled={!selectedUserId || !selectedFile || isLoading}
        className="mt-6 px-6 py-2.5 bg-primary text-white rounded-lg text-sm font-medium
          hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? 'Analysiere…' : 'Datei analysieren →'}
      </button>
    </div>
  );

  // ── Render: Schritt 2 ───────────────────────────────────────────────────

  const renderPreview = () => {
    if (!preview) return null;
    return (
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Vorschau</h2>

        {/* Zusammenfassung */}
        <div className="flex flex-wrap gap-4 mb-4 text-sm">
          <span className="text-gray-600">
            <strong>{preview.total}</strong> Einträge gefunden
          </span>
          {preview.conflicts > 0 && (
            <span className="text-red-600 font-medium">
              <XCircle size={14} className="inline mr-1" />
              {preview.conflicts} Konflikte
            </span>
          )}
          {preview.arbzg_warnings > 0 && (
            <span className="text-amber-600 font-medium">
              <AlertTriangle size={14} className="inline mr-1" />
              {preview.arbzg_warnings} ArbZG-Warnungen
            </span>
          )}
        </div>

        {/* Tabelle */}
        <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Datum', 'Von', 'Bis', 'Pause', 'Netto', 'Notiz', 'Status'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.entries.map((e, idx) => {
                const hasWarning = e.arbzg_warnings.length > 0;
                const rowBg = e.has_conflict ? 'bg-red-50' : hasWarning ? 'bg-amber-50' : '';
                return (
                  <tr key={idx} className={`border-b border-gray-100 ${rowBg}`}>
                    <td className="px-3 py-2">{formatDate(e.date)}</td>
                    <td className="px-3 py-2">{formatTime(e.start_time)}</td>
                    <td className="px-3 py-2">{formatTime(e.end_time)}</td>
                    <td className="px-3 py-2">{e.break_minutes} min</td>
                    <td className="px-3 py-2">{calcNetHours(e.start_time, e.end_time, e.break_minutes)}</td>
                    <td className="px-3 py-2 text-gray-500">{e.note || '–'}</td>
                    <td className="px-3 py-2">
                      {e.has_conflict ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">
                          <XCircle size={11} /> Konflikt
                        </span>
                      ) : hasWarning ? (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 cursor-help"
                          title={e.arbzg_warnings.join('\n')}
                        >
                          <AlertTriangle size={11} /> ArbZG
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">
                          <CheckCircle size={11} /> Neu
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Überschreiben-Checkbox */}
        {preview.conflicts > 0 && (
          <label className="flex items-center gap-2 text-sm mb-6 cursor-pointer">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
            />
            <span className="text-gray-700">
              Konflikte überschreiben ({preview.conflicts} Einträge)
            </span>
          </label>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => setStep('upload')}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            ← Zurück
          </button>
          <button
            onClick={handleConfirmImport}
            disabled={isLoading}
            className="px-6 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Importiere…' : 'Import bestätigen →'}
          </button>
        </div>
      </div>
    );
  };

  // ── Render: Schritt 3 ───────────────────────────────────────────────────

  const renderResult = () => {
    if (!result) return null;
    return (
      <div>
        <div className="flex items-center gap-2 mb-6">
          <CheckCircle size={22} className="text-green-500" />
          <h2 className="text-lg font-semibold text-gray-800">Import abgeschlossen</h2>
        </div>

        <div className="grid grid-cols-3 gap-4 max-w-sm mb-6">
          <div className="bg-green-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-green-700">{result.imported}</div>
            <div className="text-xs text-green-600 mt-1">Importiert</div>
          </div>
          <div className="bg-red-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-red-700">{result.overwritten}</div>
            <div className="text-xs text-red-600 mt-1">Überschrieben</div>
          </div>
          <div className="bg-amber-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-amber-700">{result.warnings.length}</div>
            <div className="text-xs text-amber-600 mt-1">ArbZG-Warn.</div>
          </div>
        </div>

        {result.skipped > 0 && (
          <p className="text-sm text-gray-500 mb-4">
            {result.skipped} Einträge übersprungen (Konflikte nicht überschrieben).
          </p>
        )}

        {result.warnings.length > 0 && (
          <div className="mb-6">
            <button
              onClick={() => setWarningsExpanded(!warningsExpanded)}
              className="flex items-center gap-2 text-sm text-amber-700 font-medium mb-2"
            >
              <AlertTriangle size={14} />
              {result.warnings.length} ArbZG-Warnung(en)
              <span className="text-gray-400">{warningsExpanded ? '▲' : '▼'}</span>
            </button>
            {warningsExpanded && (
              <ul className="text-xs text-gray-600 space-y-1 pl-4 border-l-2 border-amber-200">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <p className="text-sm text-gray-500 mb-6">
          Import wurde im Änderungsprotokoll gespeichert.
        </p>

        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <RotateCcw size={14} />
          Weiteren Import starten
        </button>
      </div>
    );
  };

  // ── Haupt-Render ────────────────────────────────────────────────────────

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">XLS-Import</h1>
        <p className="text-sm text-gray-500 mt-1">
          Historische Zeiterfassungsdaten aus TimeRec-XLS-Dateien importieren
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <StepIndicator step={step} />
        {step === 'upload' && renderUpload()}
        {step === 'preview' && renderPreview()}
        {step === 'result' && renderResult()}
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
