import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Layout,
  Typography,
  Card,
  Form,
  Input,
  Select,
  Button,
  Space,
  List,
  Tag,
  message,
  Spin,
  Switch,
  Popconfirm,
} from 'antd';
import { SaveOutlined, RollbackOutlined, PlayCircleOutlined } from '@ant-design/icons';
import {
  getRuleDetails,
  getRuleVersions,
  updateDraft,
  publish,
  rollback,
  toggle,
} from '../services/rules';
import type { Rule, RuleVersion } from '../types/rule';
import SelfTestPanel from '../components/rules/SelfTestPanel';
import { useAuthStore } from '../store/useAuthStore';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface RuleFormValues {
  name: string;
  default_severity: string;
  description?: string;
  remediation?: string;
  query?: string;
}

const RuleDetailPage: React.FC = () => {
  const { ruleKey } = useParams<{ ruleKey: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [rule, setRule] = useState<Rule | null>(null);
  const [versions, setVersions] = useState<RuleVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const { user } = useAuthStore();
  const canManageRules = user?.role === 'Admin';

  const fetchData = async () => {
    if (!ruleKey) return;
    setLoading(true);
    try {
      const [ruleRes, versionsRes] = await Promise.all([
        getRuleDetails(ruleKey, { skipErrorToast: true }),
        getRuleVersions(ruleKey, { skipErrorToast: true }),
      ]);
      setRule(ruleRes);
      setVersions(versionsRes.items);

      // Populate form with latest version data or rule data
      const activeVersion = versionsRes.items.find((v) => v.version === ruleRes.active_version) || versionsRes.items[0];
      
      if (activeVersion) {
        form.setFieldsValue({
          name: ruleRes.name,
          default_severity: ruleRes.default_severity,
          description: ruleRes.description,
          remediation: activeVersion.content.remediation,
          query: activeVersion.content.query,
        });
      } else {
         form.setFieldsValue({
          name: ruleRes.name,
          default_severity: ruleRes.default_severity,
          description: ruleRes.description,
        });
      }
    } catch (error) {
      console.error('Failed to fetch rule details:', error);
      const status =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { status?: number } }).response?.status
          : undefined;
      if (status === 404) {
        message.error('规则不存在或尚未发布');
        navigate('/rules', { replace: true });
      } else {
        message.error('获取规则详情失败');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [ruleKey]);

  const handleSave = async (values: RuleFormValues) => {
    if (!ruleKey) return;
    setSaving(true);
    try {
      await updateDraft(ruleKey, {
        name: values.name,
        default_severity: values.default_severity,
        description: values.description,
        content: {
          query: values.query,
          remediation: values.remediation,
        },
      });
      message.success('规则草稿已保存');
      fetchData(); // Refresh data to show new version or updated state
    } catch (error) {
      console.error('Failed to save rule:', error);
      message.error('保存规则失败');
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!ruleKey) return;
    try {
      await publish(ruleKey);
      message.success('规则已发布');
      fetchData();
    } catch (error) {
      console.error('Failed to publish rule:', error);
      message.error('发布规则失败');
    }
  };

  const handleToggle = async (checked: boolean) => {
    if (!ruleKey) return;
    try {
      await toggle(ruleKey, checked);
      message.success(`规则已${checked ? '启用' : '禁用'}`);
      fetchData();
    } catch (error) {
      console.error('Failed to toggle rule:', error);
      message.error('切换规则状态失败');
    }
  };

  const handleRollback = async (version: number) => {
    if (!ruleKey) return;
    try {
      await rollback(ruleKey, version);
      message.success(`已回滚到版本 v${version}`);
      fetchData();
    } catch (error) {
      console.error('Failed to rollback rule:', error);
      message.error('回滚失败');
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!rule) {
    return <div>Rule not found</div>;
  }

  return (
    <Layout style={{ padding: '24px', background: '#fff' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2} style={{ marginBottom: 0 }}>
            {rule.name}
            <Tag color={rule.enabled ? 'success' : 'error'} style={{ marginLeft: 12, verticalAlign: 'middle' }}>
              {rule.enabled ? 'Active' : 'Disabled'}
            </Tag>
          </Title>
          <Text type="secondary">Key: {rule.rule_key}</Text>
        </div>
        <Space>
          {canManageRules ? (
            <div style={{ marginRight: 8, display: 'flex', alignItems: 'center' }}>
              <span style={{ marginRight: 8 }}>状态:</span>
              <Switch
                checked={rule.enabled}
                onChange={handleToggle}
                checkedChildren="开启"
                unCheckedChildren="关闭"
              />
            </div>
          ) : null}
          <Button onClick={() => navigate('/rules')}>返回列表</Button>
          {canManageRules ? (
            <Button type="primary" icon={<SaveOutlined />} onClick={() => form.submit()} loading={saving}>
              保存草稿
            </Button>
          ) : null}
          {canManageRules ? (
            <Button type="primary" ghost icon={<PlayCircleOutlined />} onClick={handlePublish}>
              发布版本
            </Button>
          ) : null}
        </Space>
      </div>

      <div style={{ display: 'flex', gap: '24px' }}>
        <div style={{ flex: 2 }}>
          <Card title="规则详情" bordered={false}>
            <Form
              form={form}
              layout="vertical"
              disabled={!canManageRules}
              onFinish={handleSave}
              initialValues={{
                default_severity: 'MEDIUM',
              }}
            >
              <Form.Item
                name="name"
                label="规则名称"
                rules={[{ required: true, message: '请输入规则名称' }]}
              >
                <Input placeholder="请输入规则名称" />
              </Form.Item>

              <Form.Item
                name="default_severity"
                label="严重程度"
                rules={[{ required: true, message: '请选择严重程度' }]}
              >
                <Select>
                  <Option value="CRITICAL">Critical</Option>
                  <Option value="HIGH">High</Option>
                  <Option value="MEDIUM">Medium</Option>
                  <Option value="LOW">Low</Option>
                  <Option value="INFO">Info</Option>
                </Select>
              </Form.Item>

              <Form.Item
                name="description"
                label="描述"
              >
                <TextArea rows={3} placeholder="请输入规则描述" />
              </Form.Item>

              <Form.Item
                name="remediation"
                label="修复建议"
              >
                <TextArea rows={3} placeholder="请输入修复建议" />
              </Form.Item>

              <Form.Item
                name="query"
                label="Cypher 查询语句"
                rules={[{ required: true, message: '请输入查询语句' }]}
              >
                <TextArea
                  rows={10}
                  style={{ fontFamily: 'monospace', fontSize: '14px', backgroundColor: '#f5f5f5' }}
                  placeholder="MATCH (n) RETURN n LIMIT 10"
                />
              </Form.Item>
            </Form>
          </Card>
        </div>

        <div style={{ flex: 1 }}>
          <Card title="版本历史" bordered={false}>
            <List
              itemLayout="horizontal"
              dataSource={versions}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    canManageRules && item.version !== rule.active_version && (
                      <Popconfirm
                        title="确认回滚"
                        description={`确定要回滚到版本 v${item.version} 吗？`}
                        onConfirm={() => handleRollback(item.version)}
                        okText="确认"
                        cancelText="取消"
                        key="rollback"
                      >
                        <Button type="link" size="small" icon={<RollbackOutlined />}>
                          回滚
                        </Button>
                      </Popconfirm>
                    )
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text strong>v{item.version}</Text>
                        {item.version === rule.active_version && <Tag color="green">Active</Tag>}
                        <Tag>{item.status}</Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0}>
                        <Text type="secondary" style={{ fontSize: '12px' }}>
                          {dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}
                        </Text>
                        {item.created_by && <Text type="secondary" style={{ fontSize: '12px' }}>by {item.created_by}</Text>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>

          {canManageRules ? (
            <SelfTestPanel
              ruleKey={ruleKey || ''}
              getDraftPayload={() => {
                const values = form.getFieldsValue();
                return {
                  query: values.query,
                  remediation: values.remediation,
                };
              }}
            />
          ) : null}
        </div>
      </div>
    </Layout>
  );
};

export default RuleDetailPage;
