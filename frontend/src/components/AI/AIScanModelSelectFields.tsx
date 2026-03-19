import React, { useMemo } from 'react';
import { Alert, Input, Select, Space, Tag, Typography } from 'antd';
import type {
  AIModelCatalogPayload,
  AIModelCatalogProviderPayload,
  AIProviderSelectionRequest,
} from '../../types/ai';

const { Text } = Typography;

interface AIScanModelSelectFieldsProps {
  catalog: AIModelCatalogPayload | null;
  value: AIProviderSelectionRequest;
  onChange: (value: AIProviderSelectionRequest) => void;
  disabled?: boolean;
}

const getProviderKey = (provider: AIModelCatalogProviderPayload) =>
  JSON.stringify({ s: provider.provider_source, p: provider.provider_id });

const getModelOptionKey = (
  provider: AIModelCatalogProviderPayload,
  modelName: string,
  mode: 'model' | 'manual'
) => JSON.stringify({ s: provider.provider_source, p: provider.provider_id, m: modelName, mode });

const parseOptionKey = (key: string) => {
  try {
    const payload = JSON.parse(key) as {
      s?: string;
      p?: string | null;
      m?: string;
      mode?: 'model' | 'manual';
    };
    return payload;
  } catch {
    return {};
  }
};

const glowTagStyle = (color: string) => ({
  margin: 0,
  color,
  borderColor: `${color}55`,
  background: `${color}12`,
  boxShadow: `0 0 10px ${color}33`,
});

const statusColorMap: Record<string, string> = {
  '可用': '#22c55e',
  '可用，需手填模型': '#22c55e',
  '目录不可用，需手填模型': '#f59e0b',
  '连接失败': '#ef4444',
  '认证失败': '#ef4444',
  '未发布模型': '#94a3b8',
  '不可用': '#ef4444',
};

const AIScanModelSelectFields: React.FC<AIScanModelSelectFieldsProps> = ({
  catalog,
  value,
  onChange,
  disabled = false,
}) => {
  const providers = catalog?.items ?? [];

  const selectedProvider = useMemo(() => {
    return (
      providers.find(
        (provider) =>
          provider.provider_source === value.ai_source &&
          ((provider.provider_id ?? null) === (value.ai_provider_id ?? null))
      ) || null
    );
  }, [providers, value.ai_provider_id, value.ai_source]);

  const manualMode = Boolean(
    selectedProvider?.allow_manual_model_input &&
      ((selectedProvider.models?.length ?? 0) === 0 ||
        !selectedProvider?.models?.some((item) => item.name === value.ai_model))
  );

  const selectedValue = useMemo(() => {
    if (!selectedProvider) {
      return undefined;
    }
    const matchedModel = selectedProvider.models.find((item) => item.name === value.ai_model);
    if (matchedModel) {
      return getModelOptionKey(selectedProvider, matchedModel.name, 'model');
    }
    if (manualMode) {
      return getModelOptionKey(selectedProvider, '__manual__', 'manual');
    }
    return undefined;
  }, [manualMode, selectedProvider, value.ai_model]);

  const availableProviderCount = providers.filter((item) => item.available).length;

  const selectOptions = useMemo(() => {
    return providers.map((provider) => {
      const statusColor = statusColorMap[provider.status_label || ''] || '#94a3b8';
      const providerOptions = provider.models.map((model) => ({
        label: (
          <Space size={8} style={{ width: '100%', justifyContent: 'space-between' }}>
            <span>{model.label}</span>
            <Space size={6}>
              <Tag style={glowTagStyle(provider.source_label === '本地' ? '#3b82f6' : '#8b5cf6')}>
                {provider.source_label}
              </Tag>
              {model.is_default ? <Tag color="green">默认</Tag> : null}
            </Space>
          </Space>
        ),
        value: getModelOptionKey(provider, model.name, 'model'),
        searchLabel: `${provider.provider_label} ${provider.source_label || ''} ${model.label}`,
        disabled: disabled || !provider.available || model.selectable === false,
      }));

      if (provider.allow_manual_model_input) {
        providerOptions.push({
          label: (
            <Space>
              <span>手动输入模型名称</span>
              <Tag color="gold">手填</Tag>
            </Space>
          ),
          value: getModelOptionKey(provider, '__manual__', 'manual'),
          searchLabel: `${provider.provider_label} 手动输入模型名称`,
          disabled: disabled || !provider.available,
        });
      }

      if (providerOptions.length === 0) {
        providerOptions.push({
          label: <Text type="secondary">暂无可选模型</Text>,
          value: `${getProviderKey(provider)}-empty`,
          searchLabel: `${provider.provider_label} 暂无可选模型`,
          disabled: true,
        });
      }

      return {
        label: (
          <Space size={8} wrap>
            <Text strong>{provider.provider_label}</Text>
            <Tag style={glowTagStyle(provider.source_label === '本地' ? '#3b82f6' : '#8b5cf6')}>
              {provider.source_label || '来源'}
            </Tag>
            <Tag style={glowTagStyle(statusColor)}>{provider.status_label || '未知'}</Tag>
          </Space>
        ),
        options: providerOptions,
      };
    });
  }, [providers, disabled]);

  const handleSelectChange = (nextValue: string) => {
    const parsed = parseOptionKey(nextValue);
    const provider = providers.find(
      (item) =>
        item.provider_source === parsed.s &&
        ((item.provider_id ?? null) === (parsed.p ?? null))
    );
    if (!provider) {
      return;
    }
    if (parsed.mode === 'manual') {
      onChange({
        ai_source: provider.provider_source as AIProviderSelectionRequest['ai_source'],
        ai_provider_id: provider.provider_id ?? undefined,
        ai_model: value.ai_model || provider.default_model || '',
      });
      return;
    }
    onChange({
      ai_source: provider.provider_source as AIProviderSelectionRequest['ai_source'],
      ai_provider_id: provider.provider_id ?? undefined,
      ai_model: parsed.m || provider.default_model || '',
    });
  };

  if (!catalog) {
    return <Alert type="info" showIcon message="正在加载 AI 模型目录" />;
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {availableProviderCount === 0 ? (
        <Alert
          type="warning"
          showIcon
          message="当前没有可用的 AI 模型"
          description="请检查本地模型或外部 Provider 连接状态。"
        />
      ) : null}

      <div>
        <Text strong style={{ display: 'block', marginBottom: 8 }}>
          选择用于扫描后 AI 研判的模型
        </Text>
        <Select
          value={selectedValue}
          onChange={handleSelectChange}
          disabled={disabled}
          style={{ width: '100%' }}
          placeholder="请选择模型"
          optionFilterProp="searchLabel"
          options={selectOptions}
          showSearch
        />
      </div>

      {selectedProvider ? (
        <Alert
          type={selectedProvider.available ? 'success' : 'error'}
          showIcon
          message={`${selectedProvider.provider_label} · ${selectedProvider.status_label || '未知状态'}`}
          description={selectedProvider.status_reason || '可直接用于扫描后 AI 研判。'}
        />
      ) : null}

      {manualMode && selectedProvider ? (
        <div>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            手动填写调用模型
          </Text>
          <Input
            value={value.ai_model ?? ''}
            onChange={(event) =>
              onChange({
                ai_source: selectedProvider.provider_source as AIProviderSelectionRequest['ai_source'],
                ai_provider_id: selectedProvider.provider_id ?? undefined,
                ai_model: event.target.value,
              })
            }
            disabled={disabled || !selectedProvider.available}
            placeholder="例如 deepseek-chat / gpt-4.1-mini"
          />
        </div>
      ) : null}
    </Space>
  );
};

export default AIScanModelSelectFields;
