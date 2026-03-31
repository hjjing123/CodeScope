export interface UserUpdateRequest {
  display_name?: string;
  role?: string;
  is_active?: boolean;
}

export interface UserPayload {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface UserListPayload {
  items: UserPayload[];
  total: number;
}
