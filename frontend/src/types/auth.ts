export interface LoginRequest {
  email: string;
  password: string;
}

export type RegisterRole = 'Developer' | 'RedTeam';

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
  role: RegisterRole;
}

export interface AuthTokenPayload {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
  session_id: string;
}

export interface MePayload {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: string;
}

export interface RegisterPayload {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
}
