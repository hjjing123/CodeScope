import React, { useState, useEffect } from 'react';
import axios from 'axios';
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
  testMyAIProvider,
  testMyAIProviderDraft,
} from '../../services/ai';
import type { 
  AIProviderDraftTestPayload,
  AIProviderModelVerificationPayload,
  UserAIProviderPayload, 
  UserAIProviderCreateRequest, 
  UserAIProviderUpdateRequest 
} from '../../types/ai';
import {
  DEFAULT_PROVIDER_VENDOR,
  USER_PROVIDER_PRESETS,
  buildProviderPresetPatch,
  getUserProviderPreset,
} from './providerPresets';

const { Title, Text } = Typography;

interface UserProviderConfigPanelProps {
  onBack: () => void;
}

interface ProviderFormValues {
  vendor_name: string;
  base_url: string;
  api_key?: string;
  default_model: string;
}

interface SavedProviderTestDetail {
  model_count?: number;
  status_reason?: string | null;
  selected_model_verification?: AIProviderModelVerificationPayload | null;
}

const getProviderRequestErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const backendMessage = error.response?.data?.error?.message || error.response?.data?.message;
    if (typeof backendMessage === 'string' && backendMessage.trim()) {
      return backendMessage;
    }
    if (!error.response) {
      return '网络错误，请检查服务状态或稍后重试';
    }
  }
  return fallback;
};

const UserProviderConfigPanel: React.FC<UserProviderConfigPanelProps> = ({ onBack }) => {
  const [providers, setProviders] = useState<UserAIProviderPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingDraft, setTestingDraft] = useState(false);
  const [verifyingModel, setVerifyingModel] = useState(false);
  const [editingProvider, setEditingProvider] = useState<UserAIProviderPayload | null>(null);
  const [lastPresetVendor, setLastPresetVendor] = useState<string>(DEFAULT_PROVIDER_VENDOR);
  const [draftTestResult, setDraftTestResult] = useState<AIProviderDraftTestPayload | null>(null);
  const [modelVerification, setModelVerification] = useState<AIProviderModelVerificationPayload | null>(null);
  
  const [form] = Form.useForm<ProviderFormValues>();
  const selectedVendorName = Form.useWatch('vendor_name', form);
  const selectedPreset = getUserProviderPreset(selectedVendorName);
  const selectedModelName = Form.useWatch('default_model', form);
  const discoveredModels = draftTestResult?.models ?? [];
  const normalizedSelectedModelName = typeof selectedModelName === 'string' ? selectedModelName.trim() : '';
  const isCurrentModelVerified = Boolean(
    modelVerification?.ok && modelVerification.model === normalizedSelectedModelName
  );

  const loadProviders = async () => {
    setLoading(true);
    try {
      const res = await listMyAIProviders();
      setProviders(res.items);
    } catch {
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
    setLastPresetVendor(record.vendor_name || DEFAULT_PROVIDER_VENDOR);
    setDraftTestResult(null);
    setModelVerification(null);
    form.setFieldsValue({
      vendor_name: record.vendor_name,
      base_url: record.base_url,
      api_key: '', // Don't show existing key
      default_model: record.default_model,
    });
  };

  const handleReset = () => {
    setEditingProvider(null);
    setLastPresetVendor(DEFAULT_PROVIDER_VENDOR);
    setDraftTestResult(null);
    setModelVerification(null);
    form.resetFields();
    form.setFieldsValue({
      vendor_name: DEFAULT_PROVIDER_VENDOR,
    });
  };

  const handleVendorChange = (nextVendorName: string) => {
    const currentValues = form.getFieldsValue();
    form.setFieldsValue(
      buildProviderPresetPatch({
        nextVendorName,
        previousVendorName: lastPresetVendor,
        currentValues,
      })
    );
    setLastPresetVendor(nextVendorName);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMyAIProvider(id);
      message.success('已删除');
      if (editingProvider?.id === id) {
        handleReset();
      }
      loadProviders();
    } catch {
      message.error('删除失败');
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testMyAIProvider(id);
      const detail = res.detail as SavedProviderTestDetail;
      const modelCount = typeof detail.model_count === 'number' ? detail.model_count : 0;
      const verification = detail.selected_model_verification;
      if (verification && verification.ok === false) {
        message.error(verification.message || '默认模型验证失败，请更换可用模型');
        return;
      }
      if (verification?.ok && verification.model) {
        message.success(`测试成功，默认模型 ${verification.model} 可用，共发现 ${modelCount} 个模型`);
        return;
      }
      const allowManualModelInput = Boolean(
        (res.detail as Record<string, unknown>).allow_manual_model_input
      );
      const statusReason = typeof detail.status_reason === 'string' ? detail.status_reason : '';
      if (!res.ok) {
        message.error(statusReason || '测试失败，请检查配置或网络');
        return;
      }
      if (allowManualModelInput) {
        message.success(statusReason || '连接成功，请手动填写模型名称');
        return;
      }
      message.success(`测试成功，发现 ${modelCount} 个模型`);
    } catch (error) {
      message.error(getProviderRequestErrorMessage(error, '测试请求失败，请检查配置或网络'));
    }
  };

  const handleDraftTest = async () => {
    try {
      const values = await form.validateFields(['vendor_name', 'base_url']);
      const apiKey = form.getFieldValue('api_key')?.trim() || '';
      if (!apiKey) {
        message.warning('请输入 API Key 后再测试');
        return;
      }

      setTestingDraft(true);
      const res = await testMyAIProviderDraft({
        vendor_name: values.vendor_name,
        base_url: values.base_url,
        api_key: apiKey,
        timeout_seconds: 60,
      });
      setDraftTestResult(res);
      setModelVerification(null);

      if (res.models.length > 0) {
        const currentModel = form.getFieldValue('default_model')?.trim();
        const hasCurrentModel = res.models.some((item) => item.name === currentModel);
        if (!hasCurrentModel) {
          form.setFieldsValue({ default_model: undefined });
        }
      } else if (!editingProvider) {
        form.setFieldsValue({ default_model: undefined });
      }

      if (!res.connection_ok) {
        message.error(res.status_reason || '测试失败，请检查配置或网络');
        return;
      }
      if (res.model_count > 0) {
        message.success(`测试成功，发现 ${res.model_count} 个模型`);
        return;
      }
      if (res.allow_manual_model_input) {
        message.success(res.status_reason || '连接成功，请手动填写模型名称');
        return;
      }
      message.error(res.status_reason || '当前未发现可用模型');
    } catch (error) {
      console.error(error);
      message.error(getProviderRequestErrorMessage(error, '测试请求失败，请检查配置或网络'));
    } finally {
      setTestingDraft(false);
    }
  };

  const handleVerifySelectedModel = async () => {
    try {
      const values = await form.validateFields(['vendor_name', 'base_url', 'default_model']);
      const apiKey = form.getFieldValue('api_key')?.trim() || '';
      if (!apiKey) {
        message.warning('请输入 API Key 后再验证模型');
        return;
      }

      setVerifyingModel(true);
      const res = await testMyAIProviderDraft({
        vendor_name: values.vendor_name,
        base_url: values.base_url,
        api_key: apiKey,
        timeout_seconds: 60,
        selected_model: values.default_model.trim(),
        verify_selected_model: true,
      });
      setDraftTestResult(res);
      setModelVerification(res.selected_model_verification ?? null);

      if (res.selected_model_verification?.ok) {
        message.success(`模型 ${res.selected_model_verification.model} 验证成功`);
        return;
      }
      message.error(res.selected_model_verification?.message || '模型验证失败，请更换模型');
    } catch (error) {
      console.error(error);
      message.error(getProviderRequestErrorMessage(error, '模型验证失败，请检查配置或网络'));
    } finally {
      setVerifyingModel(false);
    }
  };

  const handleSubmit = async () => {
    try {
      if (!editingProvider && !draftTestResult) {
        message.warning('请先测试并获取模型');
        return;
      }
      const values = await form.validateFields();
      if (!editingProvider) {
        if (!isCurrentModelVerified) {
          message.warning('请先验证当前模型可用性');
          return;
        }
      }
      setSaving(true);
      if (editingProvider) {
        const payload: UserAIProviderUpdateRequest = {
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

  const handleFormValuesChange = (changedValues: Partial<ProviderFormValues>) => {
    const changedKeys = Object.keys(changedValues);
    if (changedKeys.some((key) => ['vendor_name', 'base_url', 'api_key'].includes(key))) {
      setDraftTestResult(null);
      setModelVerification(null);
      if (!editingProvider) {
        form.setFieldsValue({ default_model: undefined });
      }
      return;
    }
    if (changedKeys.includes('default_model')) {
      setModelVerification(null);
    }
  };

  const handleToggleEnabled = async (record: UserAIProviderPayload, checked: boolean) => {
    try {
      await updateMyAIProvider(record.id, { enabled: checked });
      message.success(checked ? '已启用' : '已禁用');
      loadProviders();
    } catch {
      message.error('状态切换失败');
    }
  };

  const handleToggleDefault = async (record: UserAIProviderPayload, checked: boolean) => {
    try {
      await updateMyAIProvider(record.id, { is_default: checked });
      message.success(checked ? '已设为默认' : '已取消默认');
      loadProviders();
    } catch {
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
              <Form
                form={form}
                layout="vertical"
                onFinish={handleSubmit}
                onValuesChange={handleFormValuesChange}
                initialValues={{ vendor_name: DEFAULT_PROVIDER_VENDOR }}
              >
                <Form.Item name="vendor_name" label="厂商类型" rules={[{ required: true }]}>
                  <Select
                    options={USER_PROVIDER_PRESETS.map((item) => ({
                      label: item.label,
                      value: item.value,
                    }))}
                    onChange={handleVendorChange}
                  />
                </Form.Item>
                <Form.Item
                  name="base_url"
                  label="API Base URL"
                  rules={[{ required: true, message: '请输入 Base URL' }]}
                >
                  <Input placeholder={selectedPreset.baseUrlPlaceholder} />
                </Form.Item>
                <Form.Item 
                  name="api_key" 
                  label="API Key" 
                  rules={[{ required: !editingProvider, message: '请输入 API Key' }]}
                >
                  <Input.Password
                    placeholder={
                      editingProvider ? '留空则保持原有 Key 不变' : selectedPreset.apiKeyPlaceholder
                    }
                  />
                </Form.Item>
                <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
                  <Button onClick={handleDraftTest} loading={testingDraft} block>
                    测试并获取模型
                  </Button>
                  <Button
                    onClick={handleVerifySelectedModel}
                    loading={verifyingModel}
                    disabled={!normalizedSelectedModelName || isCurrentModelVerified}
                    block
                  >
                    {isCurrentModelVerified ? '当前模型已验证' : '验证当前模型'}
                  </Button>
                </div>
                <Form.Item
                  name="default_model"
                  label="默认模型名称"
                  rules={[{ required: true, message: '请输入模型名称' }]}
                >
                  {discoveredModels.length > 0 ? (
                    <Select
                      showSearch
                      placeholder="请选择要调用的模型"
                      options={discoveredModels.map((item) => ({
                        label: item.label,
                        value: item.name,
                      }))}
                    />
                  ) : (
                    <Input
                      placeholder={
                        !editingProvider && !draftTestResult
                          ? '请先测试并获取模型'
                          : selectedPreset.defaultModelPlaceholder
                      }
                      disabled={!editingProvider && !draftTestResult}
                    />
                  )}
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
