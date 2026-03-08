import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Register from './Register';

const navigateMock = vi.fn();

vi.mock('../services/auth', () => ({
  register: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

describe('Register', () => {
  it('不展示角色相关特殊提示', () => {
    render(<Register />);

    expect(screen.queryByText('新账号默认普通用户权限')).not.toBeInTheDocument();
    expect(screen.queryByText('默认分配普通用户权限')).not.toBeInTheDocument();
  });

  it('不展示角色选择控件', () => {
    render(<Register />);

    expect(screen.queryByLabelText('角色')).not.toBeInTheDocument();
    expect(screen.queryByText('管理员')).not.toBeInTheDocument();
    expect(screen.queryByText('普通用户')).not.toBeInTheDocument();
  });
});
