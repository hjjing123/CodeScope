import request from '../utils/request';
import type { UserListPayload, UserPayload, UserUpdateRequest } from '../types/user';

export const listUsers = (page: number = 1, pageSize: number = 20): Promise<UserListPayload> => {
  return request
    .get<any, { data: UserListPayload }>('/users', { params: { page, page_size: pageSize } })
    .then((res) => res.data);
};

export const updateUser = (id: string, payload: UserUpdateRequest): Promise<UserPayload> => {
  return request
    .patch<any, { data: UserPayload }>(`/users/${id}`, payload)
    .then((res) => res.data);
};

export const deleteUser = (id: string): Promise<{ removed: boolean }> => {
  return request
    .delete<any, { data: { removed: boolean } }>(`/users/${id}`)
    .then((res) => res.data);
};
