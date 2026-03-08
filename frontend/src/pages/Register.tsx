import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import {
  SafetyCertificateOutlined,
  UserAddOutlined,
  UserOutlined,
  MailOutlined,
  LockOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { register } from '../services/auth';
import type { RegisterRequest } from '../types/auth';
import './Register.css';

const { Title, Text } = Typography;

interface RegisterFormValues extends RegisterRequest {
  confirmPassword: string;
}

const Register: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const onFinish = async (values: RegisterFormValues) => {
    setLoading(true);
    try {
      await register({
        email: values.email,
        password: values.password,
        display_name: values.display_name.trim(),
      });
      message.success('注册成功，请使用新账号登录');
      navigate('/login');
    } catch (error: any) {
      console.error('Register failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="register-page">
      <div className="register-shell">
        <section className="register-intro" aria-label="注册说明">
          <div className="register-brand">
            <SafetyCertificateOutlined className="register-brand-icon" />
            <span className="register-brand-text">CodeScope</span>
          </div>
          <Title level={1} className="register-title">
            创建平台账号
          </Title>
          <Text className="register-subtitle">
            注册后即可进入代码安全审计平台，使用普通用户权限管理项目、规则和扫描任务。
          </Text>

          <div className="register-cue-grid" aria-label="注册要点">
            <div className="register-cue-item">
              <span className="register-cue-key">Step 01</span>
              <span className="register-cue-value">填写身份信息</span>
            </div>
            <div className="register-cue-item">
              <span className="register-cue-key">Step 02</span>
                <span className="register-cue-value">设置并确认登录密码</span>
            </div>
            <div className="register-cue-item">
              <span className="register-cue-key">Step 03</span>
              <span className="register-cue-value">登录平台开始审计</span>
            </div>
          </div>
        </section>

        <Card bordered={false} className="register-card">
          <div className="register-card-header">
            <Title level={3} className="register-card-title">
              新用户注册
            </Title>
            <Text className="register-card-desc">完成以下信息后即可创建账号</Text>
          </div>

          <Form<RegisterFormValues>
            name="register"
            layout="vertical"
            requiredMark={false}
            onFinish={onFinish}
            className="register-form"
            size="large"
          >
            <Form.Item
              label="显示名称"
              name="display_name"
              rules={[
                { required: true, message: '请输入显示名称!' },
                { min: 2, message: '显示名称至少 2 个字符' },
                { max: 50, message: '显示名称不超过 50 个字符' },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="例如：张三 / Security Team" />
            </Form.Item>

            <Form.Item
              label="邮箱"
              name="email"
              rules={[
                { required: true, message: '请输入邮箱!' },
                { type: 'email', message: '请输入有效的邮箱地址!' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="name@example.com" autoComplete="email" />
            </Form.Item>

            <Form.Item
              label="密码"
              name="password"
              rules={[
                { required: true, message: '请输入密码!' },
                { min: 8, message: '密码至少 8 位' },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="至少 8 位字符"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item
              className="register-confirm-item"
              label="确认密码"
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码!' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="请再次输入密码"
                autoComplete="new-password"
              />
            </Form.Item>

            <div className="register-action-group">
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                icon={<UserAddOutlined />}
                className="register-submit-btn"
              >
                创建账号
              </Button>
              <Button
                type="default"
                icon={<ArrowLeftOutlined />}
                className="register-back-btn"
                onClick={() => navigate('/login')}
              >
                返回登录
              </Button>
            </div>
          </Form>
        </Card>
      </div>
    </div>
  );
};

export default Register;
