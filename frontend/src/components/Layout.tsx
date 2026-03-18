import { useState, useEffect, useRef } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { useUIStore } from '../stores/uiStore';
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
  Play,
  Timer,
} from 'lucide-react';
import HelpPanel from './HelpPanel';
import StampWidget from './StampWidget';

export default function Layout() {
  const { user, logout } = useAuthStore();
  const { isStampSheetOpen, openStampSheet, closeStampSheet, notifyStampChange } = useUIStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [isClockedIn, setIsClockedIn] = useState(false);
  const [sheetClosing, setSheetClosing] = useState(false);
  const fabRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

  // Clock status for FAB appearance
  useEffect(() => {
    if (!user?.track_hours) return;
    const checkStatus = async () => {
      try {
        const res = await apiClient.get('/time-entries/clock-status');
        setIsClockedIn(res.data.is_clocked_in);
      } catch { /* ignore */ }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 60000);
    return () => clearInterval(interval);
  }, [user?.track_hours]);

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
    try {
      // F-010: call backend to increment token_version and clear the HttpOnly cookie
      await apiClient.post('/auth/logout');
    } catch {
      // Even if the backend call fails, clear local state
    }
    logout();
    navigate('/login');
  };

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/time-tracking', label: 'Zeiterfassung', icon: Clock },
    { path: '/absences', label: 'Abwesenheiten', icon: Calendar },
    { path: '/profile', label: 'Profil', icon: User },
  ];

  const adminNavItems = [
    { path: '/admin', label: 'Admin-Dashboard', icon: Settings },
    { path: '/admin/users', label: 'Benutzerverwaltung', icon: Users },
    { path: '/admin/change-requests', label: 'Änderungsanträge', icon: FileEdit },
    { path: '/admin/reports', label: 'Berichte', icon: FileText },
    { path: '/admin/absences', label: 'Abwesenheiten', icon: Calendar },
    { path: '/admin/audit-log', label: 'Änderungsprotokoll', icon: ScrollText },
    { path: '/admin/errors', label: 'Fehler-Monitoring', icon: AlertTriangle },
    { path: '/admin/vacation-approvals', label: 'Urlaubsanträge', icon: ClipboardCheck },
    { path: '/admin/import', label: 'Import', icon: Upload },
    { path: '/admin/settings', label: 'Einstellungen', icon: Settings },
  ];

  return (
    <div className="h-screen bg-background flex overflow-hidden">
      {/* Skip to Content Link for Accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-primary text-white px-4 py-2 rounded-lg z-[100] focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        Zum Inhalt springen
      </a>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-surface border-b border-border flex items-center justify-between px-4 z-30">
        <h1 className="text-xl font-bold text-primary">PraxisZeit</h1>
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

      {/* Sidebar */}
      <aside
        className={`
          w-64 bg-surface border-r border-border flex flex-col
          fixed lg:relative inset-y-0 left-0 z-50
          transform transition-transform duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo/Title */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">PraxisZeit</h1>
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
                    className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                      active
                        ? 'bg-primary text-white'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    <Icon size={20} />
                    <span className="font-medium">{item.label}</span>
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
            <a
              href={user?.role === 'admin' ? '/help/CHEATSHEET-ADMIN.md' : '/help/CHEATSHEET-MITARBEITER.md'}
              download
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
            >
              <BookOpen size={13} />
              <span>Cheat-Sheet</span>
            </a>
            <a
              href={user?.role === 'admin' ? '/help/HANDBUCH-ADMIN.md' : '/help/HANDBUCH-MITARBEITER.md'}
              download
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
            >
              <FileText size={13} />
              <span>{user?.role === 'admin' ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch'}</span>
            </a>
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
          <p className="text-center text-xs text-gray-300 mt-1">v{__APP_VERSION__}</p>
        </div>
      </aside>

      {/* Main Content */}
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden lg:pt-0 pt-16 pb-20 lg:pb-0 bg-background" tabIndex={-1}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
          <Outlet />
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-30" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="relative">
          {/* FAB - Centered Stamp Button */}
          {user?.track_hours && (
            <button
              ref={fabRef}
              onClick={openStampSheet}
              className={`absolute left-1/2 -translate-x-1/2 -top-3 z-[31] w-14 h-14 rounded-full shadow-elevated flex items-center justify-center transition-all duration-300 active:scale-90 ${
                isClockedIn
                  ? 'bg-gradient-to-br from-success to-[#4AA87A] fab-pulse'
                  : 'bg-gradient-to-br from-primary to-primary-dark'
              }`}
              aria-label={isClockedIn ? 'Eingestempelt – Stempeluhr öffnen' : 'Stempeluhr öffnen'}
            >
              {isClockedIn ? <Timer size={24} className="text-white" /> : <Play size={24} className="text-white ml-0.5" />}
            </button>
          )}

          {/* Nav Bar */}
          <div className="bg-white/[0.85] supports-[backdrop-filter]:backdrop-blur-xl border-t border-border rounded-t-3xl">
            <div className="flex items-center h-16">
              {[
                { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
                { to: '/journal', icon: Clock, label: 'Journal' },
              ].map((item) => {
                const Icon = item.icon;
                const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to);
                return (
                  <Link key={item.to} to={item.to} className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${active ? 'text-primary' : 'text-text-secondary'}`}>
                    <Icon size={22} strokeWidth={1.75} />
                    <span className="text-[10px] font-medium">{item.label}</span>
                    {active && <div className="w-1 h-1 rounded-full bg-primary" />}
                  </Link>
                );
              })}
              {/* FAB spacer */}
              <div className="w-[72px] shrink-0" />
              {[
                { to: '/absences', icon: Calendar, label: 'Abwes.' },
                { to: '/profile', icon: User, label: 'Profil' },
              ].map((item) => {
                const Icon = item.icon;
                const active = location.pathname.startsWith(item.to);
                return (
                  <Link key={item.to} to={item.to} className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${active ? 'text-primary' : 'text-text-secondary'}`}>
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
      {isStampSheetOpen && (
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
            className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-surface rounded-t-3xl shadow-elevated focus:outline-none"
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
    </div>
  );
}
