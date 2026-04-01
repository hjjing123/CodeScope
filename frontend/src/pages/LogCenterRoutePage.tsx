import React from 'react';
import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';
import LogCenterPage from './LogCenterPage';
import { useAuthStore } from '../store/useAuthStore';

const LogCenterRoutePage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  if (user?.role !== 'Admin') {
    return (
      <Result
        status="403"
        title="403"
        subTitle="当前账号无权访问日志中心。"
        extra={
          <Button type="primary" onClick={() => navigate('/dashboard')}>
            返回安全概览
          </Button>
        }
      />
    );
  }

  return <LogCenterPage />;
};

export default LogCenterRoutePage;
