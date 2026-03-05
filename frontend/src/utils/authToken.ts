const TOKEN_KEY = 'token';

const getCookieToken = (): string | null => {
  const tokenCookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${TOKEN_KEY}=`));

  if (!tokenCookie) {
    return null;
  }

  const value = tokenCookie.slice(TOKEN_KEY.length + 1);
  return value ? decodeURIComponent(value) : null;
};

export const getAuthToken = (): string | null => {
  const localToken = localStorage.getItem(TOKEN_KEY);
  if (localToken) {
    return localToken;
  }
  return getCookieToken();
};

export const hasAuthToken = (): boolean => {
  return Boolean(getAuthToken());
};

export const setAuthToken = (token: string, expiresIn?: number): void => {
  localStorage.setItem(TOKEN_KEY, token);

  const maxAge =
    typeof expiresIn === 'number' && Number.isFinite(expiresIn) && expiresIn > 0
      ? `; Max-Age=${Math.floor(expiresIn)}`
      : '';
  document.cookie = `${TOKEN_KEY}=${encodeURIComponent(token)}; Path=/; SameSite=Lax${maxAge}`;
};

export const clearAuthToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = `${TOKEN_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
};
