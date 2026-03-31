import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuthTokenPayload, User } from '../types/auth';
import {
  clearAuthSession,
  getAuthToken,
  getRefreshToken,
  hasAuthToken,
  hasRefreshToken,
  isAccessTokenExpired,
  isRefreshTokenExpired,
  setAuthSession,
} from '../utils/authToken';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isAuthReady: boolean;
  login: (tokenPayload: AuthTokenPayload, user: User) => void;
  logout: () => Promise<void>;
  clearSession: () => void;
  syncFromStorage: () => void;
  initializeAuth: () => Promise<void>;
  updateUser: (user: User) => void;
}

let authInitializationPromise: Promise<void> | null = null;

const readStoredSession = () => ({
  token: getAuthToken(),
  refreshToken: getRefreshToken(),
  isAuthenticated: hasAuthToken() || hasRefreshToken(),
});

const isUnauthorizedError = (error: unknown): boolean => {
  const candidate = error as { response?: { status?: number } };
  return candidate?.response?.status === 401;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      ...readStoredSession(),
      user: null,
      isAuthReady: false,
      login: (tokenPayload, user) => {
        setAuthSession(tokenPayload);
        set({
          ...readStoredSession(),
          user,
          isAuthenticated: true,
          isAuthReady: true,
        });
      },
      logout: async () => {
        const refreshToken = getRefreshToken();

        try {
          if (refreshToken) {
            const { logout } = await import('../services/auth');
            await logout(refreshToken);
          }
        } catch (error) {
          console.warn('Failed to revoke auth session', error);
        } finally {
          get().clearSession();
        }
      },
      clearSession: () => {
        clearAuthSession();
        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
          isAuthReady: true,
        });
      },
      syncFromStorage: () => {
        set((state) => ({
          ...readStoredSession(),
          user: state.user,
          isAuthReady: state.isAuthReady,
        }));
      },
      initializeAuth: async () => {
        if (authInitializationPromise) {
          return authInitializationPromise;
        }

        authInitializationPromise = (async () => {
          const accessToken = getAuthToken();
          const refreshToken = getRefreshToken();
          const hasUsableRefreshToken = Boolean(refreshToken) && !isRefreshTokenExpired(5000);

          if (!accessToken && !hasUsableRefreshToken) {
            get().clearSession();
            return;
          }

          if (!accessToken || isAccessTokenExpired(5000)) {
            if (!hasUsableRefreshToken) {
              get().clearSession();
              return;
            }

            try {
              const { refreshAuthSession } = await import('../utils/authSession');
              await refreshAuthSession(refreshToken);
              set({
                ...readStoredSession(),
                user: get().user,
                isAuthenticated: true,
                isAuthReady: false,
              });
            } catch {
              get().clearSession();
              return;
            }
          } else {
            set((state) => ({
              ...readStoredSession(),
              user: state.user,
              isAuthenticated: true,
              isAuthReady: false,
            }));
          }

          if (!get().user) {
            try {
              const { getMe } = await import('../services/auth');
              const { data: user } = await getMe();
              set({
                ...readStoredSession(),
                user,
                isAuthenticated: true,
                isAuthReady: false,
              });
            } catch (error) {
              if (isUnauthorizedError(error)) {
                get().clearSession();
                return;
              }
            }
          }

          set((state) => ({
            ...readStoredSession(),
            user: state.user,
            isAuthenticated: hasAuthToken() || hasRefreshToken(),
            isAuthReady: true,
          }));
        })().finally(() => {
          authInitializationPromise = null;
          set((state) => (state.isAuthReady ? state : { isAuthReady: true }));
        });

        return authInitializationPromise;
      },
      updateUser: (user) => set({ user }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
      }),
    }
  )
);
