import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import { ToastProvider } from './contexts/ToastContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import TimeTracking from './pages/TimeTracking';
import ChangeRequests from './pages/ChangeRequests';
import AbsenceCalendarPage from './pages/AbsenceCalendarPage';
import Profile from './pages/Profile';
import AdminDashboard from './pages/admin/AdminDashboard';
import Users from './pages/admin/Users';
import AdminChangeRequests from './pages/admin/ChangeRequests';
import Reports from './pages/admin/Reports';
import AuditLog from './pages/admin/AuditLog';
import AdminAbsences from './pages/admin/AdminAbsences';
import ErrorMonitoring from './pages/admin/ErrorMonitoring';
import Help from './pages/Help';
import Layout from './components/Layout';

// Protected Route Component
function ProtectedRoute({
  children,
  requiredRole,
}: {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'employee';
}) {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />

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
          <Route path="change-requests" element={<ChangeRequests />} />
          <Route path="absences" element={<AbsenceCalendarPage />} />
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
          <Route path="change-requests" element={<AdminChangeRequests />} />
          <Route path="reports" element={<Reports />} />
          <Route path="audit-log" element={<AuditLog />} />
          <Route path="absences" element={<AdminAbsences />} />
          <Route path="errors" element={<ErrorMonitoring />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
