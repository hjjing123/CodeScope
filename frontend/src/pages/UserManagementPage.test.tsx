import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UserManagementPage from './UserManagementPage';
import { listUsers, updateUser, deleteUser } from '../services/users';

vi.mock('../services/users', () => ({
  listUsers: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: () => ({
    user: {
      id: 'admin-1',
      email: 'admin@example.com',
      display_name: 'Admin',
      role: 'Admin',
    },
  }),
}));

const mockedListUsers = vi.mocked(listUsers);
const mockedUpdateUser = vi.mocked(updateUser);
const mockedDeleteUser = vi.mocked(deleteUser);

describe('UserManagementPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();

    mockedListUsers.mockResolvedValue({
      items: [
        {
          id: 'user-1',
          email: 'user@example.com',
          display_name: 'Test User',
          role: 'User',
          is_active: true,
          must_change_password: false,
          created_at: '2026-03-30T08:00:00Z',
        },
      ],
      total: 1,
    });
    mockedUpdateUser.mockResolvedValue({
      id: 'user-1',
      email: 'user@example.com',
      display_name: 'Test User',
      role: 'User',
      is_active: true,
      must_change_password: false,
      created_at: '2026-03-30T08:00:00Z',
    });
    mockedDeleteUser.mockResolvedValue({ removed: true });
  });

  it('renders the page and loads the first page of users', async () => {
    render(<UserManagementPage />);

    expect(screen.getByRole('heading', { name: '用户列表' })).toBeInTheDocument();

    await waitFor(() => {
      expect(mockedListUsers).toHaveBeenCalledWith(1, 20);
    });

    expect(await screen.findByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('Test User')).toBeInTheDocument();
  });
});
