export interface UserProviderPreset {
  value: string;
  label: string;
  displayNameExample: string;
  baseUrl?: string;
  baseUrlPlaceholder: string;
  baseUrlHelp?: string;
  apiKeyPlaceholder: string;
  defaultModel?: string;
  defaultModelPlaceholder: string;
  defaultModelHelp?: string;
}

export interface ProviderFormDraft {
  display_name?: string;
  vendor_name?: string;
  base_url?: string;
  default_model?: string;
}

export const DEFAULT_PROVIDER_VENDOR = 'OpenAI Compatible';

export const USER_PROVIDER_PRESETS: UserProviderPreset[] = [
  {
    value: 'OpenAI Compatible',
    label: 'OpenAI Compatible',
    displayNameExample: '我的 OpenAI Compatible',
    baseUrlPlaceholder: '例如: https://api.openai.com/v1',
    apiKeyPlaceholder: 'sk-...',
    defaultModelPlaceholder: '例如: gpt-4.1-mini',
    defaultModelHelp: '适用于标准 OpenAI-compatible 接口，模型名按服务商文档填写。',
  },
  {
    value: 'Google Gemini',
    label: 'Google Gemini',
    displayNameExample: '我的 Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    baseUrlPlaceholder:
      '例如: https://generativelanguage.googleapis.com/v1beta/openai',
    baseUrlHelp: '使用 Gemini AI Studio 的 OpenAI-compatible 兼容地址。',
    apiKeyPlaceholder: 'AIza... 或 Gemini API Key',
    defaultModel: 'gemini-2.5-flash',
    defaultModelPlaceholder: '例如: gemini-2.5-flash',
    defaultModelHelp:
      '演示推荐 gemini-2.5-flash；如需更强推理可切换为 gemini-2.5-pro。',
  },
  {
    value: 'DeepSeek',
    label: 'DeepSeek',
    displayNameExample: '我的 DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    baseUrlPlaceholder: '例如: https://api.deepseek.com/v1',
    apiKeyPlaceholder: 'sk-...',
    defaultModel: 'deepseek-chat',
    defaultModelPlaceholder: '例如: deepseek-chat',
    defaultModelHelp: '常用模型为 deepseek-chat 或 deepseek-reasoner。',
  },
  {
    value: 'OpenRouter',
    label: 'OpenRouter',
    displayNameExample: '我的 OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    baseUrlPlaceholder: '例如: https://openrouter.ai/api/v1',
    apiKeyPlaceholder: 'sk-or-v1-...',
    defaultModel: 'openai/gpt-4.1-mini',
    defaultModelPlaceholder: '例如: openai/gpt-4.1-mini',
    defaultModelHelp: '模型名称通常包含厂商前缀，如 openai/gpt-4.1-mini。',
  },
  {
    value: 'Azure OpenAI',
    label: 'Azure OpenAI',
    displayNameExample: '我的 Azure OpenAI',
    baseUrlPlaceholder: '例如: https://{resource}.openai.azure.com/openai/v1',
    apiKeyPlaceholder: 'Azure API Key',
    defaultModelPlaceholder: '例如: gpt-4.1-mini',
    defaultModelHelp: '请按 Azure OpenAI 当前文档填写兼容地址与模型名称。',
  },
  {
    value: 'Anthropic',
    label: 'Anthropic',
    displayNameExample: '我的 Anthropic',
    baseUrlPlaceholder: '例如: https://api.anthropic.com/v1',
    apiKeyPlaceholder: 'sk-ant-...',
    defaultModelPlaceholder: '例如: claude-3-5-sonnet-latest',
    defaultModelHelp:
      '当前平台底层按 OpenAI-compatible 方式接入，如需原生 Anthropic 协议需后续扩展。',
  },
];

export const getUserProviderPreset = (
  vendorName: string | null | undefined
): UserProviderPreset => {
  const normalizedName = String(vendorName || '').trim();
  return (
    USER_PROVIDER_PRESETS.find((item) => item.value === normalizedName) ||
    USER_PROVIDER_PRESETS[0]
  );
};

const shouldApplyPresetValue = (
  currentValue: string | undefined,
  previousPresetValue: string | undefined
): boolean => {
  const normalizedCurrent = String(currentValue || '').trim();
  const normalizedPrevious = String(previousPresetValue || '').trim();
  return !normalizedCurrent || (!!normalizedPrevious && normalizedCurrent === normalizedPrevious);
};

export const buildProviderPresetPatch = ({
  nextVendorName,
  previousVendorName,
  currentValues,
}: {
  nextVendorName: string;
  previousVendorName?: string;
  currentValues: ProviderFormDraft;
}): ProviderFormDraft => {
  const nextPreset = getUserProviderPreset(nextVendorName);
  const previousPreset = previousVendorName
    ? getUserProviderPreset(previousVendorName)
    : undefined;

  const patch: ProviderFormDraft = {
    vendor_name: nextPreset.value,
  };

  if (
    nextPreset.value === 'Google Gemini' &&
    nextPreset.baseUrl &&
    shouldApplyPresetValue(currentValues.base_url, previousPreset?.baseUrl)
  ) {
    patch.base_url = nextPreset.baseUrl;
  }
  return patch;
};
