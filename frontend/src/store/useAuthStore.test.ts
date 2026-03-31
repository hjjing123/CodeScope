import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from './useAuthStore';
import { clearAuthSession, setAuthSession } from '../utils/authToken';
import type { AuthTokenPayload } from '../types/auth';
import { refreshAuthSession } from '../utils/authSession';
import { getMe, logout } from '../services/auth';

vi.mock('../utils/authSession', () => ({
  refreshAuthSession: vi.fn(),
}));

vi.mock('../services/auth', () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));

const mockedRefreshAuthSession = vi.mocked(refreshAuthSession);
const mockedGetMe = vi.mocked(getMe);
const mockedLogout = vi.mocked(logout);

const refreshedBundle: AuthTokenPayload = {
  access_token: 'fresh-access-token',
  refresh_token: 'fresh-refresh-token',
  token_type: 'bearer',
  expires_in: 900,
  refresh_expires_in: 604800,
  session_id: 'session-2',
};

describe('useAuthStore', () => {
  beforeEach(() => {
    clearAuthSession();
    localStorage.clear();
    vi.clearAllMocks();

    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isAuthReady: false,
    });
  });

  it('restores the session from refresh token during app bootstrap', async () => {
    setAuthSession({
      access_token: 'stale-access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 604800,
      session_id: 'session-1',
    });
    localStorage.setItem('token_expires_at', String(Date.now() - 10_000));

    mockedRefreshAuthSession.mockImplementation(async () => {
      setAuthSession(refreshedBundle);
      return refreshedBundle;
    });
    mockedGetMe.mockResolvedValue({
      data: {
        id: 'user-1',
        email: 'admin@example.com',
        display_name: 'Bootstrap Admin',
        role: 'Admin',
        is_active: true,
        must_change_password: false,
      },
    });

    await useAuthStore.getState().initializeAuth();

    expect(mockedRefreshAuthSession).toHaveBeenCalledWith('refresh-token');
    expect(mockedGetMe).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().token).toBe(refreshedBundle.access_token);
    expect(useAuthStore.getState().refreshToken).toBe(refreshedBundle.refresh_token);
    expect(useAuthStore.getState().user?.email).toBe('admin@example.com');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().isAuthReady).toBe(true);
  });

  it('revokes the current refresh token on logout and clears local auth state', async () => {
    setAuthSession({
      access_token: 'active-access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 604800,
      session_id: 'session-1',
    });
    useAuthStore.setState({
      token: 'active-access-token',
      refreshToken: 'refresh-token',
      user: {
        id: 'user-1',
        email: 'admin@example.com',
        display_name: 'Bootstrap Admin',
        role: 'Admin',
      },
      isAuthenticated: true,
      isAuthReady: true,
    });

    mockedLogout.mockResolvedValue({
      data: {
        revoked: true,
        session_id: 'session-1',
      },
    });

    await useAuthStore.getState().logout();

    expect(mockedLogout).toHaveBeenCalledWith('refresh-token');
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().isAuthReady).toBe(true);
  });
});
