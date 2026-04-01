import React, { useMemo, useState } from 'react';
import { Avatar, Button, Drawer, Layout, Menu, Typography } from 'antd';
import type { MenuProps } from 'antd';
import {
  FileSearchOutlined,
  LogoutOutlined,
  MenuOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import type { WorkspaceSection } from '../config/workspaceSections';
import {
  getWorkspaceSectionByKey,
  getWorkspaceSectionByPath,
  workspaceMenuItems,
  workspaceSections,
} from '../config/workspaceSections';
import './WorkspaceLayout.css';

const { Content, Header, Sider } = Layout;
const { Text, Title } = Typography;

const hiddenTaskLogsSection: WorkspaceSection = {
  key: 'task-logs',
  route: 'task-logs',
  path: '/task-logs',
  label: '任务日志',
  tagline: '按任务类型、阶段与任务 ID 查看任务执行日志。',
  badge: 'Task Trace',
  intro: '隐藏入口，仅通过安全概览页中的任务日志摘要进入。',
  icon: FileSearchOutlined,
  highlights: [],
  blocks: [],
  nextAction: '',
};

const WorkspaceBrand: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  return (
    <div className={`workspace-brand${compact ? ' workspace-brand--compact' : ''}`}>
      <div className="workspace-brand-mark">
        <SafetyCertificateOutlined />
      </div>
      <div className="workspace-brand-copy">
        <span className="workspace-brand-name">CodeScope</span>
        <span className="workspace-brand-subtitle">Security Audit Console</span>
      </div>
    </div>
  );
};

const WorkspaceLayout: React.FC = () => {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const activeSection = useMemo(() => {
    if (location.pathname === hiddenTaskLogsSection.path) {
      return hiddenTaskLogsSection;
    }
    return getWorkspaceSectionByPath(location.pathname);
  }, [location.pathname]);

  const activeMenuKey = useMemo(() => activeSection.key, [activeSection.key]);

  const filteredMenuItems = useMemo(() => {
    return workspaceMenuItems?.filter((item) => {
      if (item?.key === 'settings') {
        return false;
      }
      if (item?.key === 'users' && user?.role !== 'Admin') {
        return false;
      }
      if (item?.key === 'log-center' && user?.role !== 'Admin') {
        return false;
      }
      return true;
    });
  }, [user?.role]);

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextSection = getWorkspaceSectionByKey(String(key));
    navigate(nextSection.path);
    setMobileMenuOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const userInitial = (user?.display_name?.trim() || user?.email || 'U')
    .charAt(0)
    .toUpperCase();

  return (
    <Layout className="workspace-layout">
      <Sider width={258} className="workspace-sider" aria-label="主导航栏">
        <WorkspaceBrand />

        <Menu
          mode="inline"
          selectedKeys={[activeMenuKey]}
          items={filteredMenuItems}
          className="workspace-menu"
          onClick={handleMenuClick}
        />
      </Sider>

      <Layout className="workspace-main">
        <Header className="workspace-header" aria-label="页面头部">
          <div className="workspace-header-left">
            <Button
              type="default"
              icon={<MenuOutlined />}
              className="workspace-mobile-trigger"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="打开导航菜单"
            />

            <div className="workspace-heading">
              <Title level={2} className="workspace-title">
                {activeSection.label}
              </Title>
              <Text className="workspace-subtitle">{activeSection.tagline}</Text>
            </div>
          </div>

          <div className="workspace-header-right">
            <div className="workspace-user-chip" aria-label="当前用户信息">
              <Avatar className="workspace-user-avatar">{userInitial}</Avatar>
              <div className="workspace-user-copy">
                <span className="workspace-user-name">
                  {user?.display_name || '未命名用户'}
                </span>
                <span className="workspace-user-meta">{user?.role || '角色未分配'}</span>
              </div>
            </div>

            <Button
              type="default"
              icon={<LogoutOutlined />}
              className="workspace-logout-btn"
              onClick={() => void handleLogout()}
            >
              退出登录
            </Button>
          </div>
        </Header>

        <Content className="workspace-content">
          <Outlet />
        </Content>
      </Layout>

      <Drawer
        placement="left"
        open={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        closable={false}
        width={288}
        className="workspace-nav-drawer"
      >
        <WorkspaceBrand compact />

        <Menu
          mode="inline"
          selectedKeys={[activeMenuKey]}
          items={filteredMenuItems}
          className="workspace-drawer-menu"
          onClick={handleMenuClick}
        />

        <div className="workspace-drawer-footer">
          {workspaceSections.length} 个模块骨架已预置，可按业务优先级逐步填充。
        </div>
      </Drawer>
    </Layout>
  );
};

export default WorkspaceLayout;
