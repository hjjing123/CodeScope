import React from 'react';
import { Button, List, Typography, Avatar, Popconfirm } from 'antd';
import { PlusOutlined, MessageOutlined, BugOutlined, DeleteOutlined } from '@ant-design/icons';
import type { AIChatSessionPayload } from '../../types/ai';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { Text } = Typography;

interface SessionSidebarProps {
  sessions: AIChatSessionPayload[];
  currentSessionId?: string;
  onSelectSession: (session: AIChatSessionPayload) => void;
  onNewChat: () => void;
  onDeleteSession: (session: AIChatSessionPayload) => Promise<void> | void;
  loading?: boolean;
  deletingSessionId?: string | null;
}

const SessionSidebar: React.FC<SessionSidebarProps> = ({
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  loading,
  deletingSessionId,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
        <Button 
          type="primary" 
          block 
          icon={<PlusOutlined />} 
          onClick={onNewChat}
          size="large"
          style={{ marginBottom: 12 }}
        >
          新建会话
        </Button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>近期会话</Text>
        </div>
      </div>
      
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <List
          loading={loading}
          dataSource={sessions}
          renderItem={(item) => {
            const isActive = item.id === currentSessionId;
            return (
              <div
                key={item.id}
                onClick={() => onSelectSession(item)}
                style={{
                  padding: '12px 16px',
                  cursor: 'pointer',
                  background: isActive ? '#e6f7ff' : 'transparent',
                  borderLeft: isActive ? '3px solid #1890ff' : '3px solid transparent',
                  transition: 'all 0.2s',
                }}
                className="session-item-hover"
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <Avatar 
                    shape="square" 
                    size="small" 
                    icon={item.finding_id ? <BugOutlined /> : <MessageOutlined />} 
                    style={{ backgroundColor: item.finding_id ? '#ff4d4f' : '#1890ff', marginTop: 4 }}
                  />
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
                      <Text strong ellipsis style={{ maxWidth: 140 }}>
                        {item.title || '未命名会话'}
                      </Text>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                        <Text type="secondary" style={{ fontSize: 10, minWidth: 50, textAlign: 'right' }}>
                          {dayjs(item.created_at).fromNow(true)}
                        </Text>
                        <Popconfirm
                          title="确定删除此会话?"
                          description="删除后当前会话消息将一并移除。"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => onDeleteSession(item)}
                        >
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            aria-label={`删除会话 ${item.title || item.id}`}
                            loading={deletingSessionId === item.id}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </Popconfirm>
                      </div>
                    </div>
                    <Text type="secondary" ellipsis style={{ fontSize: 12, display: 'block' }}>
                      {item.finding_id ? `Finding: ${item.finding_id.slice(0, 8)}...` : '自由对话'}
                    </Text>
                  </div>
                </div>
              </div>
            );
          }}
        />
        {!loading && sessions.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <Text type="secondary">暂无会话历史</Text>
          </div>
        )}
      </div>
    </div>
  );
};

export default SessionSidebar;
