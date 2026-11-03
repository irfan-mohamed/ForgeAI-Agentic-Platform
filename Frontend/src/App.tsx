import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { PageSpinner } from '@/components/ui/Spinner';

// Pages
import { LandingPage } from '@/pages/landing/LandingPage';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { OrganizationSetupPage } from '@/pages/setup/OrganizationSetupPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { RepositoriesPage } from '@/pages/repositories/RepositoriesPage';
import { GitHubCallbackPage } from '@/pages/github/GitHubCallbackPage';
import { AIWorkspacePage } from '@/pages/ai/AIWorkspacePage';
import { CodeReviewsPage } from '@/pages/reviews/CodeReviewsPage';
import { CodeReviewDetailPage } from '@/pages/reviews/CodeReviewDetailPage';
import { TestAssistancePage } from '@/pages/tests/TestAssistancePage';
import { FeaturePlansPage } from '@/pages/plans/FeaturePlansPage';
import { MembersPage } from '@/pages/members/MembersPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

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

// ── App Routes ────────────────────────────────────────────────────────────────

function AppRoutes() {
  return (
    <Routes>
      {/* Public Landing & Auth */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />

      {/* Organization Setup & Dashboard */}
      <Route path="/setup" element={<PrivateRoute><OrganizationSetupPage /></PrivateRoute>} />
      <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />

      {/* Organization-Scoped Platform Workspaces */}
      <Route
        path="/organizations/:orgId/repositories"
        element={<PrivateRoute><RepositoriesPage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/ai"
        element={<PrivateRoute><AIWorkspacePage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/reviews"
        element={<PrivateRoute><CodeReviewsPage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/reviews/:reviewId"
        element={<PrivateRoute><CodeReviewDetailPage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/tests"
        element={<PrivateRoute><TestAssistancePage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/plans"
        element={<PrivateRoute><FeaturePlansPage /></PrivateRoute>}
      />
      <Route
        path="/organizations/:orgId/members"
        element={<PrivateRoute><MembersPage /></PrivateRoute>}
      />

      {/* GitHub callback */}
      <Route path="/github/callback" element={<GitHubCallbackPage />} />

      {/* Fallback 404 */}
      <Route path="*" element={<NotFoundPage />} />
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
