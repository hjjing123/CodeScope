import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ModelSelector from './ModelSelector';
import * as aiService from '../../services/ai';

vi.mock('../../services/ai', () => ({
  getMyAIModelCatalog: vi.fn(),
}));

const mockedAI = vi.mocked(aiService);

describe('ModelSelector', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockedAI.getMyAIModelCatalog.mockResolvedValue({
      items: [
        {
          provider_source: 'system_ollama',
          provider_id: null,
          provider_key: 'system_ollama',
          provider_label: 'System Ollama',
          provider_type: 'ollama_local',
          enabled: true,
          default_model: 'qwen2.5-coder:3b-instruct-q4_K_M',
          available: true,
          connection_ok: true,
          model_catalog_ok: true,
          allow_manual_model_input: false,
          source_label: '本地',
          status_label: '可用',
          status_reason: null,
          models: [
            {
              name: 'qwen2.5-coder:3b-instruct-q4_K_M',
              label: 'qwen2.5-coder:3b-instruct-q4_K_M',
              is_default: true,
              selectable: true,
              details: {},
            },
          ],
        },
        {
          provider_source: 'user_external',
          provider_id: 'provider-1',
          provider_key: null,
          provider_label: 'models/gemini-2.5-flash',
          provider_type: 'openai_compatible',
          enabled: true,
          default_model: 'models/gemini-2.5-flash',
          available: true,
          connection_ok: true,
          model_catalog_ok: true,
          allow_manual_model_input: false,
          source_label: '外部',
          status_label: '可用',
          status_reason: null,
          models: [
            {
              name: 'models/gemini-2.5-flash',
              label: 'models/gemini-2.5-flash',
              is_default: true,
              selectable: true,
              details: {},
            },
          ],
        },
      ],
      default_selection: {
        ai_source: 'system_ollama',
        ai_provider_id: null,
        ai_model: 'qwen2.5-coder:3b-instruct-q4_K_M',
      },
    } as never);
  });

  it('shows fixed label for personal provider group', async () => {
    render(
      <ModelSelector
        value={{
          ai_source: 'system_ollama',
          ai_provider_id: undefined,
          ai_model: 'qwen2.5-coder:3b-instruct-q4_K_M',
        }}
        onChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(mockedAI.getMyAIModelCatalog).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByText('qwen2.5-coder:3b-instruct-q4_K_M'));

    expect(await screen.findByText('本地模型')).toBeInTheDocument();
    expect(await screen.findByText('个人模型')).toBeInTheDocument();
  });
});
