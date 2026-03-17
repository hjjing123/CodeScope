import React, { useEffect, useRef, useState } from 'react';
import { Input, Button, List, Avatar, Typography, Spin, Empty } from 'antd';
import { SendOutlined, UserOutlined, RobotOutlined, LoadingOutlined } from '@ant-design/icons';
import type { AIChatMessagePayload } from '../../types/ai';
import dayjs from 'dayjs';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const MESSAGE_GROUP_MAX_WIDTH = '72%';

interface ChatAreaProps {
  messages: AIChatMessagePayload[];
  onSendMessage: (content: string) => Promise<void>;
  loading?: boolean;
  sending?: boolean;
}

const ChatArea: React.FC<ChatAreaProps> = ({ messages, onSendMessage, loading, sending }) => {
  const [inputValue, setInputValue] = useState('');
  const [showStreamingCursor, setShowStreamingCursor] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const showLoadingState = Boolean(loading) && messages.length === 0;
  const hasStreamingAssistantDraft = messages.some((message) => {
    if (message.role !== 'assistant') {
      return false;
    }
    return Boolean(message.meta_json && typeof message.meta_json === 'object' && message.meta_json.streaming);
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending]);

  useEffect(() => {
    if (!hasStreamingAssistantDraft) {
      setShowStreamingCursor(true);
      return;
    }

    const timer = window.setInterval(() => {
      setShowStreamingCursor((prev) => !prev);
    }, 450);

    return () => {
      window.clearInterval(timer);
    };
  }, [hasStreamingAssistantDraft]);

  const handleSend = async () => {
    if (!inputValue.trim() || sending) return;
    const content = inputValue;
    setInputValue('');
    await onSendMessage(content);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {/* Message List Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        {showLoadingState ? (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 40 }}>
            <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          </div>
        ) : messages.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty description="开始一段新的对话吧" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : (
          <List
            dataSource={messages}
            split={false}
            renderItem={(msg) => {
              const isUser = msg.role === 'user';
              const isStreamingAssistant =
                !isUser &&
                Boolean(msg.meta_json && typeof msg.meta_json === 'object' && msg.meta_json.streaming);
              return (
                <List.Item
                  style={{
                    padding: '8px 0',
                    border: 'none',
                    display: 'flex',
                    justifyContent: isUser ? 'flex-end' : 'flex-start',
                    alignItems: 'flex-start',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: isUser ? 'row-reverse' : 'row',
                      alignItems: 'flex-start',
                      gap: 8,
                      maxWidth: MESSAGE_GROUP_MAX_WIDTH,
                    }}
                  >
                    <Avatar
                      icon={isUser ? <UserOutlined /> : <RobotOutlined />}
                      style={{
                        backgroundColor: isUser ? '#1890ff' : '#52c41a',
                        flexShrink: 0,
                      }}
                    />
                    <div
                      style={{
                        minWidth: 0,
                        background: isUser ? '#e6f7ff' : '#f6f6f6',
                        padding: '12px 16px',
                        borderRadius: isUser ? '16px 0 16px 16px' : '0 16px 16px 16px',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                      }}
                    >
                      <div style={{ marginBottom: 4 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {isUser ? '我' : 'AI 助手'} • {dayjs(msg.created_at).format('HH:mm')}
                        </Text>
                      </div>
                      <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                        {msg.content || (isStreamingAssistant ? '正在思考...' : '')}
                        {isStreamingAssistant ? (
                          <span
                            aria-hidden="true"
                            style={{
                              display: 'inline-block',
                              width: 10,
                              marginLeft: 2,
                              opacity: showStreamingCursor ? 1 : 0,
                              transition: 'opacity 0.18s ease',
                            }}
                          >
                            |
                          </span>
                        ) : null}
                      </Paragraph>
                    </div>
                  </div>
                </List.Item>
              );
            }}
          />
        )}
        {sending && !hasStreamingAssistantDraft && (
          <div style={{ display: 'flex', padding: '8px 0', justifyContent: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, maxWidth: MESSAGE_GROUP_MAX_WIDTH }}>
              <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#52c41a', flexShrink: 0 }} />
              <div style={{ background: '#f6f6f6', padding: '12px 16px', borderRadius: '0 16px 16px 16px' }}>
                <Spin size="small" /> <Text type="secondary" style={{ marginLeft: 8 }}>正在思考...</Text>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div style={{ 
        padding: '16px 24px', 
        borderTop: '1px solid #f0f0f0', 
        background: '#fff',
        boxShadow: '0 -2px 10px rgba(0,0,0,0.02)'
      }}>
        <div style={{ position: 'relative' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，Shift + Enter 换行..."
            autoSize={{ minRows: 2, maxRows: 6 }}
            style={{ paddingRight: 50, borderRadius: 8 }}
            disabled={sending}
          />
          <Button 
            type="primary" 
            shape="circle" 
            icon={<SendOutlined />} 
            style={{ position: 'absolute', right: 8, bottom: 8 }}
            onClick={handleSend}
            loading={sending}
            disabled={!inputValue.trim()}
          />
        </div>
        <div style={{ marginTop: 8, textAlign: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            AI 生成的内容可能不准确，请谨慎参考。
          </Text>
        </div>
      </div>
    </div>
  );
};

export default ChatArea;
