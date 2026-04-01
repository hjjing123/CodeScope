import React, { useState, useEffect } from 'react';
import {
  Card,
  message,
  Button,
  Space,
  Tabs,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import RuleStatsCard from '../components/rules/RuleStatsCard';
import RuleListTable from '../components/rules/RuleListTable';
import RuleSetList from '../components/rules/RuleSetList';
import { createRule, getRules, toggle } from '../services/rules';
import { useAuthStore } from '../store/useAuthStore';
import type { Rule } from '../types/rule';

const { TextArea } = Input;

interface CreateRuleFormValues {
  rule_key: string;
  name: string;
  vuln_type: string;
  default_severity: string;
  description?: string;
  query: string;
  timeout_ms: number;
}

const RuleCenterPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Rule[]>([]);
  const [total, setTotal] = useState(0);
  const [enabledCount, setEnabledCount] = useState(0);
  const [disabledCount, setDisabledCount] = useState(0);
  const [togglingRuleKeys, setTogglingRuleKeys] = useState<string[]>([]);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const { user } = useAuthStore();
  const canManageRules = user?.role === 'Admin';
  const navigate = useNavigate();
  const [createForm] = Form.useForm<CreateRuleFormValues>();
  
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });

  const [filters, setFilters] = useState<{
    enabled?: boolean;
    vuln_type?: string;
    search?: string;
  }>({});

  const fetchStats = async () => {
    try {
      // Fetch enabled count
      const enabledRes = await getRules({ enabled: true, page_size: 1 });
      setEnabledCount(enabledRes.total);
      
      // Fetch disabled count
      const disabledRes = await getRules({ enabled: false, page_size: 1 });
      setDisabledCount(disabledRes.total);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const fetchData = async (page: number, pageSize: number, currentFilters: typeof filters) => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const params: any = {
        page,
        page_size: pageSize,
        ...currentFilters,
      };
      
      if (currentFilters.enabled !== undefined) {
        params.enabled = currentFilters.enabled;
      }
      
      if (currentFilters.vuln_type) {
        params.vuln_type = currentFilters.vuln_type;
      }

      const res = await getRules(params);
      setData(res.items);
      setTotal(res.total);
    } catch {
      message.error('获取规则列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchData(pagination.current, pagination.pageSize, filters);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchData(pagination.current, pagination.pageSize, filters);
  }, [pagination.current, pagination.pageSize, filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleTableChange = (newPagination: any, newFilters: any) => {
    setPagination({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    });
    
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const nextFilters: any = { ...filters };
    
    if (newFilters.enabled && newFilters.enabled.length === 1) {
      nextFilters.enabled = newFilters.enabled[0];
    } else {
      delete nextFilters.enabled;
    }
    
    setFilters(nextFilters);
  };

  const handleToggleRule = async (rule: Rule, checked: boolean) => {
    if (togglingRuleKeys.includes(rule.rule_key)) {
      return;
    }
    const prevEnabled = rule.enabled;
    const shouldAdjustStats = prevEnabled !== checked;
    setTogglingRuleKeys((prev) => [...prev, rule.rule_key]);
    setData((prev) =>
      prev.map((item) => (item.rule_key === rule.rule_key ? { ...item, enabled: checked } : item))
    );
    if (shouldAdjustStats) {
      setEnabledCount((prev) => Math.max(prev + (checked ? 1 : -1), 0));
      setDisabledCount((prev) => Math.max(prev + (checked ? -1 : 1), 0));
    }
    try {
      await toggle(rule.rule_key, checked);
      message.success(`${checked ? '启用' : '禁用'}规则成功`);
      fetchStats();
    } catch {
      setData((prev) =>
        prev.map((item) => (item.rule_key === rule.rule_key ? { ...item, enabled: prevEnabled } : item))
      );
      if (shouldAdjustStats) {
        setEnabledCount((prev) => Math.max(prev + (checked ? -1 : 1), 0));
        setDisabledCount((prev) => Math.max(prev + (checked ? 1 : -1), 0));
      }
      message.error('操作失败');
    } finally {
      setTogglingRuleKeys((prev) => prev.filter((key) => key !== rule.rule_key));
    }
  };

  const handleEditRule = (rule: Rule) => {
    navigate(`/rules/${rule.rule_key}`);
  };
  
  const handleViewVersions = (rule: Rule) => {
    navigate(`/rules/${rule.rule_key}`);
  };

  const handleOpenCreateModal = () => {
    if (!canManageRules) {
      return;
    }

    createForm.setFieldsValue({
      default_severity: 'MED',
      vuln_type: 'CUSTOM',
      timeout_ms: 5000,
    });
    setCreateModalOpen(true);
  };

  const handleCreateRule = async () => {
    if (!canManageRules) {
      return;
    }

    try {
      const values = await createForm.validateFields();
      setCreating(true);
      const created = await createRule({
        rule_key: values.rule_key.trim(),
        name: values.name.trim(),
        vuln_type: values.vuln_type.trim(),
        default_severity: values.default_severity,
        description: values.description?.trim() || undefined,
        content: {
          query: values.query,
          timeout_ms: Number(values.timeout_ms),
        },
      });
      message.success('规则创建成功');
      setCreateModalOpen(false);
      createForm.resetFields();
      fetchStats();
      fetchData(pagination.current, pagination.pageSize, filters);
      navigate(`/rules/${created.rule_key}`);
    } catch (error) {
      if (error instanceof Error) {
        console.error('Create rule failed:', error);
      }
      message.error('创建规则失败');
    } finally {
      setCreating(false);
    }
  };

  const handleSearch = (value: string) => {
    setFilters((prev) => ({ ...prev, search: value }));
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const renderRulesTab = () => (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <RuleStatsCard
        totalRules={enabledCount + disabledCount}
        enabledRules={enabledCount}
        disabledRules={disabledCount}
        loading={loading && total === 0}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ width: 300 }}>
          <Input.Search
            placeholder="搜索规则名称或标识"
            allowClear
            onSearch={handleSearch}
            enterButton
          />
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => {
            fetchStats();
            fetchData(pagination.current, pagination.pageSize, filters);
          }}>刷新</Button>
          {canManageRules ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreateModal}>
              新建规则
            </Button>
          ) : null}
        </Space>
      </div>

      <Card bodyStyle={{ padding: 0 }} bordered={false}>
        <RuleListTable
          loading={loading}
          dataSource={data}
          togglingRuleKeys={togglingRuleKeys}
          canManageRules={canManageRules}
          pagination={{
            ...pagination,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
          onEdit={handleEditRule}
          onToggle={handleToggleRule}
          onViewVersions={handleViewVersions}
          size="small"
        />
      </Card>
    </Space>
  );

  const items = [
    {
      key: 'rules',
      label: '规则列表',
      children: renderRulesTab(),
    },
    {
      key: 'rulesets',
      label: '规则集',
      children: (
        <Card>
          <RuleSetList canManageRuleSets={canManageRules} />
        </Card>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Tabs defaultActiveKey="rules" items={items} destroyInactiveTabPane={true} />
      </Space>

      <Modal
        title="新建规则"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={handleCreateRule}
        confirmLoading={creating}
        width={760}
        destroyOnClose
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{
            default_severity: 'MED',
            vuln_type: 'CUSTOM',
            timeout_ms: 5000,
          }}
        >
          <Form.Item
            name="rule_key"
            label="规则标识"
            rules={[
              { required: true, message: '请输入规则标识' },
              {
                pattern: /^[A-Za-z0-9._-]{1,128}$/,
                message: '仅支持字母数字以及 ._-，长度不超过 128',
              },
            ]}
          >
            <Input placeholder="例如: custom.demo.xss" />
          </Form.Item>

          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <Input placeholder="请输入规则名称" />
          </Form.Item>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item
              name="vuln_type"
              label="漏洞类型"
              style={{ width: 220 }}
              rules={[{ required: true, message: '请选择漏洞类型' }]}
            >
              <Select>
                <Select.Option value="XSS">XSS</Select.Option>
                <Select.Option value="SQLI">SQLI</Select.Option>
                <Select.Option value="SSRF">SSRF</Select.Option>
                <Select.Option value="XXE">XXE</Select.Option>
                <Select.Option value="RCE">RCE</Select.Option>
                <Select.Option value="PATH_TRAVERSAL">PATH_TRAVERSAL</Select.Option>
                <Select.Option value="OPEN_REDIRECT">OPEN_REDIRECT</Select.Option>
                <Select.Option value="UPLOAD">UPLOAD</Select.Option>
                <Select.Option value="CUSTOM">CUSTOM</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="default_severity"
              label="严重程度"
              style={{ width: 160 }}
              rules={[{ required: true, message: '请选择严重程度' }]}
            >
              <Select>
                <Select.Option value="HIGH">HIGH</Select.Option>
                <Select.Option value="MED">MED</Select.Option>
                <Select.Option value="LOW">LOW</Select.Option>
              </Select>
            </Form.Item>

          </Space>

          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="请输入规则描述" />
          </Form.Item>

          <Form.Item
            name="query"
            label="Cypher 查询语句"
            rules={[{ required: true, message: '请输入查询语句' }]}
          >
            <TextArea
              rows={10}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
              placeholder="MATCH (n) RETURN n LIMIT 10"
            />
          </Form.Item>

          <Form.Item
            name="timeout_ms"
            label="超时毫秒"
            rules={[{ required: true, message: '请输入超时时间' }]}
          >
            <InputNumber min={100} max={120000} step={100} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RuleCenterPage;
