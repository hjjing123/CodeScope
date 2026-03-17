import React, { useState } from 'react';
import { Button, Typography, Space, Card, Row, Col, theme, Input } from 'antd';
import { 
  SafetyCertificateOutlined, 
  BugOutlined, 
  CodeOutlined, 
  SendOutlined
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface WelcomeScreenProps {
  onNewChat: () => void;
  onStartWithMessage?: (message: string) => void;
}

const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ 
  onStartWithMessage
}) => {
  const { token } = theme.useToken();
  const [inputValue, setInputValue] = useState('');

  const handleSend = () => {
    if (inputValue.trim() && onStartWithMessage) {
      onStartWithMessage(inputValue);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%', 
      background: '#fff',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Background decoration */}
      <div style={{
        position: 'absolute',
        top: -100,
        right: -100,
        width: 400,
        height: 400,
        background: 'radial-gradient(circle, rgba(24,144,255,0.05) 0%, rgba(255,255,255,0) 70%)',
        borderRadius: '50%',
        zIndex: 0
      }} />

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', zIndex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: 900, textAlign: 'center', width: '100%' }}>
          
          {/* Hero Section */}
          <div style={{ marginBottom: 64 }}>
            <div style={{ marginBottom: 24 }}>
              <SafetyCertificateOutlined style={{ fontSize: 72, color: token.colorPrimary }} />
            </div>
            <Title level={2} style={{ marginBottom: 16 }}>
              我们先从哪里开始呢？
            </Title>
            <Paragraph type="secondary" style={{ fontSize: 16, marginBottom: 0, maxWidth: 600, margin: '0 auto' }}>
              利用大语言模型的力量，辅助您进行代码审计、漏洞分析和安全修复建议。
            </Paragraph>
          </div>

          {/* Feature Grid */}
          <div style={{ marginTop: 40 }}>
            <Row gutter={[32, 32]}>
              <Col xs={24} md={8}>
                <Card 
                  hoverable 
                  bordered={false} 
                  style={{ 
                    height: '100%', 
                    textAlign: 'left', 
                    boxShadow: '0 4px 12px rgba(0,0,0,0.03)',
                    background: '#fafafa',
                    cursor: 'default'
                  }}
                >
                  <Space direction="vertical" size={12}>
                    <div style={{ 
                      width: 48, height: 48, borderRadius: 12, 
                      background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)'
                    }}>
                      <BugOutlined style={{ fontSize: 24, color: '#faad14' }} />
                    </div>
                    <Text strong style={{ fontSize: 16 }}>漏洞深度分析</Text>
                    <Text type="secondary">
                      结合上下文深入分析漏洞成因，识别误报，评估真实风险等级。
                    </Text>
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card 
                  hoverable 
                  bordered={false} 
                  style={{ 
                    height: '100%', 
                    textAlign: 'left', 
                    boxShadow: '0 4px 12px rgba(0,0,0,0.03)',
                    background: '#fafafa',
                    cursor: 'default'
                  }}
                >
                  <Space direction="vertical" size={12}>
                    <div style={{ 
                      width: 48, height: 48, borderRadius: 12, 
                      background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)'
                    }}>
                      <CodeOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                    </div>
                    <Text strong style={{ fontSize: 16 }}>代码解释与审计</Text>
                    <Text type="secondary">
                      让 AI 解释复杂的业务逻辑，辅助人工审计，快速定位潜在的安全隐患。
                    </Text>
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card 
                  hoverable 
                  bordered={false} 
                  style={{ 
                    height: '100%', 
                    textAlign: 'left', 
                    boxShadow: '0 4px 12px rgba(0,0,0,0.03)',
                    background: '#fafafa',
                    cursor: 'default'
                  }}
                >
                  <Space direction="vertical" size={12}>
                    <div style={{ 
                      width: 48, height: 48, borderRadius: 12, 
                      background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)'
                    }}>
                      <SafetyCertificateOutlined style={{ fontSize: 24, color: '#eb2f96' }} />
                    </div>
                    <Text strong style={{ fontSize: 16 }}>修复方案建议</Text>
                    <Text type="secondary">
                      提供具体的代码修复示例和安全最佳实践，帮助开发者快速封堵漏洞。
                    </Text>
                  </Space>
                </Card>
              </Col>
            </Row>
          </div>
        </div>
      </div>

      {/* Input Area at the bottom */}
      <div style={{ 
        padding: '0 24px 24px', 
        width: '100%', 
        maxWidth: 800, 
        margin: '0 auto',
        zIndex: 1
      }}>
        <div style={{ position: 'relative' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，Shift + Enter 换行..."
            autoSize={{ minRows: 2, maxRows: 6 }}
            style={{ 
              paddingRight: 50, 
              borderRadius: 16, 
              padding: '16px 50px 16px 16px', 
              fontSize: 16, 
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              border: '1px solid #e8e8e8'
            }}
          />
          <Button 
            type="primary" 
            shape="circle" 
            icon={<SendOutlined />} 
            style={{ position: 'absolute', right: 12, bottom: 12, width: 32, height: 32 }}
            onClick={handleSend}
            disabled={!inputValue.trim()}
          />
        </div>
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            AI 生成的内容可能不准确，请谨慎参考。
          </Text>
        </div>
      </div>
    </div>
  );
};

export default WelcomeScreen;
