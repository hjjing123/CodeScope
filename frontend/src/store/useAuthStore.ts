import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuthTokenPayload, User } from '../types/auth';
import { clearAuthToken, getAuthToken, setAuthToken } from '../utils/authToken';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (tokenPayload: AuthTokenPayload, user: User) => void;
  logout: () => void;
  updateUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: getAuthToken(),
      user: null,
      isAuthenticated: Boolean(getAuthToken()),
      login: (tokenPayload, user) => {
        setAuthToken(tokenPayload.access_token, tokenPayload.expires_in);
        set({
          token: tokenPayload.access_token,
          user,
          isAuthenticated: true,
        });
      },
      logout: () => {
        clearAuthToken();
        set({
          token: null,
          user: null,
          isAuthenticated: false,
        });
      },
      updateUser: (user) => set({ user }),
    }),
    {
      name: 'auth-storage', // unique name for localStorage
    }
  )
);
