import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { Download, HelpCircle } from 'lucide-react';
import {
  Accordion,
  CheatsheetMitarbeiter,
  CheatsheetAdmin,
  handbuchMitarbeiterSections,
  handbuchAdminSections,
} from '../components/DocViewer';

// ── Main Help page ─────────────────────────────────────────────────────────────

export default function Help() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');
  const isAdmin = user?.role === 'admin';

  const cheatsheetFile = isAdmin
    ? '/help/CHEATSHEET-ADMIN.md'
    : '/help/CHEATSHEET-MITARBEITER.md';
  const handbuchFile = isAdmin
    ? '/help/HANDBUCH-ADMIN.md'
    : '/help/HANDBUCH-MITARBEITER.md';

  return (
    <div>
      {/* Header */}
      <div className="flex items-center space-x-3 mb-6">
        <HelpCircle size={28} className="text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hilfe &amp; Dokumentation</h1>
          <p className="text-sm text-gray-500">
            {isAdmin ? 'Administratoren-Dokumentation' : 'Mitarbeiter-Dokumentation'}
          </p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="border-b border-gray-200 mb-6">
        <div className="flex space-x-6">
          {(['cheatsheet', 'handbuch'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'cheatsheet' ? 'Kurzanleitung' : 'Handbuch'}
            </button>
          ))}
        </div>
      </div>

      {/* Cheatsheet Tab */}
      {activeTab === 'cheatsheet' && (
        <div>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-gray-800">
              {isAdmin ? 'Kurzanleitung für Administratoren' : 'Kurzanleitung für Mitarbeiter'}
            </h2>
            <a
              href={cheatsheetFile}
              download
              className="flex items-center space-x-1.5 px-3 py-1.5 text-sm text-primary border border-primary rounded-lg hover:bg-primary hover:text-white transition-colors"
            >
              <Download size={14} />
              <span>Herunterladen (.md)</span>
            </a>
          </div>
          {isAdmin ? <CheatsheetAdmin /> : <CheatsheetMitarbeiter />}
        </div>
      )}

      {/* Handbuch Tab */}
      {activeTab === 'handbuch' && (
        <div>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-gray-800">
              {isAdmin ? 'Administrator-Handbuch' : 'Mitarbeiter-Handbuch'}
            </h2>
            <a
              href={handbuchFile}
              download
              className="flex items-center space-x-1.5 px-3 py-1.5 text-sm text-primary border border-primary rounded-lg hover:bg-primary hover:text-white transition-colors"
            >
              <Download size={14} />
              <span>Vollständiges Handbuch (.md)</span>
            </a>
          </div>
          <p className="text-sm text-gray-500 mb-5">
            Klicken Sie auf einen Abschnitt, um ihn aufzuklappen. Das vollständige Handbuch können Sie als Markdown-Datei herunterladen.
          </p>
          <Accordion items={isAdmin ? handbuchAdminSections : handbuchMitarbeiterSections} />
        </div>
      )}
    </div>
  );
}
