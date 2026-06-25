import { useEffect, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import { useSystemStore } from './stores/systemStore';
import { useTypeColorsStore } from './stores/typeColorsStore';
import { ToastProvider } from './contexts/ToastContext';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Verify from './pages/Verify';
import Dashboard from './pages/Dashboard';
import TimeTracking from './pages/TimeTracking';
import AbsenceCalendarPage from './pages/AbsenceCalendarPage';
import Profile from './pages/Profile';
import Privacy from './pages/Privacy';
// #147: Admin-Routen + Help per Code-Splitting lazy laden -> kleineres
// Initial-Bundle. Der Suspense-Fallback liegt in Layout um den <Outlet />.
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'));
const Users = lazy(() => import('./pages/admin/Users'));
const AdminChangeRequests = lazy(() => import('./pages/admin/ChangeRequests'));
const Reports = lazy(() => import('./pages/admin/Reports'));
const AuditLog = lazy(() => import('./pages/admin/AuditLog'));
const AdminAbsences = lazy(() => import('./pages/admin/AdminAbsences'));
const ErrorMonitoring = lazy(() => import('./pages/admin/ErrorMonitoring'));
const VacationApprovals = lazy(() => import('./pages/admin/VacationApprovals'));
const ImportXls = lazy(() => import('./pages/admin/ImportXls'));
const AdminSettings = lazy(() => import('./pages/admin/Settings'));
const AdminBackups = lazy(() => import('./pages/admin/Backups'));
const AdminBilling = lazy(() => import('./pages/admin/Billing'));
const UserJournal = lazy(() => import('./pages/admin/UserJournal'));
const Help = lazy(() => import('./pages/Help'));
// #305 Schichtplanung — lazy (zieht @dnd-kit nur bei Bedarf ins Bundle)
const ShiftPlanning = lazy(() => import('./pages/ShiftPlanning'));
const AdminShiftPlanning = lazy(() => import('./pages/admin/ShiftPlanning'));
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

/**
 * F-057: Router-aware error boundary wrapper.
 *
 * Without this, a single component crash pins the whole SPA on the
 * "Etwas ist schiefgelaufen" screen until the user manually reloads,
 * because the class-based ErrorBoundary has no way to clear its own
 * state on route change. Passing a pathname-derived `key` forces React
 * to unmount and remount the boundary whenever the route changes,
 * resetting `hasError` for free.
 */
function RouterAwareErrorBoundary({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>;
}

// Protected Route Component
function ProtectedRoute({
  children,
  requiredRole,
}: {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'employee';
}) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function App() {
  // F-023: silently try to restore the session from the HttpOnly refresh
  // cookie on first mount. Until hydrate() resolves, render a minimal
  // loading state so ProtectedRoute doesn't bounce to /login prematurely.
  const hydrate = useAuthStore((s) => s.hydrate);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const fetchSystem = useSystemStore((s) => s.fetch);
  // #157: per-tenant type colours need an authenticated request, so fetch them
  // whenever a user is present (and re-fetch if the user changes).
  const fetchTypeColors = useTypeColorsStore((s) => s.fetch);
  const userId = useAuthStore((s) => s.user?.id);

  useEffect(() => {
    void hydrate();
    void fetchSystem();
  }, [hydrate, fetchSystem]);

  useEffect(() => {
    if (userId) void fetchTypeColors();
  }, [userId, fetchTypeColors]);

  if (isHydrating) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center justify-center min-h-screen bg-gray-50 text-gray-500"
      >
        Lade Sitzung…
      </div>
    );
  }

  return (
    <ToastProvider>
      <BrowserRouter>
        <RouterAwareErrorBoundary>
          <Routes>
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/privacy" element={<Privacy />} />

        {/* Protected Employee Routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="time-tracking" element={<TimeTracking />} />
          <Route path="change-requests" element={<Navigate to="/time-tracking?tab=requests" replace />} />
          <Route path="absences" element={<AbsenceCalendarPage />} />
          <Route path="shift-planning" element={<ShiftPlanning />} />
          <Route path="journal" element={<Navigate to="/time-tracking?tab=journal" replace />} />
          <Route path="profile" element={<Profile />} />
          <Route path="help" element={<Help />} />
        </Route>

        {/* Protected Admin Routes */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute requiredRole="admin">
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<AdminDashboard />} />
          <Route path="users" element={<Users />} />
          <Route path="users/:userId/journal" element={<UserJournal />} />
          <Route path="change-requests" element={<AdminChangeRequests />} />
          <Route path="reports" element={<Reports />} />
          <Route path="audit-log" element={<AuditLog />} />
          <Route path="absences" element={<AdminAbsences />} />
          <Route path="errors" element={<ErrorMonitoring />} />
          <Route path="vacation-approvals" element={<VacationApprovals />} />
          <Route path="import" element={<ImportXls />} />
          <Route path="settings" element={<AdminSettings />} />
          <Route path="backups" element={<AdminBackups />} />
          <Route path="shift-planning" element={<AdminShiftPlanning />} />
          <Route path="billing" element={<AdminBilling />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </RouterAwareErrorBoundary>
    </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
