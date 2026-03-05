import request from '../utils/request';
import type {
  LoginRequest,
  RegisterRequest,
  AuthTokenPayload,
  MePayload,
  RegisterPayload,
} from '../types/auth';

export const login = (data: LoginRequest) => {
  return request.post<any, { data: AuthTokenPayload }>('/auth/login', data);
};

export const register = (data: RegisterRequest) => {
  return request.post<any, { data: RegisterPayload }>('/auth/register', data);
};

export const logout = () => {
  return request.post('/auth/logout');
};

export const getMe = () => {
  return request.get<any, { data: MePayload }>('/auth/me');
};
