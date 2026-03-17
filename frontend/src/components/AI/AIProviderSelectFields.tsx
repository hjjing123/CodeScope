import React, { useMemo } from 'react';
import { Alert, Input, Radio, Select, Space, Tag, Typography } from 'antd';
import type { AIProviderOptionsPayload, AIProviderSelectionRequest, AISource, UserAIProviderPayload } from '../../types/ai';

const { Text } = Typography;

interface AIProviderSelectFieldsProps {
  options: AIProviderOptionsPayload | null;
  value: AIProviderSelectionRequest;
  onChange: (value: AIProviderSelectionRequest) => void;
  disabled?: boolean;
  compact?: boolean;
}

const firstEnabledProvider = (providers: UserAIProviderPayload[]) => providers[0];

const AIProviderSelectFields: React.FC<AIProviderSelectFieldsProps> = ({
  options,
  value,
  onChange,
  disabled = false,
  compact = false,
}) => {
  const availableSources = useMemo(() => {
    if (!options) {
      return [] as AISource[];
    }
    const next: AISource[] = [];
    if (options.user_providers.length > 0) {
      next.push('user_external');
    }
    if (options.system_ollama.available) {
      next.push('system_ollama');
    }
    return next;
  }, [options]);

  const resolvedSource = useMemo<AISource | undefined>(() => {
    if (value.ai_source && availableSources.includes(value.ai_source)) {
      return value.ai_source;
    }
    const fallback = options?.default_selection?.ai_source;
    if (fallback === 'user_external' || fallback === 'system_ollama') {
      return fallback;
    }
    return availableSources[0];
  }, [availableSources, options?.default_selection, value.ai_source]);

  const selectedExternalProvider = useMemo(() => {
    if (!options || resolvedSource !== 'user_external') {
      return null;
    }
    return (
      options.user_providers.find((item) => item.id === value.ai_provider_id) ||
      options.user_providers.find((item) => item.is_default) ||
      firstEnabledProvider(options.user_providers) ||
      null
    );
  }, [options, resolvedSource, value.ai_provider_id]);

  const systemModelOptions = options?.system_ollama.published_models ?? [];

  const handleSourceChange = (nextSource: AISource) => {
    if (!options) {
      return;
    }
    if (nextSource === 'user_external') {
      const provider = options.user_providers.find((item) => item.is_default) || firstEnabledProvider(options.user_providers);
      onChange({
        ai_source: nextSource,
        ai_provider_id: provider?.id,
        ai_model: provider?.default_model,
      });
      return;
    }
    onChange({
      ai_source: nextSource,
      ai_provider_id: undefined,
      ai_model: options.system_ollama.default_model || options.system_ollama.published_models[0],
    });
  };

  const handleProviderChange = (providerId: string) => {
    if (!options) {
      return;
    }
    const provider = options.user_providers.find((item) => item.id === providerId);
    onChange({
      ai_source: 'user_external',
      ai_provider_id: providerId,
      ai_model: provider?.default_model || value.ai_model,
    });
  };

  if (!options) {
    return (
      <Alert
        type="info"
        showIcon
        message="正在加载 AI Provider 配置"
        description="加载完成后可选择系统 Ollama 或你的外部 API。"
      />
    );
  }

  if (availableSources.length === 0) {
    return (
      <Alert
        type="warning"
        showIcon
        message="暂无可用 AI Provider"
        description="请先配置你的外部 API，或联系管理员启用系统 Ollama。"
      />
    );
  }

  return (
    <Space direction="vertical" size={compact ? 8 : 12} style={{ width: '100%' }}>
      <div>
        <Text strong style={{ display: 'block', marginBottom: 8 }}>
          AI 来源
        </Text>
        <Radio.Group
          value={resolvedSource}
          onChange={(event) => handleSourceChange(event.target.value as AISource)}
          disabled={disabled}
          optionType="button"
          buttonStyle="solid"
        >
          {options.user_providers.length > 0 ? (
            <Radio.Button value="user_external">我的外部 API</Radio.Button>
          ) : null}
          {options.system_ollama.available ? (
            <Radio.Button value="system_ollama">系统 Ollama</Radio.Button>
          ) : null}
        </Radio.Group>
      </div>

      {resolvedSource === 'user_external' ? (
        <Space direction="vertical" size={compact ? 8 : 12} style={{ width: '100%' }}>
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              Provider 配置
            </Text>
            <Select
              value={selectedExternalProvider?.id}
              onChange={handleProviderChange}
              disabled={disabled}
              style={{ width: '100%' }}
              options={options.user_providers.map((item) => ({
                label: `${item.display_name} · ${item.vendor_name}`,
                value: item.id,
              }))}
            />
            {selectedExternalProvider ? (
              <Space size={[8, 8]} wrap style={{ marginTop: 8 }}>
                <Tag color={selectedExternalProvider.is_default ? 'green' : 'default'}>
                  {selectedExternalProvider.is_default ? '默认' : '可用'}
                </Tag>
                <Tag>{selectedExternalProvider.api_key_masked || '已配置密钥'}</Tag>
                <Tag>{selectedExternalProvider.base_url}</Tag>
              </Space>
            ) : null}
          </div>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              模型名称
            </Text>
            <Input
              value={value.ai_model ?? selectedExternalProvider?.default_model ?? ''}
              onChange={(event) =>
                onChange({
                  ai_source: 'user_external',
                  ai_provider_id: selectedExternalProvider?.id,
                  ai_model: event.target.value,
                })
              }
              disabled={disabled}
              placeholder="例如 deepseek-chat / gpt-4.1-mini"
            />
          </div>
        </Space>
      ) : null}

      {resolvedSource === 'system_ollama' ? (
        <Space direction="vertical" size={compact ? 8 : 12} style={{ width: '100%' }}>
          <Alert
            type="success"
            showIcon
            message={options.system_ollama.display_name}
            description="使用管理员发布的系统本地模型，不需要个人 API Key。"
          />
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              模型名称
            </Text>
            {systemModelOptions.length > 0 ? (
              <Select
                value={value.ai_model ?? options.system_ollama.default_model ?? systemModelOptions[0]}
                onChange={(nextValue) =>
                  onChange({
                    ai_source: 'system_ollama',
                    ai_provider_id: undefined,
                    ai_model: nextValue,
                  })
                }
                disabled={disabled}
                style={{ width: '100%' }}
                showSearch
                options={systemModelOptions.map((item) => ({ label: item, value: item }))}
              />
            ) : (
              <Input
                value={value.ai_model ?? options.system_ollama.default_model ?? ''}
                onChange={(event) =>
                  onChange({
                    ai_source: 'system_ollama',
                    ai_provider_id: undefined,
                    ai_model: event.target.value,
                  })
                }
                disabled={disabled}
                placeholder="输入系统 Ollama 模型名称"
              />
            )}
          </div>
        </Space>
      ) : null}
    </Space>
  );
};

export default AIProviderSelectFields;
