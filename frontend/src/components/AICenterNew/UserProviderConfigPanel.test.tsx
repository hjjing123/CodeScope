import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import UserProviderConfigPanel from './UserProviderConfigPanel';
import * as aiService from '../../services/ai';

vi.mock('../../services/ai', () => ({
  listMyAIProviders: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createMyAIProvider: vi.fn().mockResolvedValue({ id: 'provider-1' }),
  updateMyAIProvider: vi.fn(),
  deleteMyAIProvider: vi.fn(),
  testMyAIProvider: vi.fn(),
  testMyAIProviderDraft: vi.fn(),
}));

const mockedAI = vi.mocked(aiService);

describe('UserProviderConfigPanel', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockedAI.listMyAIProviders.mockResolvedValue({ items: [], total: 0 });
    mockedAI.createMyAIProvider.mockResolvedValue({ id: 'provider-1' } as never);
    mockedAI.testMyAIProviderDraft.mockImplementation(async (payload) => ({
      ok: !payload.verify_selected_model || payload.selected_model === 'gemini-2.5-flash',
      provider_type: 'openai_compatible',
      provider_label: 'Google Gemini',
      base_url: payload.base_url,
      vendor_name: payload.vendor_name,
      connection_ok: true,
      model_catalog_ok: false,
      allow_manual_model_input: true,
      status_label: '目录不可用，需手填模型',
      status_reason: '模型目录接口不可用，请手动填写调用模型名称。',
      model_count: 0,
      models: [],
      selected_model_verification: payload.verify_selected_model
        ? {
            model: payload.selected_model,
            ok: payload.selected_model === 'gemini-2.5-flash',
            message:
              payload.selected_model === 'gemini-2.5-flash'
                ? '模型验证成功'
                : '模型不可用',
            error_code: payload.selected_model === 'gemini-2.5-flash' ? null : 'AI_PROVIDER_HTTP_ERROR',
            response_preview: payload.selected_model === 'gemini-2.5-flash' ? 'OK' : null,
          }
        : null,
    }) as never);
  });

  it('creates provider after draft test and selected-model verification', async () => {
    render(<UserProviderConfigPanel onBack={vi.fn()} />);

    await waitFor(() => {
      expect(mockedAI.listMyAIProviders).toHaveBeenCalled();
    });

    expect(screen.queryByText('显示名称')).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('例如: https://api.openai.com/v1'), {
      target: { value: 'https://api.example.com/v1' },
    });
    fireEvent.change(screen.getByPlaceholderText('sk-...'), {
      target: { value: 'sk-demo-key' },
    });

    fireEvent.click(screen.getByRole('button', { name: '测试并获取模型' }));

    await waitFor(() => {
      expect(mockedAI.testMyAIProviderDraft).toHaveBeenCalledWith({
        vendor_name: 'OpenAI Compatible',
        base_url: 'https://api.example.com/v1',
        api_key: 'sk-demo-key',
        timeout_seconds: 60,
      });
    });

    const modelInput = await screen.findByPlaceholderText('例如: gpt-4.1-mini');
    await waitFor(() => {
      expect(modelInput).not.toBeDisabled();
    });
    fireEvent.change(modelInput, {
      target: { value: 'gemini-2.5-flash' },
    });

    const verifyButton = screen.getByRole('button', { name: '验证当前模型' });
    await waitFor(() => {
      expect(verifyButton).not.toBeDisabled();
    });
    fireEvent.click(verifyButton);

    await waitFor(() => {
      expect(mockedAI.testMyAIProviderDraft).toHaveBeenCalledWith({
        vendor_name: 'OpenAI Compatible',
        base_url: 'https://api.example.com/v1',
        api_key: 'sk-demo-key',
        timeout_seconds: 60,
        selected_model: 'gemini-2.5-flash',
        verify_selected_model: true,
      });
    });

    fireEvent.click(screen.getByRole('button', { name: /创建 Provider/ }));

    await waitFor(() => {
      expect(mockedAI.createMyAIProvider).toHaveBeenCalledTimes(1);
    });

    const payload = mockedAI.createMyAIProvider.mock.calls[0][0];
    expect(payload).not.toHaveProperty('display_name');
    expect(payload.default_model).toBe('gemini-2.5-flash');
  });
});
