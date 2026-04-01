import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import RuleCenterPage from './RuleCenterPage';
import { createRule, getRules } from '../services/rules';
import { useAuthStore } from '../store/useAuthStore';

const { mockedRuleSetList } = vi.hoisted(() => ({
  mockedRuleSetList: vi.fn(),
}));

vi.mock('../services/rules', () => ({
  createRule: vi.fn(),
  getRules: vi.fn(),
  toggle: vi.fn(),
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../components/rules/RuleStatsCard', () => ({
  default: () => <div data-testid="rule-stats-card" />,
}));

vi.mock('../components/rules/RuleSetList', () => ({
  default: (props: { canManageRuleSets?: boolean }) => {
    mockedRuleSetList(props);
    return (
      <div data-testid="rule-set-list">
        {props.canManageRuleSets ? 'ruleset-manage' : 'ruleset-readonly'}
      </div>
    );
  },
}));

const mockedGetRules = vi.mocked(getRules);
const mockedCreateRule = vi.mocked(createRule);
const mockedUseAuthStore = vi.mocked(useAuthStore);

const renderPage = () =>
  render(
    <MemoryRouter>
      <RuleCenterPage />
    </MemoryRouter>
  );

describe('RuleCenterPage', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockedCreateRule.mockResolvedValue({
      rule_key: 'created.rule',
      name: 'Created Rule',
      vuln_type: 'CUSTOM',
      default_severity: 'MED',
      language_scope: 'java',
      description: 'created',
      enabled: true,
      active_version: null,
      created_at: '2026-04-01T08:00:00Z',
      updated_at: '2026-04-01T08:00:00Z',
    });

    mockedGetRules.mockImplementation(async (params = {}) => {
      if (params.enabled === true) {
        return { items: [], total: 6 };
      }

      if (params.enabled === false) {
        return { items: [], total: 4 };
      }

      return {
        items: [
          {
            rule_key: 'demo.rule',
            name: 'Demo Rule',
            vuln_type: 'SQLI',
            default_severity: 'HIGH',
            language_scope: 'java',
            description: 'demo rule',
            enabled: true,
            active_version: 1,
            created_at: '2026-03-31T08:00:00Z',
            updated_at: '2026-03-31T09:00:00Z',
          },
        ],
        total: 1,
      };
    });
  });

  it('shows status and action columns for admins', async () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'admin-1',
        email: 'admin@example.com',
        display_name: 'Admin',
        role: 'Admin',
      },
    } as ReturnType<typeof useAuthStore>);

    const view = renderPage();
    const scoped = within(view.container);

    expect(await screen.findByText('Demo Rule')).toBeInTheDocument();

    await waitFor(() => {
      expect(scoped.getByText('状态')).toBeInTheDocument();
      expect(scoped.getByText('操作')).toBeInTheDocument();
      expect(scoped.getAllByRole('switch').length).toBeGreaterThan(0);
    });

    expect(scoped.getByText('新建规则')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '规则集' }));

    expect(await screen.findByTestId('rule-set-list')).toHaveTextContent('ruleset-manage');
    expect(mockedRuleSetList).toHaveBeenLastCalledWith(
      expect.objectContaining({ canManageRuleSets: true })
    );
  });

  it(
    'creates a rule without exposing or submitting language scope',
    async () => {
      mockedUseAuthStore.mockReturnValue({
        user: {
          id: 'admin-1',
          email: 'admin@example.com',
          display_name: 'Admin',
          role: 'Admin',
        },
      } as ReturnType<typeof useAuthStore>);

      renderPage();

      expect(await screen.findByText('Demo Rule')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: /新建规则/ }));

      const dialog = await screen.findByRole('dialog');
      const modal = within(dialog);

      expect(modal.queryByText('语言范围')).not.toBeInTheDocument();
      expect(modal.queryByText('请输入语言范围')).not.toBeInTheDocument();

      fireEvent.change(modal.getByPlaceholderText('例如: custom.demo.xss'), {
        target: { value: 'custom.demo.xss' },
      });
      fireEvent.change(modal.getByPlaceholderText('请输入规则名称'), {
        target: { value: 'Custom Demo Rule' },
      });
      fireEvent.change(modal.getByPlaceholderText('MATCH (n) RETURN n LIMIT 10'), {
        target: { value: 'MATCH (n) RETURN n LIMIT 1' },
      });
      fireEvent.change(modal.getByRole('spinbutton'), {
        target: { value: '5000' },
      });

      fireEvent.click(modal.getByRole('button', { name: /^(OK|确定)$/ }));

      await waitFor(() => {
        expect(mockedCreateRule).toHaveBeenCalledTimes(1);
      });

      expect(mockedCreateRule.mock.calls[0][0]).toEqual({
        rule_key: 'custom.demo.xss',
        name: 'Custom Demo Rule',
        vuln_type: 'CUSTOM',
        default_severity: 'MED',
        description: undefined,
        content: {
          query: 'MATCH (n) RETURN n LIMIT 1',
          timeout_ms: 5000,
        },
      });
      expect(mockedCreateRule.mock.calls[0][0]).not.toHaveProperty('language_scope');
    },
    10000
  );

  it('hides status and action columns for regular users', async () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'User',
        role: 'User',
      },
    } as ReturnType<typeof useAuthStore>);

    const view = renderPage();
    const scoped = within(view.container);

    expect(await screen.findByText('Demo Rule')).toBeInTheDocument();

    await waitFor(() => {
      expect(scoped.queryByText('状态')).not.toBeInTheDocument();
      expect(scoped.queryByText('操作')).not.toBeInTheDocument();
      expect(scoped.queryByRole('switch')).not.toBeInTheDocument();
    });

    expect(scoped.queryByText('新建规则')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '规则集' }));

    expect(await screen.findByTestId('rule-set-list')).toHaveTextContent('ruleset-readonly');
    expect(mockedRuleSetList).toHaveBeenLastCalledWith(
      expect.objectContaining({ canManageRuleSets: false })
    );
  });
});
