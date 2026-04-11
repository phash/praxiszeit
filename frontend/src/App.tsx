import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import { ToastProvider } from './contexts/ToastContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import TimeTracking from './pages/TimeTracking';
import AbsenceCalendarPage from './pages/AbsenceCalendarPage';
import Profile from './pages/Profile';
import AdminDashboard from './pages/admin/AdminDashboard';
import Users from './pages/admin/Users';
import AdminChangeRequests from './pages/admin/ChangeRequests';
import Reports from './pages/admin/Reports';
import AuditLog from './pages/admin/AuditLog';
import AdminAbsences from './pages/admin/AdminAbsences';
import ErrorMonitoring from './pages/admin/ErrorMonitoring';
import VacationApprovals from './pages/admin/VacationApprovals';
import ImportXls from './pages/admin/ImportXls';
import AdminSettings from './pages/admin/Settings';
import UserJournal from './pages/admin/UserJournal';
import Help from './pages/Help';
import Privacy from './pages/Privacy';
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

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

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
