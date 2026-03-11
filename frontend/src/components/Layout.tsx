import { useState, useEffect } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
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
} from 'lucide-react';
import HelpPanel from './HelpPanel';

export default function Layout() {
  const { user, logout } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Close sidebar on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && sidebarOpen) {
        setSidebarOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [sidebarOpen]);

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
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 z-30">
        <h1 className="text-xl font-bold text-primary">PraxisZeit</h1>
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 rounded-lg hover:bg-gray-100 transition"
          aria-label="Menü öffnen"
        >
          <Menu size={24} />
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
          w-64 bg-white border-r border-gray-200 flex flex-col
          fixed lg:relative inset-y-0 left-0 z-50
          transform transition-transform duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo/Title */}
        <div className="p-6 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">PraxisZeit</h1>
            <p className="text-sm text-gray-500 mt-1">Zeiterfassung</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100 transition"
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
                    ? 'bg-primary text-white'
                    : 'text-gray-700 hover:bg-gray-100'
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
              <div className="my-4 border-t border-gray-200 pt-4">
                <p className="px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
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
        <div className="p-4 border-t border-gray-200">
          <Link to="/profile" className="flex items-center space-x-3 mb-3 hover:bg-gray-50 rounded-lg p-1 -m-1 transition-colors">
            {user?.profile_picture ? (
              <img src={user.profile_picture} className="w-10 h-10 rounded-full object-cover" alt="" />
            ) : (
              <div className="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center font-semibold">
                {user?.first_name?.[0]}
                {user?.last_name?.[0]}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                {user?.first_name} {user?.last_name}
              </p>
              <p className="text-xs text-gray-500 truncate">{user?.username}</p>
            </div>
          </Link>
          {/* Handbuch-Downloads */}
          <div className="mb-2 flex flex-col gap-1">
            <a
              href="/docs/Cheat-Sheet.pdf"
              download
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
            >
              <BookOpen size={13} />
              <span>Cheat-Sheet</span>
            </a>
            <a
              href="/docs/Mitarbeiter-Handbuch.pdf"
              download
              className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
            >
              <FileText size={13} />
              <span>Mitarbeiter-Handbuch</span>
            </a>
            {user?.role === 'admin' && (
              <a
                href="/docs/Admin-Handbuch.pdf"
                download
                className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors"
              >
                <FileText size={13} />
                <span>Admin-Handbuch</span>
              </a>
            )}
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
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden lg:pt-0 pt-16 pb-16 lg:pb-0" tabIndex={-1}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
          <Outlet />
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-gray-200 z-30 flex items-stretch">
        {[
          { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
          { path: '/time-tracking', icon: Clock, label: 'Zeiten' },
          { path: '/absences', icon: Calendar, label: 'Abwesen.' },
          { path: '/profile', icon: User, label: 'Profil' },
          ...(user?.role === 'admin' ? [{ path: '/admin', icon: Settings, label: 'Admin' }] : []),
        ].map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex-1 flex flex-col items-center justify-center space-y-0.5 transition-colors ${
                active ? 'text-primary' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon size={22} strokeWidth={active ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <HelpPanel isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
