import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { message } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AICenterPage from './AICenterPage';
import * as aiService from '../services/ai';
import { FindingService } from '../services/findings';
import type { AIChatSessionPayload } from '../types/ai';
import type { Finding } from '../types/finding';

const buildSession = (overrides: Partial<AIChatSessionPayload> = {}): AIChatSessionPayload => ({
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
  ...overrides,
});

const buildFinding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'finding-1',
  project_id: 'project-1',
  version_id: 'version-1',
  job_id: 'job-1',
  rule_key: 'rule-1',
  rule_version: 1,
  vuln_type: 'SQLI',
  vuln_display_name: 'SQL 注入',
  severity: 'High',
  status: 'OPEN',
  file_path: 'src/app.py',
  line_start: 12,
  line_end: 12,
  entry_display: null,
  entry_kind: null,
  has_path: false,
  path_length: null,
  source_file: null,
  source_line: null,
  sink_file: null,
  sink_line: null,
  evidence_json: {
    code_context: {
      focus: {
        snippet: 'cursor.execute(query)',
        start_line: 12,
      },
    },
  },
  ai_review: {
    has_assessment: true,
    verdict: 'TP',
    confidence: 'HIGH',
    updated_at: new Date().toISOString(),
  },
  created_at: new Date().toISOString(),
  ...overrides,
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
      default_model: 'qwen2.5-coder:7b',
      available: true,
      connection_ok: true,
      model_catalog_ok: true,
      allow_manual_model_input: false,
      source_label: '本地',
      status_label: '可用',
      status_reason: null,
      models: [
        {
          name: 'qwen2.5-coder:7b',
          label: 'qwen2.5-coder:7b',
          is_default: true,
          selectable: true,
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
  getLatestFindingAIAssessmentContext: vi.fn(),
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
const mockedGetFinding = vi.mocked(FindingService.getFinding);

const renderAICenterPage = (initialEntry = '/ai-center') =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/ai-center" element={<AICenterPage />} />
      </Routes>
    </MemoryRouter>
  );

const confirmSessionDeletion = async (title: string) => {
  fireEvent.click(screen.getByLabelText(`删除会话 ${title}`));
  const deleteButtons = await screen.findAllByRole('button', { name: /删\s*除/ });
  fireEvent.click(deleteButtons[deleteButtons.length - 1]);
};

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
    mockedAI.getLatestFindingAIAssessmentContext.mockResolvedValue(null as never);
    mockedAI.getMyAIModelCatalog.mockResolvedValue(buildModelCatalog());
    mockedAI.updateChatSessionSelection.mockResolvedValue(buildSession());
    mockedGetFinding.mockResolvedValue(buildFinding());
    vi.spyOn(message, 'error').mockImplementation(() => undefined as never);
    vi.spyOn(message, 'success').mockImplementation(() => undefined as never);
  });

  it('renders welcome screen instead of blank page', async () => {
    renderAICenterPage();

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

    renderAICenterPage();

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
      expect(mockedAI.sendChatMessageStream).toHaveBeenCalled();
    });
    expect(message.error).not.toHaveBeenCalled();
  });

  it('clears a missing session from the URL without retry loops', async () => {
    mockedAI.listMyChatSessions.mockResolvedValue({ items: [], total: 0 });
    mockedAI.getChatSession.mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 404,
        data: {
          error: {
            message: 'AI 会话不存在',
          },
        },
      },
    });

    renderAICenterPage('/ai-center?session_id=session-404');

    await waitFor(() => {
      expect(screen.getByText('我们先从哪里开始呢？')).toBeInTheDocument();
    });

    expect(mockedAI.getChatSession).toHaveBeenCalledTimes(1);
    expect(message.error).toHaveBeenCalledTimes(1);
    expect(message.error).toHaveBeenCalledWith('AI 会话不存在');
  });

  it('clears the finding context panel when deleting the active finding session', async () => {
    const findingSession = buildSession({
      id: 'session-finding',
      session_mode: 'finding_context',
      finding_id: 'finding-1',
      title: '漏洞分析会话',
    });

    mockedAI.listMyChatSessions
      .mockResolvedValueOnce({ items: [findingSession], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 });
    mockedAI.getChatSession.mockResolvedValue(findingSession);
    mockedGetFinding.mockResolvedValue(buildFinding({ id: 'finding-1' }));

    renderAICenterPage('/ai-center?session_id=session-finding&finding_id=finding-1');

    expect(await screen.findByText('SQL 注入')).toBeInTheDocument();

    await confirmSessionDeletion('漏洞分析会话');

    await waitFor(() => {
      expect(mockedAI.deleteChatSession).toHaveBeenCalledWith('session-finding');
    });

    await waitFor(() => {
      expect(screen.queryByText('SQL 注入')).not.toBeInTheDocument();
    });
    expect(message.error).not.toHaveBeenCalled();
  }, 15000);

  it('suppresses missing-session toast when deleting the active general session', async () => {
    const generalSession = buildSession({
      id: 'session-general',
      title: '待删除自由对话',
    });
    const deferredSession = createDeferred<AIChatSessionPayload>();

    mockedAI.listMyChatSessions
      .mockResolvedValueOnce({ items: [generalSession], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 });
    mockedAI.getChatSession.mockImplementation(() => deferredSession.promise);
    mockedAI.deleteChatSession.mockResolvedValue({ ok: true, session_id: generalSession.id });

    renderAICenterPage('/ai-center?session_id=session-general');

    expect(await screen.findByLabelText('删除会话 待删除自由对话')).toBeInTheDocument();

    await confirmSessionDeletion('待删除自由对话');

    await waitFor(() => {
      expect(mockedAI.deleteChatSession).toHaveBeenCalledWith('session-general');
    });

    await act(async () => {
      deferredSession.reject({
        isAxiosError: true,
        response: {
          status: 404,
          data: {
            error: {
              message: 'AI 会话不存在',
            },
          },
        },
      });

      try {
        await deferredSession.promise;
      } catch {
        // The component handles the rejection path.
      }
    });

    expect(message.error).not.toHaveBeenCalled();
  }, 15000);

});
