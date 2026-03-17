import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SessionSidebar from './SessionSidebar';
import type { AIChatSessionPayload } from '../../types/ai';

const session: AIChatSessionPayload = {
  id: 'session-1',
  session_mode: 'general',
  finding_id: null,
  project_id: null,
  version_id: null,
  provider_source: 'system_ollama',
  provider_type: 'ollama_local',
  provider_label: 'System Ollama',
  model_name: 'qwen2.5-coder:7b',
  title: '待删除会话',
  provider_snapshot: {},
  created_by: 'user-1',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  messages: [],
};

describe('SessionSidebar', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  });

  it('confirms and deletes session without selecting it', async () => {
    const onSelectSession = vi.fn();
    const onDeleteSession = vi.fn().mockResolvedValue(undefined);

    render(
      <SessionSidebar
        sessions={[session]}
        currentSessionId={session.id}
        onSelectSession={onSelectSession}
        onNewChat={vi.fn()}
        onDeleteSession={onDeleteSession}
      />
    );

    fireEvent.click(screen.getByLabelText(`删除会话 ${session.title}`));
    expect(onSelectSession).not.toHaveBeenCalled();

    const deleteButtons = await screen.findAllByRole('button', { name: /删\s*除/ });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => {
      expect(onDeleteSession).toHaveBeenCalledWith(session);
    });
  });
});
