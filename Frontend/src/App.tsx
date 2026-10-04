import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { PageSpinner } from '@/components/ui/Spinner';

// Pages
import { LoginPage }              from '@/pages/auth/LoginPage';
import { RegisterPage }           from '@/pages/auth/RegisterPage';
import { OrganizationSetupPage }  from '@/pages/setup/OrganizationSetupPage';
import { DashboardPage }          from '@/pages/dashboard/DashboardPage';
import { NotFoundPage }           from '@/pages/NotFoundPage';

// ── Route guards ──────────────────────────────────────────────────────────────

/** Redirects unauthenticated users to /login. */
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <PageSpinner />;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

/** Redirects already-authenticated users away from login/register. */
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <PageSpinner />;
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <>{children}</>;
}

// ── App ───────────────────────────────────────────────────────────────────────

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login"    element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />

      {/* Protected routes */}
      <Route path="/setup"     element={<PrivateRoute><OrganizationSetupPage /></PrivateRoute>} />
      <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />

      {/* Redirects */}
      <Route path="/"  element={<Navigate to="/dashboard" replace />} />
      <Route path="*"  element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
