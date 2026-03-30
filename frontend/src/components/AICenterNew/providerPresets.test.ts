import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PROVIDER_VENDOR,
  buildProviderPresetPatch,
  getUserProviderPreset,
} from './providerPresets';

describe('providerPresets', () => {
  it('returns Gemini preset metadata', () => {
    const preset = getUserProviderPreset('Google Gemini');

    expect(preset.baseUrl).toBe(
      'https://generativelanguage.googleapis.com/v1beta/openai'
    );
    expect(preset.defaultModel).toBe('gemini-2.5-flash');
  });

  it('fills Gemini base URL when switching from generic OpenAI preset', () => {
    const patch = buildProviderPresetPatch({
      nextVendorName: 'Google Gemini',
      previousVendorName: DEFAULT_PROVIDER_VENDOR,
      currentValues: {
        display_name: '',
        vendor_name: DEFAULT_PROVIDER_VENDOR,
        base_url: '',
        default_model: '',
      },
    });

    expect(patch).toEqual({
      vendor_name: 'Google Gemini',
      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    });
  });

  it('only auto-fills Gemini base URL', () => {
    const patch = buildProviderPresetPatch({
      nextVendorName: 'DeepSeek',
      previousVendorName: DEFAULT_PROVIDER_VENDOR,
      currentValues: {
        display_name: '',
        vendor_name: DEFAULT_PROVIDER_VENDOR,
        base_url: '',
        default_model: '',
      },
    });

    expect(patch).toEqual({
      vendor_name: 'DeepSeek',
    });
  });

  it('replaces prior Gemini-compatible base URL but preserves custom input', () => {
    const switchedPatch = buildProviderPresetPatch({
      nextVendorName: 'Google Gemini',
      previousVendorName: 'DeepSeek',
      currentValues: {
        display_name: '我的 DeepSeek',
        vendor_name: 'DeepSeek',
        base_url: 'https://api.deepseek.com/v1',
        default_model: 'deepseek-chat',
      },
    });
    expect(switchedPatch).toEqual({
      vendor_name: 'Google Gemini',
      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    });

    const previousGeminiBaseUrl =
      'https://generativelanguage.googleapis.com/v1beta/openai'
    const preservedPatch = buildProviderPresetPatch({
      nextVendorName: 'Google Gemini',
      previousVendorName: 'DeepSeek',
      currentValues: {
        display_name: '答辩演示 Gemini',
        vendor_name: 'DeepSeek',
        base_url: 'https://demo.example.com/openai',
        default_model: 'custom-model',
      },
    });
    expect(preservedPatch).toEqual({
      vendor_name: 'Google Gemini',
    });

    const retainedGeminiPatch = buildProviderPresetPatch({
      nextVendorName: 'Google Gemini',
      previousVendorName: 'Google Gemini',
      currentValues: {
        display_name: '我的 Gemini',
        vendor_name: 'Google Gemini',
        base_url: previousGeminiBaseUrl,
        default_model: 'custom-model',
      },
    });
    expect(retainedGeminiPatch).toEqual({
      vendor_name: 'Google Gemini',
      base_url: previousGeminiBaseUrl,
    });
  });
});
