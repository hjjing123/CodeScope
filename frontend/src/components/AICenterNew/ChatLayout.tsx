import React, { useState } from 'react';
import { Layout, Button } from 'antd';
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';

const { Sider, Content } = Layout;

interface ChatLayoutProps {
  sidebar?: React.ReactNode;
  header?: React.ReactNode;
  headerExtra?: React.ReactNode;
  children: React.ReactNode;
  contextPanel?: React.ReactNode;
  onSidebarCollapseChange?: (collapsed: boolean) => void;
}

const ChatLayout: React.FC<ChatLayoutProps> = ({
  sidebar,
  header,
  headerExtra,
  children,
  contextPanel,
  onSidebarCollapseChange,
}) => {
  const [collapsed, setCollpased] = useState(false);
  const [siderWidth, setSiderWidth] = useState(300);

  const handleCollapsedChange = (nextCollapsed: boolean) => {
    setCollpased(nextCollapsed);
    onSidebarCollapseChange?.(nextCollapsed);
  };

  return (
    <Layout style={{ height: '100%', overflow: 'hidden', background: '#fff' }}>
      {sidebar && (
        <Sider
          width={siderWidth}
          collapsedWidth={0}
          theme="light"
          collapsible
          collapsed={collapsed}
          onCollapse={handleCollapsedChange}
          trigger={null}
          style={{
            borderRight: collapsed ? 'none' : '1px solid #f0f0f0',
            height: '100%',
            overflowY: 'auto',
            background: '#fafafa',
            position: 'relative'
          }}
        >
          {sidebar}
          {/* Resize Handle */}
          {!collapsed && (
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: 0,
                bottom: 0,
                width: 4,
                cursor: 'col-resize',
                zIndex: 100,
              }}
              onMouseDown={(e) => {
                const startX = e.clientX;
                const startWidth = siderWidth;
                
                const handleMouseMove = (moveEvent: MouseEvent) => {
                  const newWidth = startWidth + (moveEvent.clientX - startX);
                  if (newWidth > 200 && newWidth < 600) {
                    setSiderWidth(newWidth);
                  }
                };
                
                const handleMouseUp = () => {
                  document.removeEventListener('mousemove', handleMouseMove);
                  document.removeEventListener('mouseup', handleMouseUp);
                };
                
                document.addEventListener('mousemove', handleMouseMove);
                document.addEventListener('mouseup', handleMouseUp);
              }}
            />
          )}
        </Sider>
      )}
      <Layout style={{ height: '100%', background: '#fff' }}>
        <Content style={{ height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
          {(header || headerExtra) && (
            <div style={{ 
              height: 56, 
              padding: '0 16px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between',
              borderBottom: '1px solid #f0f0f0',
              zIndex: 10
            }}>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                {sidebar && (
                  <Button
                    type="text"
                    icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                    onClick={() => handleCollapsedChange(!collapsed)}
                    style={{ marginRight: 16 }}
                  />
                )}
                {header}
              </div>
              {headerExtra ? (
                <div style={{ display: 'flex', alignItems: 'center', marginLeft: 16 }}>
                  {headerExtra}
                </div>
              ) : null}
            </div>
          )}
          <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
            {children}
          </div>
        </Content>
        {contextPanel && (
          <Sider
            width={350}
            theme="light"
            style={{
              borderLeft: '1px solid #f0f0f0',
              height: '100%',
              overflowY: 'auto',
              background: '#fff'
            }}
          >
            {contextPanel}
          </Sider>
        )}
      </Layout>
    </Layout>
  );
};

export default ChatLayout;
