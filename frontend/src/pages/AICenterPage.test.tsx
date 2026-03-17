import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AICenterPage from './AICenterPage';
import * as aiService from '../services/ai';

const buildSession = () => ({
  id: 'session-1',
  session_mode: 'general' as const,
  finding_id: null,
  project_id: null,
  version_id: null,
  provider_source: 'system_ollama' as const,
  provider_type: 'ollama_local',
  provider_label: 'System Ollama',
  model_name: 'qwen2.5-coder:7b',
  title: '新的 AI 对话',
  provider_snapshot: {},
  created_by: 'user-1',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  messages: [],
});

const buildModelCatalog = () => ({
  items: [
    {
      provider_source: 'system_ollama',
      provider_id: null,
      provider_key: 'system_ollama',
      provider_label: 'System Ollama',
      provider_type: 'ollama_local',
      enabled: true,
      models: [
        {
          name: 'qwen2.5-coder:7b',
          label: 'qwen2.5-coder:7b',
          is_default: true,
          details: {},
        },
      ],
    },
  ],
  default_selection: {
    ai_source: 'system_ollama',
    ai_model: 'qwen2.5-coder:7b',
  },
});

const createDeferred = <T,>() => {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return { promise, resolve, reject };
};

vi.mock('../services/ai', () => ({
  listMyChatSessions: vi.fn(),
  createGeneralChatSession: vi.fn(),
  createChatSession: vi.fn(),
  deleteChatSession: vi.fn(),
  getChatSession: vi.fn(),
  sendChatMessageStream: vi.fn(),
  listMyAIProviders: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getMyAIModelCatalog: vi.fn(),
  updateChatSessionSelection: vi.fn(),
}));

vi.mock('../services/findings', () => ({
  FindingService: {
    getFinding: vi.fn(),
  },
}));

const mockedAI = vi.mocked(aiService);

describe('AICenterPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
    vi.clearAllMocks();

    mockedAI.listMyChatSessions.mockResolvedValue({ items: [], total: 0 });
    mockedAI.createGeneralChatSession.mockResolvedValue(buildSession());
    mockedAI.createChatSession.mockResolvedValue(buildSession());
    mockedAI.deleteChatSession.mockResolvedValue({ ok: true, session_id: 'session-1' });
    mockedAI.getChatSession.mockResolvedValue(buildSession());
    mockedAI.sendChatMessageStream.mockResolvedValue(undefined);
    mockedAI.getMyAIModelCatalog.mockResolvedValue(buildModelCatalog());
    mockedAI.updateChatSessionSelection.mockResolvedValue(buildSession());
  });

  it('renders welcome screen instead of blank page', async () => {
    render(
      <MemoryRouter initialEntries={['/ai-center']}>
        <Routes>
          <Route path="/ai-center" element={<AICenterPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('我们先从哪里开始呢？')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('输入消息，Shift + Enter 换行...')).toBeInTheDocument();
    });
  });

  it('shows the first user message before assistant reply arrives', async () => {
    const userContent = '请先帮我分析这段代码';
    const assistantContent = '好的，我先从输入校验和权限边界开始分析。';
    const deferredSend = createDeferred<void>();
    const session = buildSession();
    const persistedUserMessage = {
      id: 'msg-user-1',
      session_id: session.id,
      role: 'user' as const,
      content: userContent,
      created_at: new Date().toISOString(),
      meta_json: {},
    };
    const persistedAssistantMessage = {
      id: 'msg-assistant-1',
      session_id: session.id,
      role: 'assistant' as const,
      content: assistantContent,
      created_at: new Date().toISOString(),
      meta_json: {},
    };

    mockedAI.createGeneralChatSession.mockResolvedValue(session);
    mockedAI.sendChatMessageStream.mockImplementation(async (_sessionId, _data, options) => {
      options.onEvent({ event: 'user_message', data: persistedUserMessage });
      await deferredSend.promise;
      options.onEvent({ event: 'assistant_delta', data: { delta: assistantContent } });
      options.onEvent({ event: 'assistant_message', data: persistedAssistantMessage });
      options.onEvent({ event: 'done', data: { session_id: session.id } });
    });
    mockedAI.getChatSession
      .mockResolvedValueOnce({
        ...session,
        messages: [],
      });

    render(
      <MemoryRouter initialEntries={['/ai-center']}>
        <Routes>
          <Route path="/ai-center" element={<AICenterPage />} />
        </Routes>
      </MemoryRouter>
    );

    const welcomeInputs = await screen.findAllByPlaceholderText('输入消息，Shift + Enter 换行...');
    welcomeInputs.forEach((input) => {
      fireEvent.change(input, { target: { value: userContent } });
    });
    const welcomeInput = welcomeInputs[welcomeInputs.length - 1];
    fireEvent.keyDown(welcomeInput, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(mockedAI.createGeneralChatSession).toHaveBeenCalled();
    });

    expect(await screen.findByText(userContent)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockedAI.getChatSession).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText(userContent)).toBeInTheDocument();

    await act(async () => {
      deferredSend.resolve();
      await deferredSend.promise;
    });

    await waitFor(() => {
      expect(screen.getByText(assistantContent)).toBeInTheDocument();
    });
  });
});
