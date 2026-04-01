import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import LogCenterRoutePage from './LogCenterRoutePage';
import { useAuthStore } from '../store/useAuthStore';

vi.mock('./LogCenterPage', () => ({
  default: () => <div>日志中心页面</div>,
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseAuthStore = vi.mocked(useAuthStore);

describe('LogCenterRoutePage', () => {
  it('renders a 403 page for regular users', () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'user',
        role: 'User',
      },
    } as ReturnType<typeof useAuthStore>);

    render(
      <MemoryRouter>
        <LogCenterRoutePage />
      </MemoryRouter>
    );

    expect(screen.getByText('403')).toBeInTheDocument();
    expect(screen.getByText('当前账号无权访问日志中心。')).toBeInTheDocument();
    expect(screen.queryByText('日志中心页面')).not.toBeInTheDocument();
  });

  it('renders the full log center for admins', () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'admin-1',
        email: 'admin@example.com',
        display_name: 'admin',
        role: 'Admin',
      },
    } as ReturnType<typeof useAuthStore>);

    render(
      <MemoryRouter>
        <LogCenterRoutePage />
      </MemoryRouter>
    );

    expect(screen.getByText('日志中心页面')).toBeInTheDocument();
  });
});
