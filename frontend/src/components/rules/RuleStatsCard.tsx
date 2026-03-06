import React from 'react';
import { Card, Col, Row, Statistic } from 'antd';
import { SafetyCertificateOutlined, CheckCircleOutlined, StopOutlined } from '@ant-design/icons';

interface RuleStatsCardProps {
  totalRules: number;
  enabledRules: number;
  disabledRules: number;
  loading?: boolean;
}

const RuleStatsCard: React.FC<RuleStatsCardProps> = ({
  totalRules,
  enabledRules,
  disabledRules,
  loading = false,
}) => {
  return (
    <Row gutter={16}>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable bodyStyle={{ padding: '12px 24px' }}>
          <Statistic
            title={<span style={{ fontSize: 14 }}>规则总数</span>}
            value={totalRules}
            prefix={<SafetyCertificateOutlined />}
            valueStyle={{ color: '#1890ff', fontSize: 24 }}
          />
        </Card>
      </Col>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable bodyStyle={{ padding: '12px 24px' }}>
          <Statistic
            title={<span style={{ fontSize: 14 }}>已启用</span>}
            value={enabledRules}
            prefix={<CheckCircleOutlined />}
            valueStyle={{ color: '#3f8600', fontSize: 24 }}
          />
        </Card>
      </Col>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable bodyStyle={{ padding: '12px 24px' }}>
          <Statistic
            title={<span style={{ fontSize: 14 }}>已禁用</span>}
            value={disabledRules}
            prefix={<StopOutlined />}
            valueStyle={{ color: '#cf1322', fontSize: 24 }}
          />
        </Card>
      </Col>
    </Row>
  );
};

export default RuleStatsCard;
