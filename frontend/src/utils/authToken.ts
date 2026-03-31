import type { AuthTokenPayload } from '../types/auth';

const ACCESS_TOKEN_KEY = 'token';
const ACCESS_TOKEN_EXPIRES_AT_KEY = 'token_expires_at';
const REFRESH_TOKEN_KEY = 'refresh_token';
const REFRESH_TOKEN_EXPIRES_AT_KEY = 'refresh_token_expires_at';
const SESSION_ID_KEY = 'session_id';

const getCookieToken = (): string | null => {
  const tokenCookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${ACCESS_TOKEN_KEY}=`));

  if (!tokenCookie) {
    return null;
  }

  const value = tokenCookie.slice(ACCESS_TOKEN_KEY.length + 1);
  return value ? decodeURIComponent(value) : null;
};

const getStoredNumber = (key: string): number | null => {
  const value = localStorage.getItem(key);
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const setStoredExpiry = (key: string, expiresIn?: number): void => {
  if (typeof expiresIn === 'number' && Number.isFinite(expiresIn) && expiresIn > 0) {
    localStorage.setItem(key, String(Date.now() + Math.floor(expiresIn * 1000)));
    return;
  }

  localStorage.removeItem(key);
};

export const getAuthToken = (): string | null => {
  const localToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (localToken) {
    return localToken;
  }
  return getCookieToken();
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

export const getAccessTokenExpiresAt = (): number | null => {
  return getStoredNumber(ACCESS_TOKEN_EXPIRES_AT_KEY);
};

export const getRefreshTokenExpiresAt = (): number | null => {
  return getStoredNumber(REFRESH_TOKEN_EXPIRES_AT_KEY);
};

export const getSessionId = (): string | null => {
  return localStorage.getItem(SESSION_ID_KEY);
};

export const hasAuthToken = (): boolean => {
  return Boolean(getAuthToken());
};

export const hasRefreshToken = (): boolean => {
  return Boolean(getRefreshToken());
};

export const isAccessTokenExpired = (bufferMs = 0): boolean => {
  const token = getAuthToken();
  if (!token) {
    return true;
  }

  const expiresAt = getAccessTokenExpiresAt();
  if (!expiresAt) {
    return false;
  }

  return expiresAt <= Date.now() + bufferMs;
};

export const isRefreshTokenExpired = (bufferMs = 0): boolean => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return true;
  }

  const expiresAt = getRefreshTokenExpiresAt();
  if (!expiresAt) {
    return false;
  }

  return expiresAt <= Date.now() + bufferMs;
};

export const setAuthToken = (token: string, expiresIn?: number): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
  setStoredExpiry(ACCESS_TOKEN_EXPIRES_AT_KEY, expiresIn);

  const maxAge =
    typeof expiresIn === 'number' && Number.isFinite(expiresIn) && expiresIn > 0
      ? `; Max-Age=${Math.floor(expiresIn)}`
      : '';
  document.cookie = `${ACCESS_TOKEN_KEY}=${encodeURIComponent(token)}; Path=/; SameSite=Lax${maxAge}`;
};

export const setAuthSession = (payload: AuthTokenPayload): void => {
  setAuthToken(payload.access_token, payload.expires_in);
  localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
  setStoredExpiry(REFRESH_TOKEN_EXPIRES_AT_KEY, payload.refresh_expires_in);
  localStorage.setItem(SESSION_ID_KEY, payload.session_id);
};

export const clearAuthSession = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(ACCESS_TOKEN_EXPIRES_AT_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_EXPIRES_AT_KEY);
  localStorage.removeItem(SESSION_ID_KEY);
  document.cookie = `${ACCESS_TOKEN_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
};

export const clearAuthToken = (): void => {
  clearAuthSession();
};
