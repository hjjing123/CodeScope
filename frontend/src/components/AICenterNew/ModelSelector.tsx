import React, { useEffect, useState, useMemo } from 'react';
import { Dropdown, Typography, Space, Tag, Spin, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined, CheckOutlined } from '@ant-design/icons';
import { getMyAIModelCatalog } from '../../services/ai';
import type { AIModelCatalogPayload, AIProviderSelectionRequest } from '../../types/ai';

const { Text } = Typography;
type MenuItem = NonNullable<MenuProps['items']>[number];

const MODEL_CATALOG_RETRY_DELAY_MS = 5000;
const MODEL_CATALOG_MAX_RETRIES = 12;

interface ModelSelectorProps {
  value?: AIProviderSelectionRequest;
  onChange?: (value: AIProviderSelectionRequest) => void;
  disabled?: boolean;
}

const getModelKey = (source: string, providerId: string | null, model: string) => {
  return JSON.stringify({ s: source, p: providerId, m: model });
};

const parseModelKey = (key: string): AIProviderSelectionRequest => {
  try {
    const { s, p, m } = JSON.parse(key);
    return {
      ai_source: s,
      ai_provider_id: p,
      ai_model: m,
    };
  } catch (e) {
    return {};
  }
};

const getModelDetailLabel = (details: Record<string, unknown> | undefined): string | null => {
  if (!details) {
    return null;
  }

  const family = typeof details.family === 'string' ? details.family.trim() : '';
  const parameterSize =
    typeof details.parameter_size === 'string' || typeof details.parameter_size === 'number'
      ? String(details.parameter_size).trim()
      : '';
  const parts = [family, parameterSize].filter(Boolean);

  return parts.length > 0 ? parts.join(' · ') : null;
};

const ModelSelector: React.FC<ModelSelectorProps> = ({ value, onChange, disabled }) => {
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<AIModelCatalogPayload | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;
    let retryTimer: number | null = null;

    const fetchCatalog = async (attempt = 0) => {
      setLoading(true);
      try {
        const data = await getMyAIModelCatalog();
        if (isMounted) {
          setCatalog(data);
          
          // Only auto-select if there is no value at all AND we have a default selection.
          // Don't auto-select if value is partially set (e.g. empty object).
          const isValueEmpty = !value || Object.keys(value).length === 0;
          if (isValueEmpty && data.default_selection && onChange) {
            onChange(data.default_selection as AIProviderSelectionRequest);
          }

          const hasAvailableModels = data.items.some(
            (provider) => provider.models && provider.models.length > 0
          );
          if (!hasAvailableModels && attempt < MODEL_CATALOG_MAX_RETRIES) {
            retryTimer = window.setTimeout(() => {
              void fetchCatalog(attempt + 1);
            }, MODEL_CATALOG_RETRY_DELAY_MS);
          }
        }
      } catch (error) {
        console.error('Failed to load model catalog', error);
        if (isMounted && attempt < MODEL_CATALOG_MAX_RETRIES) {
          retryTimer = window.setTimeout(() => {
            void fetchCatalog(attempt + 1);
          }, MODEL_CATALOG_RETRY_DELAY_MS);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    void fetchCatalog();
    return () => {
      isMounted = false;
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }
    };
  }, []);

  const selectedKey = useMemo(() => {
    if (!value?.ai_model) return undefined;
    return getModelKey(value.ai_source || '', value.ai_provider_id || null, value.ai_model);
  }, [value]);

  const hasModels = useMemo(() => {
    if (!catalog?.items) return false;
    // Check if any provider has models
    return catalog.items.some(provider => provider.models && provider.models.length > 0);
  }, [catalog]);

  const currentLabel = useMemo(() => {
    if (!catalog) return '加载中...';
    if (!hasModels) return '无模型可用';
    
    if (!value?.ai_model) return '选择模型';
    
    for (const provider of catalog.items) {
      if (
        provider.provider_source === value.ai_source && 
        (provider.provider_id === value.ai_provider_id || (!provider.provider_id && !value.ai_provider_id))
      ) {
        const model = provider.models.find(m => m.name === value.ai_model);
        if (model) return `${model.label}`;
      }
    }
    return value.ai_model;
  }, [catalog, value, hasModels]);

  const menuItems = useMemo<NonNullable<MenuProps['items']>>(() => {
    if (!catalog || !hasModels) {
      return [{
        key: 'no-model',
        label: <Text type="secondary" style={{ padding: '8px 12px', display: 'block' }}>无模型可用，请先在设置中配置</Text>,
        disabled: true
      }];
    }
    
    return catalog.items.flatMap((provider): MenuItem[] => {
      // Skip providers with no models
      if (!provider.models || provider.models.length === 0) return [];

      const options = provider.models.map<MenuItem>((model) => {
        const key = getModelKey(provider.provider_source, provider.provider_id, model.name);
        const isSelected = key === selectedKey;
        const detailLabel = getModelDetailLabel(model.details);

        return {
          key,
          label: (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '4px 0', maxWidth: 220 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Tooltip title={model.label} placement="left">
                  <Text style={{ 
                    fontWeight: isSelected ? 600 : 400, 
                    fontSize: 14,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: 180
                  }}>
                    {model.label}
                  </Text>
                </Tooltip>
                {isSelected && <CheckOutlined style={{ color: '#1890ff', fontSize: 14, flexShrink: 0 }} />}
              </div>
              {detailLabel ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {detailLabel}
                </Text>
              ) : null}
            </div>
          ),
          onClick: () => {
            if (onChange) onChange(parseModelKey(key));
            setOpen(false);
          },
        };
      });

      const groupTitle: MenuItem = {
        key: `group-${provider.provider_source}-${provider.provider_id || 'system'}`,
        type: 'group',
        label: (
          <Space>
            {provider.provider_label}
            {provider.provider_source === 'system_ollama' && (
              <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '16px', borderRadius: 4 }}>
                本地
              </Tag>
            )}
          </Space>
        ),
        children: options,
      };

      return [groupTitle];
    });
  }, [catalog, selectedKey, onChange]);

  if (loading && !catalog) {
    return <Spin size="small" />;
  }

  return (
    <Dropdown 
      menu={{ 
        items: menuItems,
        style: { 
          maxHeight: 400, 
          overflowY: 'auto', 
          width: 260, 
          padding: 8,
          borderRadius: 12,
          boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          border: '1px solid #f0f0f0'
        }
      }} 
      trigger={['click']}
      open={open}
      onOpenChange={setOpen}
      disabled={disabled}
    >
      <div 
        style={{ 
          cursor: disabled ? 'not-allowed' : 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '6px 12px',
          borderRadius: 8,
          transition: 'all 0.2s',
          background: open ? 'rgba(0,0,0,0.04)' : 'transparent',
          color: '#333',
          maxWidth: 300
        }}
        className="model-selector-trigger"
        onMouseEnter={(e) => {
          if (!disabled && !open) e.currentTarget.style.background = 'rgba(0,0,0,0.04)';
        }}
        onMouseLeave={(e) => {
          if (!disabled && !open) e.currentTarget.style.background = 'transparent';
        }}
      >
        <Tooltip title={currentLabel}>
          <span style={{ 
            fontWeight: 600, 
            fontSize: 18, 
            color: '#202123',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: 240
          }}>
            {currentLabel}
          </span>
        </Tooltip>
        <DownOutlined style={{ fontSize: 12, color: '#8e8ea0', marginLeft: 4, flexShrink: 0 }} />
      </div>
    </Dropdown>
  );
};

export default ModelSelector;
