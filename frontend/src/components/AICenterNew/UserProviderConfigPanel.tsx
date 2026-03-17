import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Typography, 
  Form, 
  Input, 
  Button, 
  Table, 
  Space, 
  message, 
  Popconfirm,
  Select,
  Switch,
  Row,
  Col,
  Empty
} from 'antd';
import { 
  EditOutlined, 
  DeleteOutlined, 
  SaveOutlined,
  LeftOutlined,
  UserOutlined,
  ApiOutlined
} from '@ant-design/icons';
import { 
  listMyAIProviders, 
  createMyAIProvider, 
  updateMyAIProvider, 
  deleteMyAIProvider, 
  testMyAIProvider 
} from '../../services/ai';
import type { 
  UserAIProviderPayload, 
  UserAIProviderCreateRequest, 
  UserAIProviderUpdateRequest 
} from '../../types/ai';

const { Title, Text } = Typography;

interface UserProviderConfigPanelProps {
  onBack: () => void;
}

interface ProviderFormValues {
  display_name: string;
  vendor_name: string;
  base_url: string;
  api_key?: string;
  default_model: string;
}

const UserProviderConfigPanel: React.FC<UserProviderConfigPanelProps> = ({ onBack }) => {
  const [providers, setProviders] = useState<UserAIProviderPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingProvider, setEditingProvider] = useState<UserAIProviderPayload | null>(null);
  
  const [form] = Form.useForm<ProviderFormValues>();

  const loadProviders = async () => {
    setLoading(true);
    try {
      const res = await listMyAIProviders();
      setProviders(res.items);
    } catch (error) {
      message.error('加载 Provider 列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
  }, []);

  const handleEdit = (record: UserAIProviderPayload) => {
    setEditingProvider(record);
    form.setFieldsValue({
      display_name: record.display_name,
      vendor_name: record.vendor_name,
      base_url: record.base_url,
      api_key: '', // Don't show existing key
      default_model: record.default_model,
    });
  };

  const handleReset = () => {
    setEditingProvider(null);
    form.resetFields();
    form.setFieldsValue({
      vendor_name: 'OpenAI Compatible',
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMyAIProvider(id);
      message.success('已删除');
      if (editingProvider?.id === id) {
        handleReset();
      }
      loadProviders();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testMyAIProvider(id);
      const modelCount = typeof res.detail.model_count === 'number' ? res.detail.model_count : 0;
      message.success(`测试成功，发现 ${modelCount} 个模型`);
    } catch (error) {
      message.error('测试请求失败，请检查配置或网络');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingProvider) {
        const payload: UserAIProviderUpdateRequest = {
          display_name: values.display_name,
          vendor_name: values.vendor_name,
          base_url: values.base_url,
          default_model: values.default_model,
        };
        if (values.api_key?.trim()) {
          payload.api_key = values.api_key.trim();
        }
        await updateMyAIProvider(editingProvider.id, payload);
        message.success('更新成功');
      } else {
        const payload: UserAIProviderCreateRequest = {
          display_name: values.display_name,
          vendor_name: values.vendor_name,
          base_url: values.base_url,
          api_key: values.api_key?.trim() || '',
          default_model: values.default_model,
          timeout_seconds: 60,
          temperature: 0.1,
          enabled: true,
          is_default: false,
        };
        await createMyAIProvider(payload);
        message.success('创建成功');
      }
      handleReset();
      loadProviders();
    } catch (error) {
      console.error(error);
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (record: UserAIProviderPayload, checked: boolean) => {
    try {
      await updateMyAIProvider(record.id, { enabled: checked });
      message.success(checked ? '已启用' : '已禁用');
      loadProviders();
    } catch (error) {
      message.error('状态切换失败');
    }
  };

  const handleToggleDefault = async (record: UserAIProviderPayload, checked: boolean) => {
    try {
      await updateMyAIProvider(record.id, { is_default: checked });
      message.success(checked ? '已设为默认' : '已取消默认');
      loadProviders();
    } catch (error) {
      message.error('设置默认失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'display_name',
      key: 'display_name',
      render: (text: string, record: UserAIProviderPayload) => (
        <Space direction="vertical" size={0}>
          <Text strong>{text}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.vendor_name}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'status',
      render: (_: unknown, record: UserAIProviderPayload) => (
        <Space direction="vertical" size={4}>
          <Space size="small">
            <Switch 
              size="small" 
              checked={record.enabled} 
              onChange={(checked) => handleToggleEnabled(record, checked)} 
            />
            <Text style={{ fontSize: 12 }}>启用</Text>
          </Space>
          <Space size="small">
            <Switch 
              size="small" 
              checked={record.is_default} 
              onChange={(checked) => handleToggleDefault(record, checked)} 
            />
            <Text style={{ fontSize: 12 }}>默认</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: 'API Base',
      dataIndex: 'base_url',
      key: 'base_url',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: UserAIProviderPayload) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => handleTest(record.id)}>测试</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除?" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger size="small" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '24px', background: '#fff' }}>
      <div style={{ margin: '0 auto', paddingBottom: 24 }}>
        <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center' }}>
          <Button icon={<LeftOutlined />} onClick={onBack} style={{ marginRight: 16 }}>
            返回对话
          </Button>
          <Title level={4} style={{ margin: 0 }}>个人模型配置</Title>
        </div>

        <Row gutter={[24, 24]}>
          {/* Form Card */}
          <Col xs={24} lg={8}>
            <Card 
              title={<Space><ApiOutlined />{editingProvider ? `编辑: ${editingProvider.display_name}` : '添加新 Provider'}</Space>} 
              bordered={true} 
              style={{ height: '100%' }}
            >
              <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ vendor_name: 'OpenAI Compatible' }}>
                <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="例如: 我的 DeepSeek" />
                </Form.Item>
                <Form.Item name="vendor_name" label="厂商类型" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { label: 'OpenAI Compatible', value: 'OpenAI Compatible' },
                      { label: 'DeepSeek', value: 'DeepSeek' },
                      { label: 'OpenRouter', value: 'OpenRouter' },
                      { label: 'Azure OpenAI', value: 'Azure OpenAI' },
                      { label: 'Anthropic', value: 'Anthropic' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="base_url" label="API Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
                  <Input placeholder="例如: https://api.deepseek.com/v1" />
                </Form.Item>
                <Form.Item 
                  name="api_key" 
                  label="API Key" 
                  rules={[{ required: !editingProvider, message: '请输入 API Key' }]}
                  extra={editingProvider ? "留空则保持原有 Key 不变" : undefined}
                >
                  <Input.Password placeholder="sk-..." />
                </Form.Item>
                <Form.Item name="default_model" label="默认模型名称" rules={[{ required: true, message: '请输入模型名称' }]}>
                  <Input placeholder="例如: deepseek-chat" />
                </Form.Item>

                <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
                  <Button 
                    type="primary" 
                    icon={<SaveOutlined />} 
                    htmlType="submit" 
                    loading={saving}
                    block
                  >
                    {editingProvider ? '保存修改' : '创建 Provider'}
                  </Button>
                  {editingProvider && (
                    <Button onClick={handleReset} block>
                      取消编辑
                    </Button>
                  )}
                </div>
              </Form>
            </Card>
          </Col>

          {/* List Card */}
          <Col xs={24} lg={16}>
            <Card 
              title={<Space><UserOutlined />我的 Providers</Space>} 
              bordered={true} 
              style={{ height: '100%' }}
            >
              <Table 
                dataSource={providers} 
                columns={columns} 
                rowKey="id" 
                pagination={false} 
                size="small"
                loading={loading}
                locale={{ emptyText: <Empty description="暂无配置，请在左侧添加" /> }}
              />
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  );
};

export default UserProviderConfigPanel;
