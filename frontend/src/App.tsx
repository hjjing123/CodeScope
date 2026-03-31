import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAuthStore } from './store/useAuthStore';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'dayjs/locale/zh-cn';
import WorkspaceLayout from './layouts/WorkspaceLayout';
import WorkspaceSectionPage from './pages/WorkspaceSectionPage';
import LogCenterPage from './pages/LogCenterPage';
import RuleCenterPage from './pages/RuleCenterPage';
import RuleDetailPage from './pages/RuleDetailPage';
import { workspaceSections } from './config/workspaceSections';

const CodeManagementPage = lazy(() => import('./pages/CodeManagementPage'));
const ScanTasksPage = lazy(() => import('./pages/ScanTasksPage'));
const FindingsPage = lazy(() => import('./pages/FindingsPage'));
const AICenterPage = lazy(() => import('./pages/AICenterPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const UserManagementPage = lazy(() => import('./pages/UserManagementPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));

const RouteFallback = () => (
  <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
    <Spin size="large" />
  </div>
);

// Protected Route Component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isAuthReady } = useAuthStore();
  if (!isAuthReady) {
    return <RouteFallback />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

// Admin Route Component
const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isAuthReady } = useAuthStore();
  if (!isAuthReady) {
    return <RouteFallback />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (!user) {
    return <RouteFallback />;
  }
  if (user?.role !== 'Admin') {
    return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
};

function App() {
  const initializeAuth = useAuthStore((state) => state.initializeAuth);

  useEffect(() => {
    void initializeAuth();
  }, [initializeAuth]);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1d4ed8',
          colorInfo: '#1e40af',
          colorSuccess: '#0369a1',
          colorWarning: '#b45309',
          borderRadius: 6,
          colorText: '#0f172a',
          colorTextSecondary: '#475569',
          colorBgLayout: '#f8fafc',
          colorBorder: '#dbe3ee',
          fontFamily: "'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <WorkspaceLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route
              path="dashboard"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <DashboardPage />
                </Suspense>
              }
            />
            <Route
              path="code-management"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CodeManagementPage />
                </Suspense>
              }
            />
            <Route
              path="scans"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <ScanTasksPage />
                </Suspense>
              }
            />
            <Route path="projects" element={<Navigate to="/code-management" replace />} />
            <Route path="log-center" element={<LogCenterPage />} />
            <Route path="rules" element={<RuleCenterPage />} />
            <Route path="rules/:ruleKey" element={<RuleDetailPage />} />
            <Route
              path="findings"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <FindingsPage />
                </Suspense>
              }
            />
            <Route
              path="ai-center"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <AICenterPage />
                </Suspense>
              }
            />
            <Route
              path="reports"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <ReportsPage />
                </Suspense>
              }
            />
            <Route
              path="users"
              element={
                <AdminRoute>
                  <Suspense fallback={<RouteFallback />}>
                    <UserManagementPage />
                  </Suspense>
                </AdminRoute>
              }
            />
            {workspaceSections
              .filter(
                (section) =>
                  section.key !== 'dashboard' &&
                  section.key !== 'projects' &&
                  section.key !== 'scans' &&
                  section.key !== 'log-center' &&
                  section.key !== 'rules' &&
                  section.key !== 'findings' &&
                  section.key !== 'ai-center' &&
                  section.key !== 'reports' &&
                  section.key !== 'users'
              )
              .map((section) => (
                <Route
                  key={section.key}
                  path={section.route}
                  element={<WorkspaceSectionPage />}
                />
              ))}
            <Route path="*" element={<Navigate to="dashboard" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
