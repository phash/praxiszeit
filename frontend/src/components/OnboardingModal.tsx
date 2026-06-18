import { useState, useEffect, useCallback, type ComponentType } from 'react';
import {
  LayoutDashboard, Users, FileEdit, FileText,
  Clock, Calendar, User as UserIcon, BookOpen,
} from 'lucide-react';
import { useAuthStore } from '../stores/authStore';
import { useSystemStore } from '../stores/systemStore';
import { lockBodyScroll, unlockBodyScroll } from '../utils/bodyScrollLock';
import apiClient from '../api/client';

interface Feature {
  icon: ComponentType<{ size?: number | string; className?: string }>;
  title: string;
  desc: string;
}

const ADMIN_FEATURES: Feature[] = [
  { icon: LayoutDashboard, title: 'Admin-Dashboard', desc: 'Überblick über Team-Stunden, Salden und fehlende Buchungen.' },
  { icon: Users, title: 'Benutzerverwaltung', desc: 'Mitarbeiter anlegen, Arbeitszeiten und Urlaubskonten pflegen.' },
  { icon: FileEdit, title: 'Änderungsanträge', desc: 'Korrekturen der Mitarbeiter prüfen und freigeben.' },
  { icon: FileText, title: 'Berichte', desc: 'Monats-/Jahresauswertungen ansehen und exportieren.' },
];

const EMPLOYEE_FEATURES: Feature[] = [
  { icon: Clock, title: 'Zeiterfassung', desc: 'Ein- und ausstempeln, Arbeitszeiten erfassen und ansehen.' },
  { icon: Calendar, title: 'Abwesenheiten', desc: 'Urlaub und Krankheit beantragen und im Kalender sehen.' },
  { icon: FileEdit, title: 'Änderungsanträge', desc: 'Korrekturen an deinen Einträgen beantragen.' },
  { icon: UserIcon, title: 'Profil', desc: 'Deine Daten, Kalenderfarbe und Passwort verwalten.' },
];

/**
 * Rollenspezifisches Welcome-Onboarding beim allerersten Login.
 *
 * Sichtbar, solange der eingeloggte Nutzer `onboarding_completed_at == null`
 * hat. Beim Schließen (Button/Escape/Overlay) wird `POST /auth/onboarding/
 * complete` gerufen, das den Zeitstempel setzt — danach erscheint es nicht
 * wieder (auch nicht auf anderen Geräten). Selbst-entscheidend: einfach in
 * Layout mounten, kein Prop nötig.
 */
export default function OnboardingModal() {
  const { user, setUser } = useAuthStore();
  // Admin-Toggle (Default an): ein explizites false in /system/info unterdrückt die Tour.
  const onboardingEnabled = useSystemStore((s) => s.info?.onboarding_enabled !== false);
  // Erst nach geladenem /system/info entscheiden — sonst flackert die Tour kurz auf,
  // bevor ein evtl. gesetztes onboarding_enabled=false greift.
  const systemLoaded = useSystemStore((s) => s.isLoaded);
  const [closed, setClosed] = useState(false);

  const show = !!user && !closed && !user.onboarding_completed_at && onboardingEnabled && systemLoaded;

  const complete = useCallback(async () => {
    setClosed(true); // optimistisch sofort ausblenden
    const current = useAuthStore.getState().user;
    if (!current) return;
    try {
      const resp = await apiClient.post('/auth/onboarding/complete');
      setUser({ ...current, ...resp.data }); // Flag persistieren -> kein erneutes Anzeigen
    } catch {
      // Best-effort: diese Sitzung ausgeblendet; beim nächsten Login erneuter Versuch.
    }
  }, [setUser]);

  useEffect(() => {
    if (!show) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') void complete(); };
    document.addEventListener('keydown', onKey);
    lockBodyScroll();
    return () => {
      document.removeEventListener('keydown', onKey);
      unlockBodyScroll();
    };
  }, [show, complete]);

  if (!show) return null;

  const isAdmin = user!.role === 'admin';
  const features = isAdmin ? ADMIN_FEATURES : EMPLOYEE_FEATURES;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={() => void complete()} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Willkommen bei PraxisZeit"
        className="relative z-10 bg-white rounded-xl shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-gray-100">
          <h2 className="text-xl font-semibold text-gray-900">Willkommen bei PraxisZeit 👋</h2>
          <p className="mt-1 text-sm text-gray-500">
            {isAdmin
              ? `Schön, dass du da bist, ${user!.first_name}! Als Administrator hast du diese Bereiche:`
              : `Schön, dass du da bist, ${user!.first_name}! Das kannst du hier tun:`}
          </p>
        </div>

        {/* Feature-Liste */}
        <div className="px-6 py-4 space-y-3 overflow-y-auto">
          {features.map((f) => (
            <div key={f.title} className="flex items-start gap-3">
              <div className="shrink-0 w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <f.icon size={18} />
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900">{f.title}</div>
                <div className="text-sm text-gray-500 leading-snug">{f.desc}</div>
              </div>
            </div>
          ))}

          <div className="flex items-start gap-3 pt-1">
            <div className="shrink-0 w-9 h-9 rounded-lg bg-gray-50 text-gray-500 flex items-center justify-center">
              <BookOpen size={18} />
            </div>
            <div className="text-sm text-gray-500 leading-snug self-center">
              {isAdmin ? 'Admin-Handbuch' : 'Handbuch & Cheat-Sheet'} findest du jederzeit unten links in der Seitenleiste.
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-end shrink-0">
          <button
            onClick={() => void complete()}
            autoFocus
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Los geht's
          </button>
        </div>
      </div>
    </div>
  );
}
