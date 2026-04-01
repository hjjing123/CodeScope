import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { message } from 'antd';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RuleDetailPage from './RuleDetailPage';
import {
  getRuleDetails,
  getRuleVersions,
  publish,
  rollback,
  toggle,
  updateDraft,
} from '../services/rules';
import { useAuthStore } from '../store/useAuthStore';

const navigateMock = vi.fn();

vi.mock('../services/rules', () => ({
  getRuleDetails: vi.fn(),
  getRuleVersions: vi.fn(),
  updateDraft: vi.fn(),
  publish: vi.fn(),
  rollback: vi.fn(),
  toggle: vi.fn(),
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../components/rules/SelfTestPanel', () => ({
  default: () => <div data-testid="self-test-panel">Rule Self-Test</div>,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

const mockedGetRuleDetails = vi.mocked(getRuleDetails);
const mockedGetRuleVersions = vi.mocked(getRuleVersions);
const mockedUpdateDraft = vi.mocked(updateDraft);
const mockedPublish = vi.mocked(publish);
const mockedRollback = vi.mocked(rollback);
const mockedToggle = vi.mocked(toggle);
const mockedUseAuthStore = vi.mocked(useAuthStore);

const messageErrorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);

const publishedRule = {
  rule_key: 'demo.rule',
  name: 'Demo Rule',
  vuln_type: 'XSS',
  default_severity: 'HIGH',
  language_scope: 'java',
  description: 'Published description',
  enabled: true,
  active_version: 1,
  created_at: '2026-04-01T08:00:00Z',
  updated_at: '2026-04-01T08:00:00Z',
};

const renderPage = (path = '/rules/demo.rule') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/rules/:ruleKey" element={<RuleDetailPage />} />
      </Routes>
    </MemoryRouter>
  );

describe('RuleDetailPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();

    mockedUpdateDraft.mockResolvedValue({ rule: publishedRule, draft_version: {} as never });
    mockedPublish.mockResolvedValue({ rule: publishedRule, published_version: {} as never });
    mockedRollback.mockResolvedValue(publishedRule);
    mockedToggle.mockResolvedValue(publishedRule);
  });

  afterEach(() => {
    cleanup();
  });

  it('keeps management actions available for admins', async () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'admin-1',
        email: 'admin@example.com',
        display_name: 'Admin',
        role: 'Admin',
      },
    } as ReturnType<typeof useAuthStore>);

    mockedGetRuleDetails.mockResolvedValue({
      ...publishedRule,
      name: 'Draft Visible Rule',
    });
    mockedGetRuleVersions.mockResolvedValue({
      items: [
        {
          id: 'draft-version',
          rule_key: 'demo.rule',
          version: 2,
          status: 'DRAFT',
          content: {
            query: 'MATCH (n) RETURN n LIMIT 2',
            remediation: 'Draft remediation',
          },
          created_by: 'admin-1',
          created_at: '2026-04-01T09:00:00Z',
        },
        {
          id: 'published-version',
          rule_key: 'demo.rule',
          version: 1,
          status: 'PUBLISHED',
          content: {
            query: 'MATCH (n) RETURN n LIMIT 1',
            remediation: 'Published remediation',
          },
          created_by: 'admin-1',
          created_at: '2026-04-01T08:00:00Z',
        },
      ],
      total: 2,
    });

    renderPage();

    expect(await screen.findByText('Draft Visible Rule')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockedGetRuleDetails).toHaveBeenCalledWith('demo.rule', {
        skipErrorToast: true,
      });
      expect(mockedGetRuleVersions).toHaveBeenCalledWith('demo.rule', {
        skipErrorToast: true,
      });
    });

    expect(screen.getByRole('button', { name: /保存草稿/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /发布版本/ })).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByText('回滚')).toBeInTheDocument();
    expect(screen.getByTestId('self-test-panel')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Draft Visible Rule')).not.toBeDisabled();
  });

  it('renders published rules as read-only for regular users', async () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'User',
        role: 'User',
      },
    } as ReturnType<typeof useAuthStore>);

    mockedGetRuleDetails.mockResolvedValue(publishedRule);
    mockedGetRuleVersions.mockResolvedValue({
      items: [
        {
          id: 'published-version',
          rule_key: 'demo.rule',
          version: 1,
          status: 'PUBLISHED',
          content: {
            query: 'MATCH (n) RETURN n LIMIT 1',
            remediation: 'Published remediation',
          },
          created_by: 'admin-1',
          created_at: '2026-04-01T08:00:00Z',
        },
      ],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText('Demo Rule')).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: /保存草稿/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /发布版本/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByText('回滚')).not.toBeInTheDocument();
    expect(screen.queryByTestId('self-test-panel')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('Demo Rule')).toBeDisabled();
    expect(screen.getByDisplayValue('MATCH (n) RETURN n LIMIT 1')).toBeDisabled();
  });

  it('redirects regular users away from hidden draft rules', async () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'User',
        role: 'User',
      },
    } as ReturnType<typeof useAuthStore>);

    const notFoundError = { response: { status: 404 } };
    mockedGetRuleDetails.mockRejectedValue(notFoundError);
    mockedGetRuleVersions.mockRejectedValue(notFoundError);

    renderPage('/rules/hidden.rule');

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/rules', { replace: true });
    });

    expect(messageErrorSpy).toHaveBeenCalledWith('规则不存在或尚未发布');
  });
});
