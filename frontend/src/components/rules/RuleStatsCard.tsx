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
    <Row gutter={16} style={{ marginBottom: 24 }}>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable>
          <Statistic
            title="规则总数"
            value={totalRules}
            prefix={<SafetyCertificateOutlined />}
            valueStyle={{ color: '#1890ff' }}
          />
        </Card>
      </Col>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable>
          <Statistic
            title="已启用"
            value={enabledRules}
            prefix={<CheckCircleOutlined />}
            valueStyle={{ color: '#3f8600' }}
          />
        </Card>
      </Col>
      <Col span={8}>
        <Card bordered={false} loading={loading} hoverable>
          <Statistic
            title="已禁用"
            value={disabledRules}
            prefix={<StopOutlined />}
            valueStyle={{ color: '#cf1322' }}
          />
        </Card>
      </Col>
    </Row>
  );
};

export default RuleStatsCard;
