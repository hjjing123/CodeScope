import request from '../utils/request';
import type {
  LoginRequest,
  RegisterRequest,
  AuthTokenPayload,
  MePayload,
  RegisterPayload,
} from '../types/auth';

export const login = (data: LoginRequest) => {
  return request.post<any, { data: AuthTokenPayload }>('/auth/login', data, {
    skipAuthRefresh: true,
    skipUnauthorizedHandler: true,
  });
};

export const register = (data: RegisterRequest) => {
  return request.post<any, { data: RegisterPayload }>('/auth/register', data, {
    skipAuthRefresh: true,
    skipUnauthorizedHandler: true,
  });
};

export const refresh = (refreshToken: string) => {
  return request.post<any, { data: AuthTokenPayload }>(
    '/auth/refresh',
    { refresh_token: refreshToken },
    {
      skipAuthRefresh: true,
      skipUnauthorizedHandler: true,
      skipErrorToast: true,
    }
  );
};

export const logout = (refreshToken: string) => {
  return request.post<any, { data: { revoked: boolean; session_id: string } }>(
    '/auth/revoke',
    { refresh_token: refreshToken },
    {
      skipAuthRefresh: true,
      skipUnauthorizedHandler: true,
      skipErrorToast: true,
    }
  );
};

export const getMe = () => {
  return request.get<any, { data: MePayload }>('/auth/me');
};
