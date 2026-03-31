import React, { useEffect, useState } from 'react';
import { Table, Tag, Switch, Button, Popconfirm, message, Space, Typography, Tooltip } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { listUsers, updateUser, deleteUser } from '../services/users';
import type { UserPayload } from '../types/user';
import { useAuthStore } from '../store/useAuthStore';
import dayjs from 'dayjs';

const { Text } = Typography;

const UserManagementPage: React.FC = () => {
  const { user: currentUser } = useAuthStore();
  const [data, setData] = useState<UserPayload[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 });

  const fetchUsers = async (page = 1, pageSize = 20) => {
    setLoading(true);
    try {
      const res = await listUsers(page, pageSize);
      setData(res.items);
      setTotal(res.total);
    } catch (error: any) {
      message.error(error.message || '获取用户列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(pagination.current, pagination.pageSize);
  }, [pagination.current, pagination.pageSize]);

  const handleTableChange = (newPagination: any) => {
    setPagination({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    });
  };

  const handleStatusChange = async (userId: string, checked: boolean) => {
    try {
      await updateUser(userId, { is_active: checked });
      message.success('状态更新成功');
      fetchUsers(pagination.current, pagination.pageSize);
    } catch (error: any) {
      message.error(error.message || '状态更新失败');
    }
  };

  const handleDelete = async (userId: string) => {
    try {
      await deleteUser(userId);
      message.success('用户删除成功');
      if (data.length === 1 && pagination.current > 1) {
        setPagination(prev => ({ ...prev, current: prev.current - 1 }));
      } else {
        fetchUsers(pagination.current, pagination.pageSize);
      }
    } catch (error: any) {
      message.error(error.message || '用户删除失败');
    }
  };

  const columns: ColumnsType<UserPayload> = [
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      render: (text) => <Text strong>{text}</Text>,
    },
    {
      title: '显示名称',
      dataIndex: 'display_name',
      key: 'display_name',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => {
        return <Tag color={role === 'Admin' ? 'purple' : 'default'}>{role}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive, record) => {
        const isSelf = record.id === currentUser?.id;
        return (
          <Switch
            checked={isActive}
            size="small"
            disabled={isSelf}
            onChange={(checked) => handleStatusChange(record.id, checked)}
          />
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => {
        const isSelf = record.id === currentUser?.id;
        return (
          <Space size="middle">
            <Tooltip title={isSelf ? '不能删除自己' : '删除用户'}>
              <Popconfirm
                title="确定要删除该用户吗？"
                onConfirm={() => handleDelete(record.id)}
                disabled={isSelf}
                okText="确定"
                cancelText="取消"
              >
                <Button type="text" danger disabled={isSelf} icon={<DeleteOutlined />} />
              </Popconfirm>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ padding: '16px 24px 24px', background: '#fff', minHeight: '100%' }}>
      <div style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>用户列表</h2>
      </div>
      
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
      />
    </div>
  );
};

export default UserManagementPage;
