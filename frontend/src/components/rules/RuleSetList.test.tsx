import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RuleSetList from './RuleSetList';
import {
  bindRuleSetRules,
  createRuleSet,
  getRuleSet,
  getRuleSets,
  getRules,
  updateRuleSet,
} from '../../services/rules';

vi.mock('../../services/rules', () => ({
  bindRuleSetRules: vi.fn(),
  createRuleSet: vi.fn(),
  getRuleSet: vi.fn(),
  getRuleSets: vi.fn(),
  getRules: vi.fn(),
  updateRuleSet: vi.fn(),
}));

const mockedBindRuleSetRules = vi.mocked(bindRuleSetRules);
const mockedCreateRuleSet = vi.mocked(createRuleSet);
const mockedGetRuleSet = vi.mocked(getRuleSet);
const mockedGetRuleSets = vi.mocked(getRuleSets);
const mockedGetRules = vi.mocked(getRules);
const mockedUpdateRuleSet = vi.mocked(updateRuleSet);

describe('RuleSetList', () => {
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

    mockedBindRuleSetRules.mockResolvedValue({
      id: 'rule-set-1',
      key: 'default-set',
      name: '默认规则集',
      description: '面向默认扫描场景',
      enabled: true,
      created_at: '2026-03-31T08:00:00Z',
      updated_at: '2026-03-31T09:00:00Z',
      items: [],
    });
    mockedCreateRuleSet.mockResolvedValue({
      id: 'rule-set-1',
      key: 'default-set',
      name: '默认规则集',
      description: '面向默认扫描场景',
      enabled: true,
      rule_count: 2,
      created_at: '2026-03-31T08:00:00Z',
      updated_at: '2026-03-31T09:00:00Z',
    });
    mockedUpdateRuleSet.mockResolvedValue({
      id: 'rule-set-1',
      key: 'default-set',
      name: '默认规则集',
      description: '面向默认扫描场景',
      enabled: true,
      rule_count: 2,
      created_at: '2026-03-31T08:00:00Z',
      updated_at: '2026-03-31T09:00:00Z',
    });
    mockedGetRuleSets.mockResolvedValue({
      items: [
        {
          id: 'rule-set-1',
          key: 'default-set',
          name: '默认规则集',
          description: '面向默认扫描场景',
          enabled: true,
          rule_count: 2,
          created_at: '2026-03-31T08:00:00Z',
          updated_at: '2026-03-31T09:00:00Z',
        },
      ],
      total: 1,
    });
    mockedGetRules.mockResolvedValue({
      items: [
        {
          rule_key: 'demo.rule.one',
          name: '默认规则一',
          vuln_type: 'XSS',
          default_severity: 'HIGH',
          language_scope: 'java',
          description: 'rule one',
          enabled: true,
          active_version: 1,
          created_at: '2026-03-31T08:00:00Z',
          updated_at: '2026-03-31T09:00:00Z',
        },
        {
          rule_key: 'demo.rule.two',
          name: '默认规则二',
          vuln_type: 'SQLI',
          default_severity: 'MED',
          language_scope: 'java',
          description: 'rule two',
          enabled: true,
          active_version: 1,
          created_at: '2026-03-31T08:00:00Z',
          updated_at: '2026-03-31T09:00:00Z',
        },
      ],
      total: 2,
    });
    mockedGetRuleSet.mockResolvedValue({
      id: 'rule-set-1',
      key: 'default-set',
      name: '默认规则集',
      description: '面向默认扫描场景',
      enabled: true,
      created_at: '2026-03-31T08:00:00Z',
      updated_at: '2026-03-31T09:00:00Z',
      items: [
        {
          id: 'item-1',
          rule_set_id: 'rule-set-1',
          rule_key: 'demo.rule.one',
          created_at: '2026-03-31T08:00:00Z',
        },
        {
          id: 'item-2',
          rule_set_id: 'rule-set-1',
          rule_key: 'demo.rule.two',
          created_at: '2026-03-31T08:05:00Z',
        },
      ],
    });
  });

  it('shows view and edit actions for admins and supports view details', async () => {
    render(<RuleSetList canManageRuleSets={true} />);

    expect(await screen.findByText('默认规则集')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /新建规则集/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看规则集 默认规则集' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '编辑规则集 默认规则集' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看规则集 默认规则集' }));

    await waitFor(() => {
      expect(mockedGetRuleSet).toHaveBeenCalledWith('rule-set-1');
    });

    expect(await screen.findByText('查看规则集：默认规则集')).toBeInTheDocument();
    expect(screen.getByText('默认规则一')).toBeInTheDocument();
    expect(screen.getByText('默认规则二')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));

    await waitFor(() => {
      expect(screen.queryByText('查看规则集：默认规则集')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '编辑规则集 默认规则集' }));

    await waitFor(() => {
      expect(mockedGetRuleSet).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('编辑规则集')).toBeInTheDocument();
  });

  it('keeps regular users in read-only mode with view-only actions', async () => {
    render(<RuleSetList canManageRuleSets={false} />);

    expect(await screen.findByText('默认规则集')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新建规则集' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看规则集 默认规则集' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '编辑规则集 默认规则集' })
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看规则集 默认规则集' }));

    await waitFor(() => {
      expect(mockedGetRuleSet).toHaveBeenCalledWith('rule-set-1');
    });

    expect(await screen.findByText('查看规则集：默认规则集')).toBeInTheDocument();
    expect(screen.getByText('默认规则一')).toBeInTheDocument();
    expect(screen.getByText('默认规则二')).toBeInTheDocument();
  });
});
