import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useSearchParams } from 'react-router-dom';
import { Button, Dropdown, message, Spin } from 'antd';
import type { MenuProps } from 'antd';
import { CloudServerOutlined, MenuUnfoldOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons';
import ChatLayout from '../components/AICenterNew/ChatLayout';
import SessionSidebar from '../components/AICenterNew/SessionSidebar';
import ModelSelector from '../components/AICenterNew/ModelSelector';
import { 
  listMyChatSessions, 
  createGeneralChatSession,
  createChatSession, 
  deleteChatSession,
  getChatSession, 
  sendChatMessageStream,
  updateChatSessionSelection
} from '../services/ai';
import { FindingService } from '../services/findings';
import type { AIChatSessionPayload, AIChatMessagePayload, AIProviderSelectionRequest } from '../types/ai';
import type { Finding } from '../types/finding';

// Lazy load components
const ChatArea = React.lazy(() => import('../components/AICenterNew/ChatArea'));
const FindingContextPanel = React.lazy(() => import('../components/AICenterNew/FindingContextPanel'));
const OllamaConfigPanel = React.lazy(() => import('../components/AICenterNew/OllamaConfigPanel'));
const UserProviderConfigPanel = React.lazy(() => import('../components/AICenterNew/UserProviderConfigPanel'));
const WelcomeScreen = React.lazy(() => import('../components/AICenterNew/WelcomeScreen'));

const CHAT_SEND_TIMEOUT_MESSAGE = 'AI 响应较慢，请稍候，避免重复发送。';

const getChatSendErrorMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const backendMessage = error.response?.data?.error?.message || error.response?.data?.message;
    if (typeof backendMessage === 'string' && backendMessage.trim()) {
      return backendMessage;
    }
    if (error.code === 'ECONNABORTED') {
      return CHAT_SEND_TIMEOUT_MESSAGE;
    }
    if (!error.response) {
      return '网络波动，请稍后查看会话结果。';
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return '发送失败';
};

const AICenterPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  
  // State
  const [viewMode, setViewMode] = useState<'chat' | 'config' | 'user_config'>('chat');
  const [sessions, setSessions] = useState<AIChatSessionPayload[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(searchParams.get('session_id'));
  const [messages, setMessages] = useState<AIChatMessagePayload[]>([]);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [modelSelection, setModelSelection] = useState<AIProviderSelectionRequest>({});
  
  // UI State
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [loadingFinding, setLoadingFinding] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [forceLayout, setForceLayout] = useState(false);
  const pendingInitialMessageRef = useRef<{
    sessionId: string;
    message: AIChatMessagePayload;
  } | null>(null);

  // Initial Data Fetch
  const refreshSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const res = await listMyChatSessions();
      setSessions(res.items);
    } catch (error) {
      message.error('加载会话列表失败');
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // Load Session Details
  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      setFinding(null);
      pendingInitialMessageRef.current = null;
      return;
    }

    const loadSession = async () => {
      setLoadingChat(true);
      try {
        const session = await getChatSession(currentSessionId);
        const sessionMessages = session.messages ?? [];
        const pendingInitialMessage = pendingInitialMessageRef.current;
        if (
          pendingInitialMessage?.sessionId === currentSessionId &&
          sessionMessages.length === 0
        ) {
          setMessages((prev) => {
            const hasPendingMessage = prev.some(
              (item) => item.id === pendingInitialMessage.message.id
            );
            return hasPendingMessage ? prev : [pendingInitialMessage.message];
          });
        } else {
          setMessages((prev) => {
            const belongsToCurrentSession =
              prev.length > 0 && prev.every((item) => item.session_id === currentSessionId);
            if (belongsToCurrentSession && prev.length > sessionMessages.length) {
              return prev;
            }
            return sessionMessages;
          });
          if (
            pendingInitialMessage?.sessionId === currentSessionId &&
            sessionMessages.length > 0
          ) {
            pendingInitialMessageRef.current = null;
          }
        }
        
        // Update model selection from session
        setModelSelection({
          ai_source: session.provider_source as any,
          ai_provider_id: undefined, // Session doesn't store provider ID directly but it's part of snapshot
          ai_model: session.model_name,
        });

        if (session.finding_id) {
          setLoadingFinding(true);
          try {
            const f = await FindingService.getFinding(session.finding_id);
            setFinding(f);
          } catch (e) {
            console.error(e);
          } finally {
            setLoadingFinding(false);
          }
        } else {
          setFinding(null);
        }
      } catch (error) {
        message.error('加载会话详情失败');
        pendingInitialMessageRef.current = null;
        setCurrentSessionId(null);
      } finally {
        setLoadingChat(false);
      }
    };

    loadSession();
  }, [currentSessionId]);

  // Handle URL params
  useEffect(() => {
    const sid = searchParams.get('session_id');
    if (sid && sid !== currentSessionId) {
      setCurrentSessionId(sid);
    }
    // Handle finding_id to create new chat? 
    // If finding_id is present and no session_id, maybe prompt to create or find existing?
    // For now, let's just respect session_id.
  }, [searchParams]);

  const handleSelectSession = (session: AIChatSessionPayload) => {
    setViewMode('chat');
    setCurrentSessionId(session.id);
    setSearchParams({ session_id: session.id });
  };

  const handleNewChat = async () => {
    const findingId = searchParams.get('finding_id');
    try {
      let session: AIChatSessionPayload;

      if (findingId) {
        session = await createChatSession(findingId, { title: '新的漏洞分析会话' });
      } else {
        session = await createGeneralChatSession({ title: '新的 AI 对话' });
      }

      message.success('已创建新会话');
      await refreshSessions();
      setViewMode('chat');
      setCurrentSessionId(session.id);
      if (session.finding_id) {
        setSearchParams({ session_id: session.id, finding_id: session.finding_id });
      } else {
        setSearchParams({ session_id: session.id });
      }
    } catch (error) {
      message.error('创建会话失败，请先确认可用模型或 AI Provider 配置');
    }
  };

  const buildTempChatMessage = ({
    sessionId,
    role,
    content,
    meta = {},
  }: {
    sessionId: string;
    role: AIChatMessagePayload['role'];
    content: string;
    meta?: Record<string, unknown>;
  }): AIChatMessagePayload => ({
    id: `temp-${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    created_at: new Date().toISOString(),
    session_id: sessionId,
    meta_json: meta,
  });

  const streamChatMessage = async (
    sessionId: string,
    content: string,
    tempUserMessageId: string
  ) => {
    const controller = new AbortController();
    const assistantDraftId = `temp-assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let streamErrorMessage: string | null = null;

    setSending(true);

    try {
      await sendChatMessageStream(sessionId, { content }, {
        signal: controller.signal,
        onEvent: (event) => {
          if (event.event === 'user_message') {
            const persistedUserMessage = event.data as AIChatMessagePayload;
            setMessages((prev) => {
              const targetIndex = prev.findIndex((item) => item.id === tempUserMessageId);
              if (targetIndex < 0) {
                return prev.some((item) => item.id === persistedUserMessage.id)
                  ? prev
                  : [...prev, persistedUserMessage];
              }
              const next = [...prev];
              next[targetIndex] = persistedUserMessage;
              return next;
            });
            if (pendingInitialMessageRef.current?.sessionId === sessionId) {
              pendingInitialMessageRef.current = {
                sessionId,
                message: persistedUserMessage,
              };
            }
            return;
          }

          if (event.event === 'assistant_delta') {
            const delta =
              event.data && typeof event.data === 'object' && 'delta' in event.data
                ? event.data.delta
                : '';
            if (typeof delta !== 'string' || !delta) {
              return;
            }
            setMessages((prev) => {
              const draftIndex = prev.findIndex((item) => item.id === assistantDraftId);
              if (draftIndex < 0) {
                return [
                  ...prev,
                  {
                    ...buildTempChatMessage({
                      sessionId,
                      role: 'assistant',
                      content: delta,
                      meta: { streaming: true },
                    }),
                    id: assistantDraftId,
                  },
                ];
              }
              const next = [...prev];
              next[draftIndex] = {
                ...next[draftIndex],
                content: `${next[draftIndex].content}${delta}`,
                meta_json: {
                  ...next[draftIndex].meta_json,
                  streaming: true,
                },
              };
              return next;
            });
            return;
          }

          if (event.event === 'assistant_message') {
            const persistedAssistantMessage = event.data as AIChatMessagePayload;
            setMessages((prev) => {
              const draftIndex = prev.findIndex((item) => item.id === assistantDraftId);
              if (draftIndex < 0) {
                return prev.some((item) => item.id === persistedAssistantMessage.id)
                  ? prev
                  : [...prev, persistedAssistantMessage];
              }
              const next = [...prev];
              next[draftIndex] = persistedAssistantMessage;
              return next;
            });
            if (pendingInitialMessageRef.current?.sessionId === sessionId) {
              pendingInitialMessageRef.current = null;
            }
            return;
          }

          if (event.event === 'error') {
            const payload = event.data as Record<string, unknown>;
            streamErrorMessage =
              typeof payload?.message === 'string' && payload.message.trim()
                ? payload.message
                : '发送失败';
          }
        },
      });

      if (streamErrorMessage) {
        throw new Error(streamErrorMessage);
      }
      await refreshSessions();
    } catch (error) {
      setMessages((prev) => {
        const draftIndex = prev.findIndex((item) => item.id === assistantDraftId);
        if (draftIndex < 0) {
          return prev;
        }
        if (prev[draftIndex].content.trim()) {
          const next = [...prev];
          next[draftIndex] = {
            ...next[draftIndex],
            meta_json: {
              ...next[draftIndex].meta_json,
              streaming: false,
              stream_error: true,
            },
          };
          return next;
        }
        return prev.filter((item) => item.id !== assistantDraftId);
      });
      if (pendingInitialMessageRef.current?.sessionId === sessionId) {
        pendingInitialMessageRef.current = null;
      }
      message.error(getChatSendErrorMessage(error));
    } finally {
      controller.abort();
      setSending(false);
    }
  };

  const handleStartSessionWithMessage = async (content: string) => {
    const findingId = searchParams.get('finding_id');
    try {
      let session: AIChatSessionPayload;
      const title = content.length > 20 ? content.substring(0, 20) + '...' : content;
      
      const payload = {
        title,
        ...modelSelection
      };

      if (findingId) {
        session = await createChatSession(findingId, payload);
      } else {
        session = await createGeneralChatSession(payload);
      }

      await refreshSessions();
      setViewMode('chat');
      setCurrentSessionId(session.id);
      if (session.finding_id) {
        setSearchParams({ session_id: session.id, finding_id: session.finding_id });
      } else {
        setSearchParams({ session_id: session.id });
      }

      const tempMsg = buildTempChatMessage({
        sessionId: session.id,
        role: 'user',
        content,
      });
      pendingInitialMessageRef.current = {
        sessionId: session.id,
        message: tempMsg,
      };
      setMessages([tempMsg]);
      await streamChatMessage(session.id, content, tempMsg.id);
    } catch (error) {
      message.error('创建会话失败，请先确认可用模型或 AI Provider 配置');
    }
  };

  const handleSendMessage = async (content: string) => {
    if (!currentSessionId) return;
    
    const tempMsg = buildTempChatMessage({
      sessionId: currentSessionId,
      role: 'user',
      content,
    });
    setMessages(prev => [...prev, tempMsg]);
    await streamChatMessage(currentSessionId, content, tempMsg.id);
  };

  const handleDeleteSession = async (session: AIChatSessionPayload) => {
    try {
      setDeletingSessionId(session.id);
      await deleteChatSession(session.id);

      if (currentSessionId === session.id) {
        setCurrentSessionId(null);
        setMessages([]);
        setFinding(null);

        const nextParams = new URLSearchParams(searchParams);
        nextParams.delete('session_id');
        if (session.finding_id) {
          nextParams.set('finding_id', session.finding_id);
        }
        setSearchParams(nextParams);
      }

      await refreshSessions();
      message.success('会话已删除');
    } catch (error) {
      message.error('删除会话失败');
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleViewConfig = () => {
    setViewMode('config');
  };

  const handleViewUserConfig = () => {
    setViewMode('user_config');
  };

  const aiSettingsMenu: MenuProps['items'] = [
    {
      key: 'user-config',
      label: '个人模型配置',
      icon: <UserOutlined />,
      onClick: handleViewUserConfig,
    },
    {
      key: 'system-ollama',
      label: '系统 Ollama 配置',
      icon: <CloudServerOutlined />,
      onClick: handleViewConfig,
    },
  ];

  const aiSettingsControl = viewMode === 'chat' ? (
    <Dropdown menu={{ items: aiSettingsMenu }} placement="bottomRight" trigger={['click']}>
      <Button type="text" icon={<SettingOutlined />} style={{ height: 36, paddingInline: 12 }}>
        AI 设置
      </Button>
    </Dropdown>
  ) : undefined;

  const handleSidebarCollapseChange = (collapsed: boolean) => {
    if (viewMode !== 'chat') {
      return;
    }
    if (!currentSessionId && sessions.length === 0) {
      setForceLayout(!collapsed);
    }
  };

  const handleModelChange = async (value: AIProviderSelectionRequest) => {
    // If the new value is effectively empty or same as current, ignore
    if (!value || !value.ai_model) return;
    
    // Check if this is an initialization (current state was empty)
    // If we have a currentSessionId, it means we are loading or have loaded a session.
    // In that case, we should NOT let the default selection overwrite the session's model.
    const isInit = !modelSelection.ai_model;
    
    setModelSelection(value);
    
    // If we have an active session, update it immediately
    if (currentSessionId) {
      // If we are just initializing (empty -> value), DO NOT update the session.
      // The session has its own model, which will be loaded via loadSession().
      if (isInit) return;

      try {
        await updateChatSessionSelection(currentSessionId, value);
        message.success(`已切换模型为 ${value.ai_model}`);
      } catch (error) {
        message.error('切换模型失败');
        // Revert selection? Or just let it stay as per UI state?
        // Ideally reload session details to sync back
      }
    }
  };

  const showWelcome = !forceLayout && !currentSessionId && viewMode === 'chat' && sessions.length === 0;

  if (showWelcome) {
    return (
      <div style={{ height: 'calc(100vh - 168px)', minHeight: 640, position: 'relative' }}>
        <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}><Spin /></div>}>
          <div style={{ position: 'absolute', top: 16, left: 24, right: 24, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={() => setForceLayout(true)}
                aria-label="展开历史会话"
              />
              <ModelSelector value={modelSelection} onChange={handleModelChange} />
            </div>
            {aiSettingsControl}
          </div>
          <WelcomeScreen 
            onNewChat={handleNewChat} 
            onStartWithMessage={handleStartSessionWithMessage}
          />
        </Suspense>
      </div>
    );
  }
  
  return (
    <div style={{ height: 'calc(100vh - 168px)', minHeight: 640 }}>
      <ChatLayout
        header={
          viewMode === 'chat' ? (
            <ModelSelector value={modelSelection} onChange={handleModelChange} />
          ) : undefined
        }
        headerExtra={aiSettingsControl}
        onSidebarCollapseChange={handleSidebarCollapseChange}
        sidebar={
          viewMode === 'chat' ? (
            <SessionSidebar 
              sessions={sessions}
              currentSessionId={currentSessionId || undefined}
              onSelectSession={handleSelectSession}
              onNewChat={handleNewChat}
              loading={loadingSessions}
              onDeleteSession={handleDeleteSession}
              deletingSessionId={deletingSessionId}
            />
          ) : undefined
        }
        contextPanel={viewMode === 'chat' && finding ? (
          <Suspense fallback={<Spin />}>
            <FindingContextPanel finding={finding} loading={loadingFinding} />
          </Suspense>
        ) : undefined}
      >
        {viewMode === 'config' ? (
          <Suspense fallback={<div style={{ padding: 50, textAlign: 'center' }}><Spin /></div>}>
            <OllamaConfigPanel onBack={() => setViewMode('chat')} />
          </Suspense>
        ) : viewMode === 'user_config' ? (
          <Suspense fallback={<div style={{ padding: 50, textAlign: 'center' }}><Spin /></div>}>
            <UserProviderConfigPanel onBack={() => setViewMode('chat')} />
          </Suspense>
        ) : currentSessionId ? (
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', padding: 50 }}><Spin /></div>}>
            <ChatArea 
              messages={messages}
              onSendMessage={handleSendMessage}
              loading={loadingChat}
              sending={sending}
            />
          </Suspense>
        ) : (
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', padding: 50 }}><Spin /></div>}>
            <WelcomeScreen 
              onNewChat={handleNewChat} 
              onStartWithMessage={handleStartSessionWithMessage}
            />
          </Suspense>
        )}

      </ChatLayout>
    </div>
  );
};

export default AICenterPage;
