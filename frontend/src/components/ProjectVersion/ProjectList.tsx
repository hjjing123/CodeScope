import React, { useEffect, useState } from 'react';
import { Table, Space, Button, Popconfirm, message, Tooltip, Badge } from 'antd';
import { PlusOutlined, DeleteOutlined, FolderOpenOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType, TableProps } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import type { Project } from '../../types/projectVersion';
import { getProjects, deleteProject } from '../../services/projectVersion';
import ProjectCreateModal from './ProjectCreateModal';

interface ProjectListProps {
  onProjectSelect?: (projectId: string) => void;
}

interface PaginationState {
  current: number;
  pageSize: number;
  total: number;
}

const ProjectList: React.FC<ProjectListProps> = ({ onProjectSelect }) => {
  const [data, setData] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState<PaginationState>({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [modalVisible, setModalVisible] = useState(false);
  const navigate = useNavigate();

  const fetchData = async (page: number, pageSize: number) => {
    setLoading(true);
    try {
      const res = await getProjects({ page, page_size: pageSize });
      const responseData = res.data;
      setData(responseData.items);
      setPagination((previous) => ({
        ...previous,
        current: page,
        pageSize,
        total: responseData.total,
      }));
    } catch (error) {
      console.error('Failed to fetch projects:', error);
      message.error('获取项目列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData(pagination.current, pagination.pageSize);
  }, []);

  const handleTableChange: TableProps<Project>['onChange'] = (newPagination) => {
    const nextPage = newPagination.current ?? 1;
    const nextPageSize = newPagination.pageSize ?? pagination.pageSize;
    void fetchData(nextPage, nextPageSize);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id);
      message.success('项目删除成功');
      void fetchData(pagination.current, pagination.pageSize);
    } catch (error) {
      console.error('Failed to delete project:', error);
      message.error('项目删除失败');
    }
  };

  const handleProjectClick = (project: Project) => {
    if (onProjectSelect) {
      onProjectSelect(project.id);
    } else {
      navigate('/code-management');
    }
  };

  const columns: ColumnsType<Project> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Project) => (
        <a onClick={() => handleProjectClick(record)} style={{ fontWeight: 'bold' }}>
          {text}
        </a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        let color = 'default';
        let text = status;
        
        if (status === 'SCANNABLE') {
          color = 'success';
          text = '可扫描';
        } else if (status === 'ARCHIVED') {
          color = 'default';
          text = '已归档';
        } else if (status === 'DELETED') {
          color = 'error';
          text = '已删除';
        }

        return <Badge status={color as any} text={text} />;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="进入项目">
            <Button 
              type="text" 
              icon={<FolderOpenOutlined />} 
              onClick={() => handleProjectClick(record)} 
            />
          </Tooltip>
          <Tooltip title="删除项目">
            <Popconfirm
              title="确认删除该项目吗？"
              onConfirm={() => handleDelete(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>项目列表</h2>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => void fetchData(pagination.current, pagination.pageSize)}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            新建项目
          </Button>
        </Space>
      </div>
      
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        pagination={pagination}
        loading={loading}
        onChange={handleTableChange}
      />

      <ProjectCreateModal
        open={modalVisible}
        onClose={() => setModalVisible(false)}
        onSuccess={() => void fetchData(1, pagination.pageSize)}
      />
    </div>
  );
};

export default ProjectList;
