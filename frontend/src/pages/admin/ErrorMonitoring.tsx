import { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, EyeOff, Trash2, Github, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import apiClient from '../../api/client';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';

interface ErrorLog {
  id: string;
  level: string;
  logger: string;
  message: string;
  traceback: string | null;
  path: string | null;
  method: string | null;
  status_code: number | null;
  count: number;
  first_seen: string;
  last_seen: string;
  status: 'open' | 'ignored' | 'resolved';
  github_issue_url: string | null;
}

const LEVEL_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-800 border-red-300',
  error: 'bg-orange-100 text-orange-800 border-orange-300',
  warning: 'bg-yellow-100 text-yellow-800 border-yellow-300',
};

const STATUS_TABS = [
  { value: '', label: 'Alle' },
  { value: 'open', label: 'Offen' },
  { value: 'ignored', label: 'Ignoriert' },
  { value: 'resolved', label: 'Behoben' },
];

export default function ErrorMonitoring() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [errors, setErrors] = useState<ErrorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('open');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [githubUrlInput, setGithubUrlInput] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<Record<string, number>>({});

  useEffect(() => {
    fetchErrors();
    fetchSummary();
  }, [filterStatus]);

  const fetchErrors = async () => {
    setLoading(true);
    try {
      const params = filterStatus ? `?status=${filterStatus}` : '';
      const res = await apiClient.get(`/admin/errors/${params}`);
      setErrors(res.data);
    } catch {
      toast.error('Fehler beim Laden');
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const res = await apiClient.get('/admin/errors/summary');
      setSummary(res.data);
    } catch {
      // Ignore
    }
  };

  const updateStatus = async (id: string, status: string) => {
    try {
      await apiClient.patch(`/admin/errors/${id}/status`, { status });
      toast.success(`Status auf "${status}" gesetzt`);
      fetchErrors();
      fetchSummary();
    } catch {
      toast.error('Fehler beim Aktualisieren');
    }
  };

  const deleteError = (id: string, message: string) => {
    confirm({
      title: 'Fehler löschen',
      message: `Diesen Fehler wirklich permanent löschen?\n\n"${message.slice(0, 100)}"`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/errors/${id}`);
          toast.success('Fehler gelöscht');
          fetchErrors();
          fetchSummary();
        } catch {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  const saveGithubUrl = async (id: string) => {
    const url = githubUrlInput[id];
    if (!url) return;
    try {
      await apiClient.patch(`/admin/errors/${id}/github-url`, { github_issue_url: url });
      toast.success('GitHub Issue URL gespeichert');
      fetchErrors();
    } catch {
      toast.error('Fehler beim Speichern');
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });

  const totalOpen = summary['open'] || 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Fehler-Monitoring</h1>
          {totalOpen > 0 && (
            <p className="text-sm text-red-600 mt-1 font-medium">
              {totalOpen} offene Fehler
            </p>
          )}
        </div>
        <button
          onClick={() => { fetchErrors(); fetchSummary(); }}
          className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
        >
          <RefreshCw size={16} />
          <span>Aktualisieren</span>
        </button>
      </div>

      {/* Summary badges */}
      <div className="flex gap-3 mb-6 flex-wrap">
        {Object.entries(summary).map(([status, count]) => (
          <div key={status} className={`px-3 py-1 rounded-full text-sm font-medium border
            ${status === 'open' ? 'bg-red-50 text-red-700 border-red-200' :
              status === 'ignored' ? 'bg-gray-50 text-gray-600 border-gray-200' :
              'bg-green-50 text-green-700 border-green-200'}`}>
            {status}: {count}
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 mb-6 border-b border-gray-200">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setFilterStatus(tab.value)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition
              ${filterStatus === tab.value
                ? 'bg-white border border-b-white border-gray-200 text-primary -mb-px'
                : 'text-gray-600 hover:text-gray-900'}`}
          >
            {tab.label}
            {tab.value === 'open' && totalOpen > 0 && (
              <span className="ml-2 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">
                {totalOpen}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error List */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Lädt...</div>
      ) : errors.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-8 text-center">
          <CheckCircle className="mx-auto text-green-500 mb-3" size={40} />
          <p className="text-green-700 font-medium">Keine Fehler gefunden</p>
        </div>
      ) : (
        <div className="space-y-3">
          {errors.map(err => (
            <div
              key={err.id}
              className={`bg-white rounded-xl border shadow-sm overflow-hidden
                ${err.status === 'resolved' ? 'opacity-60' : ''}`}
            >
              {/* Header */}
              <div className="p-4 flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded border ${LEVEL_COLORS[err.level] || 'bg-gray-100 text-gray-700 border-gray-300'}`}>
                      {err.level}
                    </span>
                    {err.count > 1 && (
                      <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full font-medium">
                        ×{err.count}
                      </span>
                    )}
                    {err.path && (
                      <span className="text-xs text-gray-500 font-mono">{err.method} {err.path}</span>
                    )}
                    {err.status !== 'open' && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${err.status === 'ignored' ? 'bg-gray-100 text-gray-600' : 'bg-green-100 text-green-700'}`}>
                        {err.status === 'ignored' ? 'Ignoriert' : 'Behoben'}
                      </span>
                    )}
                    {err.github_issue_url && (
                      <a
                        href={err.github_issue_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                      >
                        <Github size={12} /> Issue
                      </a>
                    )}
                  </div>
                  <p className="text-sm text-gray-800 font-mono truncate">{err.message}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    Zuerst: {formatDate(err.first_seen)} · Zuletzt: {formatDate(err.last_seen)} · {err.logger}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {err.status !== 'resolved' && (
                    <button
                      onClick={() => updateStatus(err.id, 'resolved')}
                      title="Als behoben markieren"
                      className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition"
                    >
                      <CheckCircle size={18} />
                    </button>
                  )}
                  {err.status === 'open' && (
                    <button
                      onClick={() => updateStatus(err.id, 'ignored')}
                      title="Ignorieren"
                      className="p-2 text-gray-500 hover:bg-gray-50 rounded-lg transition"
                    >
                      <EyeOff size={18} />
                    </button>
                  )}
                  {err.status !== 'open' && (
                    <button
                      onClick={() => updateStatus(err.id, 'open')}
                      title="Wieder öffnen"
                      className="p-2 text-orange-500 hover:bg-orange-50 rounded-lg transition"
                    >
                      <AlertTriangle size={18} />
                    </button>
                  )}
                  <button
                    onClick={() => deleteError(err.id, err.message)}
                    title="Löschen"
                    className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition"
                  >
                    <Trash2 size={18} />
                  </button>
                  <button
                    onClick={() => setExpanded(p => ({ ...p, [err.id]: !p[err.id] }))}
                    className="p-2 text-gray-400 hover:bg-gray-50 rounded-lg transition"
                  >
                    {expanded[err.id] ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </button>
                </div>
              </div>

              {/* Expanded: traceback + GitHub */}
              {expanded[err.id] && (
                <div className="border-t border-gray-100 p-4 bg-gray-50 space-y-3">
                  {err.traceback && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1 uppercase">Stack Trace</p>
                      <pre className="text-xs bg-gray-900 text-green-300 p-3 rounded overflow-x-auto max-h-64 whitespace-pre-wrap break-all">
                        {err.traceback}
                      </pre>
                    </div>
                  )}

                  {/* GitHub Issue Link */}
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1 uppercase">GitHub Issue</p>
                    {err.github_issue_url ? (
                      <div className="flex items-center gap-2">
                        <a
                          href={err.github_issue_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-blue-600 hover:underline flex items-center gap-1"
                        >
                          <Github size={14} /> {err.github_issue_url}
                        </a>
                        <button
                          onClick={() => {
                            setGithubUrlInput(p => ({ ...p, [err.id]: err.github_issue_url || '' }));
                          }}
                          className="text-xs text-gray-400 hover:text-gray-600"
                        >
                          Ändern
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <a
                          href={`https://github.com/phash/praxiszeit/issues/new?title=${encodeURIComponent('[Bug] ' + err.message.slice(0, 80))}&body=${encodeURIComponent(
                            `## Fehlerbeschreibung\n\n**Level:** ${err.level}\n**Logger:** ${err.logger}\n**Pfad:** ${err.method || ''} ${err.path || ''}\n**Zuerst gesehen:** ${err.first_seen}\n**Zuletzt gesehen:** ${err.last_seen}\n**Anzahl:** ${err.count}\n\n## Stack Trace\n\n\`\`\`\n${err.traceback || 'kein Stack Trace'}\n\`\`\``
                          )}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-sm bg-gray-800 text-white px-3 py-1.5 rounded-lg hover:bg-gray-700 transition"
                        >
                          <Github size={14} /> Issue auf GitHub erstellen
                        </a>
                        <div className="flex gap-1 flex-1">
                          <input
                            type="url"
                            placeholder="GitHub Issue URL einfügen..."
                            value={githubUrlInput[err.id] || ''}
                            onChange={(e) => setGithubUrlInput(p => ({ ...p, [err.id]: e.target.value }))}
                            className="flex-1 text-sm px-2 py-1 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                          />
                          <button
                            onClick={() => saveGithubUrl(err.id)}
                            disabled={!githubUrlInput[err.id]}
                            className="text-sm bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark disabled:opacity-50 transition"
                          >
                            Speichern
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
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
    </div>
  );
}
