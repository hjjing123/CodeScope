import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import request from './request';
import { clearAuthSession, setAuthSession } from './authToken';
import type { AuthTokenPayload } from '../types/auth';

const mocks = vi.hoisted(() => ({
  clearSession: vi.fn(),
  syncFromStorage: vi.fn(),
  refreshAuthSession: vi.fn(),
  messageError: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      error: mocks.messageError,
    },
  };
});

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({
      clearSession: mocks.clearSession,
      syncFromStorage: mocks.syncFromStorage,
    }),
  },
}));

vi.mock('./authSession', () => ({
  refreshAuthSession: mocks.refreshAuthSession,
}));

const refreshedBundle: AuthTokenPayload = {
  access_token: 'fresh-access-token',
  refresh_token: 'fresh-refresh-token',
  token_type: 'bearer',
  expires_in: 900,
  refresh_expires_in: 604800,
  session_id: 'session-2',
};

const buildUnauthorizedError = (config: Record<string, unknown>) => ({
  config,
  response: {
    status: 401,
    data: { message: '令牌已过期' },
    headers: {},
    config,
    statusText: 'Unauthorized',
  },
});

describe('request auth refresh handling', () => {
  const originalAdapter = request.defaults.adapter;

  beforeEach(() => {
    clearAuthSession();
    localStorage.clear();
    vi.clearAllMocks();
    window.history.replaceState({}, '', '/login');

    setAuthSession({
      access_token: 'stale-access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 604800,
      session_id: 'session-1',
    });
  });

  afterEach(() => {
    request.defaults.adapter = originalAdapter;
  });

  it('refreshes once and retries the original request after a 401', async () => {
    mocks.refreshAuthSession.mockImplementation(async () => {
      setAuthSession(refreshedBundle);
      return refreshedBundle;
    });

    const adapter = vi.fn(async (config) => {
      if (config.headers?.Authorization === `Bearer ${refreshedBundle.access_token}`) {
        return {
          data: { data: { ok: true } },
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        };
      }

      return Promise.reject(buildUnauthorizedError(config as Record<string, unknown>));
    });
    request.defaults.adapter = adapter;

    const result = await request.get('/protected-resource');

    expect(result).toEqual({ data: { ok: true } });
    expect(mocks.refreshAuthSession).toHaveBeenCalledTimes(1);
    expect(mocks.syncFromStorage).toHaveBeenCalledTimes(1);
    expect(mocks.clearSession).not.toHaveBeenCalled();
    expect(adapter).toHaveBeenCalledTimes(2);
  });

  it('clears local auth state when refresh fails', async () => {
    mocks.refreshAuthSession.mockRejectedValue(new Error('refresh failed'));

    const adapter = vi.fn(async (config) => {
      return Promise.reject(buildUnauthorizedError(config as Record<string, unknown>));
    });
    request.defaults.adapter = adapter;

    await expect(request.get('/protected-resource')).rejects.toThrow('refresh failed');

    expect(mocks.refreshAuthSession).toHaveBeenCalledTimes(1);
    expect(mocks.clearSession).toHaveBeenCalledTimes(1);
    expect(mocks.syncFromStorage).not.toHaveBeenCalled();
    expect(mocks.messageError).toHaveBeenCalledWith('令牌已过期');
    expect(adapter).toHaveBeenCalledTimes(1);
  });
});
