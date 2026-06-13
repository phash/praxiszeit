import { useEffect, useState } from 'react';
import { Download, X } from 'lucide-react';
import apiClient from '../api/client';
import { safeHttpUrl } from '../utils/url';

interface UpdateData {
  latest_version: string;
  current_version: string;
  changelog?: string;
  critical?: boolean;
}

/**
 * Admin-Hinweis, dass eine neue PraxisZeit-Version verfügbar ist, mit Link zur
 * Downloadseite. Prüft einmal pro Browser-Session gegen den Update-Server
 * (POST /api/admin/updates/check). Ist kein Update-Server konfiguriert
 * (z.B. Docker/Dev → 404) oder kein Update vorhanden, wird nichts angezeigt.
 * Pro Version einmal ausblendbar.
 */
export default function UpdateBanner() {
  const [info, setInfo] = useState<UpdateData | null>(null);
  const [downloadPage, setDownloadPage] = useState('https://praxiszeit.mr-development.de');
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const apply = (data: any) => {
      if (!data?.update_available || !data?.update) return;
      if (sessionStorage.getItem('pz-update-dismissed') === data.update.latest_version) return;
      setInfo(data.update);
      // download_page stammt vom Update-Server → vor dem Rendern als href
      // auf ein sicheres http(s)-Schema einschränken (kein javascript:/data:).
      const safe = safeHttpUrl(data.download_page);
      if (safe) setDownloadPage(safe);
    };
    const cached = sessionStorage.getItem('pz-update-check');
    if (cached) {
      try { apply(JSON.parse(cached)); } catch { /* ignore */ }
      return;
    }
    (async () => {
      try {
        const { data } = await apiClient.post('/admin/updates/check');
        if (cancelled) return;
        sessionStorage.setItem('pz-update-check', JSON.stringify(data));
        apply(data);
      } catch {
        // 404 (kein Update-Server) oder Netzwerkfehler → kein Banner
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!info || dismissed) return null;

  const critical = info.critical === true;
  return (
    <div
      className={`mb-4 rounded-xl border px-4 py-3 flex items-start gap-3 ${
        critical ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'
      }`}
      role="status"
    >
      <Download size={20} className={`${critical ? 'text-red-600' : 'text-blue-600'} mt-0.5 shrink-0`} />
      <div className="flex-1 text-sm">
        <p className={`font-semibold ${critical ? 'text-red-800' : 'text-blue-800'}`}>
          Neue Version {info.latest_version} verfügbar{critical && ' — wichtiges Update'}
        </p>
        <p className="text-gray-600">
          Installiert: {info.current_version}.{' '}
          <a
            href={downloadPage}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary font-medium hover:underline"
          >
            Zur Downloadseite
          </a>
        </p>
        {info.changelog && <p className="text-xs text-gray-500 mt-1 line-clamp-2">{info.changelog}</p>}
      </div>
      <button
        onClick={() => {
          sessionStorage.setItem('pz-update-dismissed', info.latest_version);
          setDismissed(true);
        }}
        aria-label="Hinweis ausblenden"
        className="p-1 text-gray-400 hover:text-gray-700 rounded-lg shrink-0"
      >
        <X size={18} />
      </button>
    </div>
  );
}
