import React, { useState, useEffect, useRef } from 'react';
import { 
  Card, 
  Typography, 
  Form, 
  Input, 
  Button, 
  Table, 
  Space, 
  message, 
  Row, 
  Col, 
  Select, 
  InputNumber, 
  Popconfirm,
  Tag,
  Progress,
  Tooltip
} from 'antd';
import { 
  CloudServerOutlined, 
  ApiOutlined, 
  ReloadOutlined, 
  DeleteOutlined, 
  DownloadOutlined, 
  SaveOutlined,
  LeftOutlined,
  HistoryOutlined,
  ArrowLeftOutlined
} from '@ant-design/icons';
import { 
  getSystemOllamaConfig, 
  updateSystemOllamaConfig, 
  testSystemOllamaConfig, 
  listOllamaModels, 
  pullOllamaModel, 
  deleteOllamaModel,
  listOllamaPullJobs
} from '../../services/ai';
import type { 
  OllamaModelPayload, 
  SystemOllamaConfigPayload, 
  SystemOllamaPullJob,
  SystemOllamaPullJobStatus 
} from '../../types/ai';

const { Title, Text } = Typography;

interface OllamaConfigPanelProps {
  onBack: () => void;
}

const OllamaConfigPanel: React.FC<OllamaConfigPanelProps> = ({ onBack }) => {
  const [loading, setLoading] = useState(false);
  const [config, setConfig] = useState<SystemOllamaConfigPayload | null>(null);
  const [models, setModels] = useState<OllamaModelPayload[]>([]);
  const [testing, setTesting] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [pullModelName, setPullModelName] = useState('');
  
  // Progress view state
  const [viewMode, setViewMode] = useState<'models' | 'pulls'>('models');
  const [pullJobs, setPullJobs] = useState<SystemOllamaPullJob[]>([]);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [form] = Form.useForm();

  const loadConfig = async () => {
    setLoading(true);
    try {
      const res = await getSystemOllamaConfig();
      setConfig(res);
      form.setFieldsValue({
        base_url: res.base_url,
        default_model: res.default_model,
        timeout_seconds: res.timeout_seconds,
        temperature: res.temperature,
      });
      if (res.connection_ok) {
        loadModels();
      }
    } catch (error) {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const loadModels = async () => {
    try {
      const res = await listOllamaModels();
      setModels(res.items);
    } catch (error) {
      console.error('加载模型列表失败', error);
    }
  };

  const loadPullJobs = async () => {
    try {
      const res = await listOllamaPullJobs({ limit: 20 });
      setPullJobs(res.items);
      return res.items;
    } catch (error) {
      console.error('加载拉取任务失败', error);
      return [];
    }
  };

  useEffect(() => {
    loadConfig();
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, []);

  // Poll for pull jobs when in 'pulls' mode
  useEffect(() => {
    if (viewMode === 'pulls') {
      loadPullJobs();
      
      const poll = async () => {
        const jobs = await loadPullJobs();
        const hasActive = jobs.some(j => ['PENDING', 'RUNNING'].includes(j.status));
        if (hasActive && viewMode === 'pulls') {
          pollTimerRef.current = setTimeout(poll, 3000);
        }
      };
      
      poll();
    } else {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    }
    
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, [viewMode]);

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      const res = await testSystemOllamaConfig();
      if (res.ok) {
        message.success('连接成功');
        setConfig(prev => prev ? { ...prev, connection_ok: true } : null);
        loadModels();
      } else {
        message.error('连接失败');
        setConfig(prev => prev ? { ...prev, connection_ok: false } : null);
      }
    } catch (error) {
      message.error('测试请求失败');
    } finally {
      setTesting(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      const values = await form.validateFields();
      await updateSystemOllamaConfig({
        base_url: values.base_url,
        default_model: values.default_model,
        timeout_seconds: values.timeout_seconds,
        temperature: values.temperature,
        enabled: true, // Always enable if saving
        published_models: [], // Keep existing logic or update if needed
        display_name: 'System Ollama'
      });
      message.success('配置已保存');
      handleTestConnection();
    } catch (error) {
      message.error('保存失败');
    }
  };

  const handlePullModel = async () => {
    if (!pullModelName.trim()) return;
    setPulling(true);
    try {
      await pullOllamaModel(pullModelName);
      message.success(`模型 ${pullModelName} 拉取任务已提交`);
      setPullModelName('');
      setViewMode('pulls'); // Switch to progress view
    } catch (error) {
      message.error('拉取模型失败');
    } finally {
      setPulling(false);
    }
  };

  const handleDeleteModel = async (name: string) => {
    try {
      await deleteOllamaModel(name);
      message.success('模型已删除');
      loadModels();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const getStatusColor = (status: SystemOllamaPullJobStatus) => {
    switch (status) {
      case 'SUCCEEDED': return 'success';
      case 'RUNNING': return 'processing';
      case 'FAILED': 
      case 'TIMEOUT': return 'error';
      case 'CANCELED': return 'default';
      default: return 'default';
    }
  };

  const modelColumns = [
    {
      title: '模型名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => (
        <Tooltip title={text}>
          <Text strong style={{ maxWidth: 200, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle' }}>
            {text}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => (size ? `${(size / 1024 / 1024 / 1024).toFixed(2)} GB` : '-'),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: OllamaModelPayload) => (
        <Popconfirm title="确定删除此模型?" onConfirm={() => handleDeleteModel(record.name)}>
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  const pullJobColumns = [
    {
      title: '模型名称',
      dataIndex: 'model_name',
      key: 'model_name',
      render: (text: string) => (
        <Tooltip title={text}>
          <Text strong style={{ maxWidth: 200, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle' }}>
            {text}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: SystemOllamaPullJobStatus) => (
        <Tag color={getStatusColor(status)}>{status}</Tag>
      ),
    },
    {
      title: '进度',
      key: 'progress',
      render: (_: unknown, record: SystemOllamaPullJob) => {
        const { percent, status_text } = record.progress || {};
        return (
          <div style={{ minWidth: 200 }}>
            <Progress 
              percent={percent || 0} 
              size="small" 
              status={record.status === 'FAILED' ? 'exception' : (record.status === 'SUCCEEDED' ? 'success' : 'active')} 
            />
            <div style={{ fontSize: 12, color: '#888', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <Tooltip title={status_text || '-'}>{status_text || '-'}</Tooltip>
            </div>
          </div>
        );
      }
    },
    {
      title: '阶段',
      dataIndex: 'stage',
      key: 'stage',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString(),
    }
  ];

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '24px', background: '#fff' }}>
      <div style={{ margin: '0 auto', paddingBottom: 24 }}>
        <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center' }}>
          <Button icon={<LeftOutlined />} onClick={onBack} style={{ marginRight: 16 }}>
            返回对话
          </Button>
          <Title level={4} style={{ margin: 0 }}>系统 Ollama 配置</Title>
        </div>

        <Row gutter={[24, 24]}>
          {/* Status Card */}
          <Col span={24}>
            <Card bordered={true}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Space size="large">
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <div style={{ 
                      width: 12, height: 12, borderRadius: '50%', 
                      background: config?.connection_ok ? '#52c41a' : '#ff4d4f',
                      marginRight: 8 
                    }} />
                    <Text strong style={{ fontSize: 16 }}>
                      {config?.connection_ok ? '服务在线' : '服务未连接'}
                    </Text>
                  </div>
                  <Text type="secondary">Base URL: {config?.base_url}</Text>
                </Space>
                <Space>
                  <Button icon={<ReloadOutlined />} onClick={loadConfig} loading={loading}>刷新状态</Button>
                </Space>
              </div>
            </Card>
          </Col>

          {/* Configuration Card */}
          <Col xs={24} lg={8}>
            <Card title={<Space><ApiOutlined />连接设置</Space>} bordered={true} style={{ height: '100%' }}>
              <Form form={form} layout="vertical">
                <Form.Item name="base_url" label="Ollama Base URL" rules={[{ required: true }]}>
                  <Input placeholder="http://localhost:11434" />
                </Form.Item>
                <Form.Item name="timeout_seconds" label="超时时间 (秒)">
                  <InputNumber min={10} max={300} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="temperature" label="默认 Temperature">
                  <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="default_model" label="默认模型">
                  <Select 
                    showSearch 
                    placeholder="选择默认模型"
                    options={models.map(m => ({ label: m.name, value: m.name }))}
                  />
                </Form.Item>
                
                <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
                  <Button 
                    type="primary" 
                    icon={<SaveOutlined />} 
                    onClick={handleSaveConfig} 
                    block
                  >
                    保存配置
                  </Button>
                  <Button 
                    icon={<CloudServerOutlined />} 
                    onClick={handleTestConnection} 
                    loading={testing}
                    block
                  >
                    测试连接
                  </Button>
                </div>
              </Form>
            </Card>
          </Col>

          {/* Models Card */}
          <Col xs={24} lg={16}>
            <Card 
              title={
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space><CloudServerOutlined />本地模型管理</Space>
                  <Space>
                    {viewMode === 'pulls' ? (
                      <Button 
                        size="small" 
                        type="text"
                        icon={<ArrowLeftOutlined />} 
                        onClick={() => setViewMode('models')}
                      >
                        返回模型列表
                      </Button>
                    ) : (
                      <Button 
                        size="small" 
                        type="text"
                        icon={<HistoryOutlined />} 
                        onClick={() => setViewMode('pulls')}
                      >
                        查看进度
                      </Button>
                    )}
                  </Space>
                </div>
              } 
              bordered={true} 
              style={{ height: '100%' }}
            >
              {viewMode === 'models' ? (
                <>
                  <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
                    <Input 
                      placeholder="输入模型名称 (如: llama3:latest)" 
                      value={pullModelName}
                      onChange={e => setPullModelName(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <Button 
                      type="primary" 
                      icon={<DownloadOutlined />} 
                      onClick={handlePullModel}
                      loading={pulling}
                    >
                      Pull 模型
                    </Button>
                  </div>

                  <Table 
                    dataSource={models} 
                    columns={modelColumns} 
                    rowKey="name" 
                    pagination={false} 
                    size="small"
                    scroll={{ y: 360 }}
                  />
                  
                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      提示: Pull 操作可能耗时较长，请耐心等待。
                    </Text>
                  </div>
                </>
              ) : (
                <>
                  <Table 
                    dataSource={pullJobs} 
                    columns={pullJobColumns} 
                    rowKey="id" 
                    pagination={false} 
                    size="small"
                    scroll={{ y: 400 }}
                  />
                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      提示: 任务进度会自动刷新。
                    </Text>
                  </div>
                </>
              )}
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  );
};

export default OllamaConfigPanel;
