import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import {
  UserOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  CheckCircleFilled,
  ArrowRightOutlined,
  UserAddOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { login, getMe } from '../services/auth';
import type { LoginRequest } from '../types/auth';
import { clearAuthSession, setAuthSession } from '../utils/authToken';
import './Login.css';

const { Title, Text } = Typography;
const securityHighlights = [
  '统一权限管控与审计日志可追溯',
  '漏洞结果支持分级、归档与复核',
  '扫描流程可编排，支持多项目并行',
];
const trustBadges = ['ISO 27001 对齐', '最小权限原则', '全链路可追踪'];

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login: setAuth } = useAuthStore();

  const onFinish = async (values: LoginRequest) => {
    setLoading(true);
    try {
      const { data: tokenData } = await login(values);
      setAuthSession(tokenData);

      const { data: userData } = await getMe();

      setAuth(tokenData, userData);
      message.success('登录成功');
      navigate('/dashboard');
    } catch (error: any) {
      clearAuthSession();
      console.error('Login failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-shell">
        <section className="login-intro" aria-label="平台介绍">
          <div className="login-brand">
            <SafetyCertificateOutlined className="login-brand-icon" />
            <span className="login-brand-text">CodeScope</span>
          </div>
          <Title level={1} className="login-title">
            代码安全审计平台
          </Title>
          <Text className="login-subtitle">
            面向研发与安全团队的统一工作台，覆盖导入、扫描、研判与审计闭环。
          </Text>

          <div className="login-badge-row" aria-label="平台能力标签">
            {trustBadges.map((badge) => (
              <span className="login-badge" key={badge}>
                {badge}
              </span>
            ))}
          </div>

          <ul className="login-highlight-list">
            {securityHighlights.map((item) => (
              <li key={item} className="login-highlight-item">
                <CheckCircleFilled className="login-highlight-icon" />
                <span>{item}</span>
              </li>
            ))}
          </ul>

          <div className="login-metric-grid" aria-label="平台指标">
            <div className="login-metric-card">
              <p className="login-metric-value">24/7</p>
              <p className="login-metric-label">持续监测</p>
            </div>
            <div className="login-metric-card">
              <p className="login-metric-value">RBAC</p>
              <p className="login-metric-label">细粒度授权</p>
            </div>
            <div className="login-metric-card">
              <p className="login-metric-value">Audit</p>
              <p className="login-metric-label">全链路留痕</p>
            </div>
          </div>
        </section>

        <Card bordered={false} className="login-card">
          <div className="login-card-header">
            <Title level={3} className="login-card-title">
              账户登录
            </Title>
          </div>

          <Form
            name="login"
            onFinish={onFinish}
            layout="vertical"
            size="large"
            requiredMark={false}
            className="login-form"
          >
            <Form.Item
              label="账号"
              name="email"
              rules={[{ required: true, message: '请输入账号!' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="请输入邮箱" autoComplete="username" />
            </Form.Item>

            <Form.Item
              className="login-password-wrap"
              label="密码"
              name="password"
              rules={[{ required: true, message: '请输入密码!' }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="请输入密码"
                autoComplete="current-password"
              />
            </Form.Item>

            <Form.Item className="login-submit-wrap">
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={loading}
                className="login-submit-btn"
                icon={<ArrowRightOutlined />}
              >
                登录系统
              </Button>
            </Form.Item>

            <Form.Item className="login-register-wrap">
              <Button
                type="default"
                block
                className="login-register-btn"
                icon={<UserAddOutlined />}
                onClick={() => navigate('/register')}
              >
                注册新账号
              </Button>
            </Form.Item>

          </Form>
        </Card>
      </div>
    </div>
  );
};

export default Login;
