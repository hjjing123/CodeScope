import React, { useEffect, useState } from 'react';
import { Table, Space, Button, Popconfirm, message, Tooltip } from 'antd';
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
      message.error('Failed to fetch projects');
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
      message.success('Project deleted successfully');
      void fetchData(pagination.current, pagination.pageSize);
    } catch (error) {
      console.error('Failed to delete project:', error);
      message.error('Failed to delete project');
    }
  };

  const handleProjectClick = (project: Project) => {
    if (onProjectSelect) {
      onProjectSelect(project.id);
    } else {
      navigate(`/projects/${project.id}`);
    }
  };

  const columns: ColumnsType<Project> = [
    {
      title: 'Project Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Project) => (
        <a onClick={() => handleProjectClick(record)} style={{ fontWeight: 'bold' }}>
          {text}
        </a>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
    },
    {
      title: 'Created At',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="Open Project">
            <Button 
              type="text" 
              icon={<FolderOpenOutlined />} 
              onClick={() => handleProjectClick(record)} 
            />
          </Tooltip>
          <Tooltip title="Delete Project">
            <Popconfirm
              title="Are you sure to delete this project?"
              onConfirm={() => handleDelete(record.id)}
              okText="Yes"
              cancelText="No"
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
        <h2>Projects</h2>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => void fetchData(pagination.current, pagination.pageSize)}
          >
            Refresh
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            New Project
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
