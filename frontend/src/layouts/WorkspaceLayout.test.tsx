import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import WorkspaceLayout from './WorkspaceLayout';
import { useAuthStore } from '../store/useAuthStore';

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseAuthStore = vi.mocked(useAuthStore);

const renderLayout = () =>
  render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route path="dashboard" element={<div>dashboard content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );

describe('WorkspaceLayout', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
  });

  it('hides the log center and settings menu items for regular users', () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'user',
        role: 'User',
      },
      logout: vi.fn(),
    } as ReturnType<typeof useAuthStore>);

    renderLayout();

    expect(screen.queryByText('日志中心')).not.toBeInTheDocument();
    expect(screen.queryByText('系统设置')).not.toBeInTheDocument();
  });

  it('keeps the log center menu item for admins while hiding settings', () => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'admin-1',
        email: 'admin@example.com',
        display_name: 'admin',
        role: 'Admin',
      },
      logout: vi.fn(),
    } as ReturnType<typeof useAuthStore>);

    renderLayout();

    expect(screen.getByText('日志中心')).toBeInTheDocument();
    expect(screen.queryByText('系统设置')).not.toBeInTheDocument();
  });
});
