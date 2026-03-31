import axios from 'axios';
import type { AuthTokenPayload } from '../types/auth';
import { clearAuthSession, getRefreshToken, isRefreshTokenExpired, setAuthSession } from './authToken';

const authClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

let refreshPromise: Promise<AuthTokenPayload> | null = null;

export const refreshAuthSession = async (
  refreshToken: string | null = getRefreshToken()
): Promise<AuthTokenPayload> => {
  if (!refreshToken || isRefreshTokenExpired()) {
    clearAuthSession();
    throw new Error('Refresh token expired');
  }

  if (!refreshPromise) {
    refreshPromise = authClient
      .post<{ data: AuthTokenPayload }>('/auth/refresh', {
        refresh_token: refreshToken,
      })
      .then((response) => {
        const payload = response.data.data;
        setAuthSession(payload);
        return payload;
      })
      .catch((error) => {
        clearAuthSession();
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
};
