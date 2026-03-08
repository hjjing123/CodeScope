import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAuthStore } from './store/useAuthStore';
import { hasAuthToken } from './utils/authToken';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'dayjs/locale/zh-cn';
import WorkspaceLayout from './layouts/WorkspaceLayout';
import WorkspaceSectionPage from './pages/WorkspaceSectionPage';
import LogCenterPage from './pages/LogCenterPage';
import ProjectVersionPage from './pages/ProjectVersionPage';
import RuleCenterPage from './pages/RuleCenterPage';
import RuleDetailPage from './pages/RuleDetailPage';
import { workspaceSections } from './config/workspaceSections';

// Protected Route Component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated && !hasAuthToken()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

function App() {
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
            <Route path="code-management" element={<ProjectVersionPage />} />
            <Route path="projects" element={<Navigate to="/code-management" replace />} />
            <Route path="log-center" element={<LogCenterPage />} />
            <Route path="rules" element={<RuleCenterPage />} />
            <Route path="rules/:ruleKey" element={<RuleDetailPage />} />
            {workspaceSections
              .filter(
                (section) =>
                  section.key !== 'projects' &&
                  section.key !== 'log-center' &&
                  section.key !== 'rules'
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
