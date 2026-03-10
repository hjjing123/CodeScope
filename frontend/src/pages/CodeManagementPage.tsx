import React, { useState, useEffect } from 'react';
import { Button, message, Spin } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ProjectList from '../components/ProjectVersion/ProjectList';
import VersionList from '../components/ProjectVersion/VersionList';
import { getProject } from '../services/projectVersion';
import type { Project } from '../types/projectVersion';

const CodeManagementPage: React.FC = () => {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedProjectId) {
      setProject(null);
      return;
    }

    setLoading(true);
    getProject(selectedProjectId)
      .then((response) => {
        setProject(response.data);
      })
      .catch(() => {
        message.error('加载项目详情失败');
        setSelectedProjectId(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedProjectId]);

  if (selectedProjectId) {
    return (
      <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center' }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => setSelectedProjectId(null)}
            style={{ marginRight: 16 }}
          >
            返回项目列表
          </Button>
          {loading ? <Spin /> : project && <h2 style={{ margin: 0 }}>{project.name} - 代码快照记录</h2>}
        </div>
        <VersionList
          projectId={selectedProjectId}
        />
      </div>
    );
  }

  return <ProjectList onProjectSelect={setSelectedProjectId} />;
};

export default CodeManagementPage;
