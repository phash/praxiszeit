import { useState, useEffect, useRef, Suspense } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { trackHoursToday } from '../utils/contractToday';
import { useUIStore } from '../stores/uiStore';
import DialogFocusTrap from './DialogFocusTrap';
import { useSystemStore } from '../stores/systemStore';
import TrialBanner from './TrialBanner';
import BetaBadge from './BetaBadge';
import ImpersonationBanner from './ImpersonationBanner';
import apiClient from '../api/client';
import {
  LayoutDashboard,
  Clock,
  Calendar,
  User,
  Users,
  FileText,
  FileEdit,
  ScrollText,
  LogOut,
  Settings,
  Menu,
  X,
  AlertTriangle,
  BookOpen,
  HelpCircle,
  Shield,
  ClipboardCheck,
  Upload,
  CreditCard,
  Play,
  Timer,
  Heart,
  Rocket,
  Database,
  CalendarClock,
  CalendarRange,
} from 'lucide-react';
import HelpPanel from './HelpPanel';
import StampWidget from './StampWidget';
import { DocDrawer } from './DocDrawer';
import OnboardingModal from './OnboardingModal';

export default function Layout() {
  const { user, logout } = useAuthStore();
  // F011: Stundenzählung laut heute gültigem Vertrag (schedule_today).
  const userTracksHours = trackHoursToday(user) === true;
  // #370: during read-only impersonation, hide the primary write CTA (stamp
  // button). The backend middleware is the hard guarantee; this is UX.
  const isImpersonating = useAuthStore((s) => s.isImpersonating());
  const { isStampSheetOpen, openStampSheet, closeStampSheet, notifyStampChange } = useUIStore();
  const requestVersion = useUIStore((st) => st.requestVersion);
  // ui-18: Stempeln über eine Seiten-Karte (notifyStampChange) soll den FAB sofort umschalten.
  const stampVersion = useUIStore((st) => st.stampVersion);
  const deploymentMode = useSystemStore((s) => s.info?.deployment_mode);
  const isBeta = useSystemStore((s) => s.info?.beta === true);
  const shiftPlanningEnabled = useSystemStore((s) => s.isShiftPlanningEnabled());
  const location = useLocation();
  const navigate = useNavigate();
  const showFab = userTracksHours && !isImpersonating;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<'schnellstart' | 'cheatsheet'>('cheatsheet');
  const [isClockedIn, setIsClockedIn] = useState(false);
  const [sheetClosing, setSheetClosing] = useState(false);
  const [pendingCRCount, setPendingCRCount] = useState(0);
  const [pendingVRCount, setPendingVRCount] = useState(0);
  const fabRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

  // Pending change request + vacation request counts for the admin badges.
  // auth-19: neu laden bei Routenwechsel und uiStore-Ereignis (requestVersion), Abfrage im
  // Hintergrund-Tab pausieren und beim Zurückkehren nachladen.
  useEffect(() => {
    if (user?.role !== 'admin') return;
    const fetchCounts = async () => {
      try {
        const res = await apiClient.get('/admin/change-requests/pending-count');
        setPendingCRCount(res.data.count);
      } catch { /* ignore */ }
      try {
        const res = await apiClient.get('/admin/vacation-requests/pending-count');
        setPendingVRCount(res.data.count);
      } catch { /* ignore */ }
    };
    fetchCounts();
    const interval = setInterval(() => {
      if (!document.hidden) fetchCounts();
    }, 60000);
    const onVisible = () => {
      if (!document.hidden) fetchCounts();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [user?.role, requestVersion, location.pathname]);

  // Clock status for FAB appearance
  useEffect(() => {
    if (!userTracksHours) return;
    const checkStatus = async () => {
      try {
        const res = await apiClient.get('/time-entries/clock-status');
        setIsClockedIn(res.data.is_clocked_in);
      } catch { /* ignore */ }
    };
    checkStatus();
    const interval = setInterval(() => {
      if (!document.hidden) checkStatus();
    }, 60000);
    const onVisible = () => {
      if (!document.hidden) checkStatus();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [userTracksHours, stampVersion]);

  const handleStampSuccess = () => {
    apiClient.get('/time-entries/clock-status').then(res => {
      setIsClockedIn(res.data.is_clocked_in);
    }).catch(() => {});
    notifyStampChange();
    setSheetClosing(true);
    setTimeout(() => {
      closeStampSheet();
      setSheetClosing(false);
      fabRef.current?.focus();
    }, 250);
  };

  // Dismiss without stamping – no notifyStampChange
  const handleSheetDismiss = () => {
    setSheetClosing(true);
    setTimeout(() => {
      closeStampSheet();
      setSheetClosing(false);
      fabRef.current?.focus();
    }, 250);
  };

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Close sidebar / stamp sheet on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isStampSheetOpen) handleSheetDismiss();
        else if (sidebarOpen) setSidebarOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [sidebarOpen, isStampSheetOpen]);

  // Move focus into stamp sheet when it opens
  useEffect(() => {
    if (isStampSheetOpen) {
      setTimeout(() => sheetRef.current?.focus(), 50);
    }
  }, [isStampSheetOpen]);

  const handleLogout = async () => {
    // authStore.logout() now handles the backend /auth/logout call, clears
    // the in-memory access token, drops persist storage and wipes caches.
    await logout();
    navigate('/login');
  };

  const isActive = (path: string) => {
    // F-059: Highlight the nav entry on sub-routes as well.
    // Example: /admin/users/:userId/journal should still light up the
    // "Benutzerverwaltung" item.
    //
    // Two items keep exact-match semantics because they are nav roots
    // with children below them — otherwise they would swallow every
    // child route:
    //   /      (Dashboard — parent of /time-tracking, /absences, …)
    //   /admin (Admin-Dashboard — parent of /admin/users, /admin/reports, …)
    if (path === '/' || path === '/admin') {
      return location.pathname === path;
    }
    // Exact match OR a proper segment-prefix (so '/admin' doesn't
    // incorrectly match '/admin-foo').
    return (
      location.pathname === path ||
      location.pathname.startsWith(path + '/')
    );
  };

  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/time-tracking', label: 'Zeiterfassung', icon: Clock },
    { path: '/absences', label: 'Abwesenheiten', icon: Calendar },
    // #305 Schichtplan (read-only) — nur wenn das Feature aktiviert ist.
    ...(shiftPlanningEnabled
      ? [{ path: '/shift-planning', label: 'Schichtplan', icon: CalendarClock }]
      : []),
    { path: '/profile', label: 'Profil', icon: User },
  ];

  const adminNavItems = [
    { path: '/admin', label: 'Admin-Dashboard', icon: Settings, badge: 0 },
    { path: '/admin/users', label: 'Benutzerverwaltung', icon: Users, badge: 0 },
    // 1.21 Teamübersicht: wer arbeitet laut Arbeitszeit-Blöcken wann
    { path: '/admin/team-schedule', label: 'Arbeitszeiten im Team', icon: CalendarRange, badge: 0 },
    { path: '/admin/change-requests', label: 'Änderungsanträge', icon: FileEdit, badge: pendingCRCount },
    { path: '/admin/reports', label: 'Berichte', icon: FileText, badge: 0 },
    { path: '/admin/absences', label: 'Abwesenheiten', icon: Calendar, badge: 0 },
    { path: '/admin/audit-log', label: 'Änderungsprotokoll', icon: ScrollText, badge: 0 },
    { path: '/admin/errors', label: 'Fehler-Monitoring', icon: AlertTriangle, badge: 0 },
    { path: '/admin/vacation-approvals', label: 'Anträge', icon: ClipboardCheck, badge: pendingVRCount },
    { path: '/admin/import', label: 'Import', icon: Upload, badge: 0 },
    { path: '/admin/settings', label: 'Einstellungen', icon: Settings, badge: 0 },
    // #305 Schichtplanung-Verwaltung — nur wenn das Feature aktiviert ist.
    ...(shiftPlanningEnabled
      ? [{ path: '/admin/shift-planning', label: 'Schichtplanung', icon: CalendarClock, badge: 0 }]
      : []),
    { path: '/admin/backups', label: 'Datensicherung', icon: Database, badge: 0 },
    // Billing is SaaS-only — on-prem installs hide this entry via the filter below.
    ...(deploymentMode === 'saas'
      ? [{ path: '/admin/billing', label: 'Abrechnung', icon: CreditCard, badge: 0 }]
      : []),
  ];

  return (
    <div className="h-screen bg-background flex overflow-hidden">
      {/* Skip to Content Link for Accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-primary text-white px-4 py-2 rounded-lg z-100 focus:outline-hidden focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        Zum Inhalt springen
      </a>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-surface border-b border-border flex items-center justify-between px-4 z-30">
        <div className="flex items-center">
          <h1 className="text-xl font-bold text-primary">PraxisZeit</h1>
          {isBeta && <BetaBadge />}
        </div>
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 rounded-xl hover:bg-muted transition"
          aria-label="Menü öffnen"
        >
          <Menu size={24} className="text-text-primary" />
        </button>
      </div>

      {/* Backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar (ui-19: geöffnet auf Mobil = modaler Dialog mit Fokusfalle, Fokus zurück zum Menü-Knopf) */}
      <DialogFocusTrap
        active={sidebarOpen}
        focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, returnFocusOnDeactivate: true, fallbackFocus: '#main-content' }}
      >
      <aside
        role={sidebarOpen ? 'dialog' : undefined}
        aria-modal={sidebarOpen ? 'true' : undefined}
        aria-label={sidebarOpen ? 'Hauptmenü' : undefined}
        className={`
          w-64 bg-surface border-r border-border flex flex-col
          fixed lg:relative inset-y-0 left-0 z-50
          transition-[transform,visibility] duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full max-lg:invisible lg:translate-x-0'}
        `}
      >
        {/* Logo/Title */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div>
            <div className="flex items-center">
              <h1 className="text-2xl font-bold text-primary">PraxisZeit</h1>
              {isBeta && <BetaBadge />}
            </div>
            <p className="text-sm text-text-secondary mt-1">Zeiterfassung</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 rounded-xl hover:bg-muted transition"
            aria-label="Menü schließen"
          >
            <X size={24} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {/* Employee Navigation */}
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                aria-current={active ? 'page' : undefined}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  active
                    ? 'bg-primary-light text-primary-dark'
                    : 'text-text-secondary hover:bg-muted'
                }`}
              >
                <Icon size={20} />
                <span className="font-medium">{item.label}</span>
              </Link>
            );
          })}

          {/* Admin Navigation */}
          {user?.role === 'admin' && (
            <>
              <div className="my-4 border-t border-border pt-4">
                <p className="px-4 text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  Administration
                </p>
              </div>
              {adminNavItems.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    aria-current={active ? 'page' : undefined}
                    className={`flex items-center justify-between gap-2 px-4 py-3 rounded-lg transition-colors ${
                      active
                        ? 'bg-primary text-white'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    <div className="flex items-center space-x-3 min-w-0">
                      <Icon size={20} />
                      <span className="font-medium">{item.label}</span>
                    </div>
                    {item.badge > 0 && (
                      <span className={`inline-flex shrink-0 items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-bold rounded-full ${
                        active ? 'bg-white text-primary' : 'bg-red-500 text-white'
                      }`}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </>
          )}
        </nav>

        {/* User Info & Logout */}
        <div className="p-4 border-t border-border">
          <Link to="/profile" className="flex items-center space-x-3 mb-3 hover:bg-muted rounded-xl p-1 -m-1 transition-colors">
            {user?.profile_picture ? (
              <img src={user.profile_picture} className="w-10 h-10 rounded-full object-cover" alt="" />
            ) : (
              <div className="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center font-semibold">
                {user?.first_name?.[0]}
                {user?.last_name?.[0]}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">
                {user?.first_name} {user?.last_name}
              </p>
              <p className="text-xs text-text-secondary truncate">{user?.username}</p>
            </div>
          </Link>
          {/* Handbuch-Downloads */}
          <div className="mb-2 flex flex-col gap-1">
            {user?.role === 'admin' && (
              <button
                onClick={() => { setDrawerTab('schnellstart'); setDrawerOpen(true); }}
                className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors w-full text-left"
              >
                <Rocket size={13} />
                <span>Schnellstart</span>
              </button>
            )}
            <button
              onClick={() => { setDrawerTab('cheatsheet'); setDrawerOpen(true); }}
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors w-full text-left"
            >
              <BookOpen size={13} />
              <span>Cheat-Sheet</span>
            </button>
            <Link
              to={user?.role === 'admin' ? '/help/praxisleitung' : '/help/mitarbeitende'}
              onClick={() => setSidebarOpen(false)}
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors w-full text-left"
            >
              <FileText size={13} />
              <span>{user?.role === 'admin' ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch'}</span>
            </Link>
          </div>

          <Link
            to="/privacy"
            className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-lg transition-colors mb-1"
          >
            <Shield size={12} />
            <span>Datenschutzerklärung</span>
          </Link>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setHelpOpen(true)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 rounded-lg transition-colors"
              aria-label="Hilfe öffnen"
            >
              <HelpCircle size={16} />
              <span>Hilfe</span>
            </button>
            <button
              onClick={handleLogout}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <LogOut size={16} />
              <span>Abmelden</span>
            </button>
          </div>
          <p className="text-center text-xs text-gray-300 mt-1">
            v{__APP_VERSION__}
            {deploymentMode === 'onprem' && (
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-sm bg-gray-100 text-gray-500">
                Lokale Installation
              </span>
            )}
          </p>
          <a
            href="https://paypal.me/mroedig"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 flex items-center justify-center gap-1.5 text-xs text-center text-gray-400 hover:text-primary transition-colors"
          >
            <Heart size={13} className="shrink-0" aria-hidden="true" />
            Unterstützen Sie die Entwicklung mit einer Spende
          </a>
        </div>
      </aside>
      </DialogFocusTrap>

      {/* Main Content */}
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden lg:pt-0 pt-16 pb-20 lg:pb-0 bg-background" tabIndex={-1}>
        <ImpersonationBanner />
        <TrialBanner />
        {/* #287: Arbeitsbereich nutzt die volle Breite neben dem Menü (kein
            max-w-7xl-Cap mehr, das auf breiten Screens ~die Hälfte leer ließ).
            Die responsive px-Polsterung lässt einen schmalen Rand ⇒ ~95 % Füllung.
            Schmale Form-Seiten (Billing/Backups) behalten ihre eigenen max-w. */}
        <div className="w-full px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
          {/* #147: Lazy-geladene Routen (admin/* + Help) -> Suspense nur um den
              Content, damit die Sidebar beim Chunk-Laden stehen bleibt. */}
          <Suspense
            fallback={
              <div role="status" aria-live="polite" className="py-12 text-center text-gray-500">
                Lädt…
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-30" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="relative">
          {/* FAB - Centered Stamp Button */}
          {showFab && (
            <button
              ref={fabRef}
              onClick={openStampSheet}
              className={`absolute left-1/2 -translate-x-1/2 -top-3 z-31 w-14 h-14 rounded-full shadow-elevated flex items-center justify-center transition-all duration-300 active:scale-90 ${
                isClockedIn
                  ? 'bg-linear-to-br from-success to-[#4AA87A] fab-pulse'
                  : 'bg-linear-to-br from-primary to-primary-dark'
              }`}
              aria-label={isClockedIn ? 'Eingestempelt – Stempeluhr öffnen' : 'Stempeluhr öffnen'}
            >
              {isClockedIn ? <Timer size={24} className="text-white" /> : <Play size={24} className="text-white ml-0.5" />}
            </button>
          )}

          {/* Nav Bar */}
          <div className="bg-white/85 supports-backdrop-filter:backdrop-blur-xl border-t border-border rounded-t-3xl">
            <div className="flex items-center h-16">
              {[
                { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
                { to: '/journal', icon: Clock, label: 'Journal' },
              ].map((item) => {
                const Icon = item.icon;
                // auth-17: /journal leitet auf /time-tracking?tab=journal um — dort gilt der Reiter als aktiv.
                const onJournalTab = location.pathname === '/time-tracking'
                  && new URLSearchParams(location.search).get('tab') === 'journal';
                const active = item.to === '/journal'
                  ? location.pathname.startsWith('/journal') || onJournalTab
                  : item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to);
                return (
                  <Link key={item.to} to={item.to} aria-current={active ? 'page' : undefined} className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${active ? 'text-primary' : 'text-text-secondary'}`}>
                    <Icon size={22} strokeWidth={1.75} />
                    <span className="text-[10px] font-medium">{item.label}</span>
                    {active && <div className="w-1 h-1 rounded-full bg-primary" />}
                  </Link>
                );
              })}
              {/* FAB spacer (ui-19: nur, wenn der FAB auch gerendert wird) */}
              {showFab && <div className="w-[72px] shrink-0" />}
              {[
                { to: '/absences', icon: Calendar, label: 'Abwes.' },
                { to: '/profile', icon: User, label: 'Profil' },
              ].map((item) => {
                const Icon = item.icon;
                const active = location.pathname.startsWith(item.to);
                return (
                  <Link key={item.to} to={item.to} aria-current={active ? 'page' : undefined} className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${active ? 'text-primary' : 'text-text-secondary'}`}>
                    <Icon size={22} strokeWidth={1.75} />
                    <span className="text-[10px] font-medium">{item.label}</span>
                    {active && <div className="w-1 h-1 rounded-full bg-primary" />}
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </nav>

      {/* Stamp Bottom Sheet */}
      {isStampSheetOpen && !isImpersonating && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-40 lg:hidden transition-opacity duration-200"
            style={{ opacity: sheetClosing ? 0 : 1 }}
            onClick={handleSheetDismiss}
          />
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="stamp-sheet-title"
            tabIndex={-1}
            className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-surface rounded-t-3xl shadow-elevated focus:outline-hidden"
            style={{
              animation: sheetClosing ? undefined : 'slideUp 300ms ease-out',
              transform: sheetClosing ? 'translateY(100%)' : 'translateY(0)',
              transition: sheetClosing ? 'transform 250ms ease-in' : undefined,
              paddingBottom: 'env(safe-area-inset-bottom)',
            }}
          >
            <div className="flex items-center justify-between px-4 pt-3 pb-2">
              <div className="w-8" />
              <div className="w-10 h-1 bg-gray-300 rounded-full" aria-hidden="true" />
              <button
                onClick={handleSheetDismiss}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-muted transition"
                aria-label="Schließen"
              >
                <X size={18} className="text-text-secondary" />
              </button>
            </div>
            <div className="px-6 pb-6">
              <h2 id="stamp-sheet-title" className="sr-only">Stempeluhr</h2>
              <StampWidget variant="sheet" onSuccess={handleStampSuccess} />
            </div>
          </div>
        </>
      )}

      <HelpPanel isOpen={helpOpen} onClose={() => setHelpOpen(false)} />

      <DocDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        isAdmin={user?.role === 'admin'}
        initialTab={drawerTab}
      />

      <OnboardingModal />
    </div>
  );
}
