import React, { useState, useEffect } from 'react';
import { Card, Tabs, Upload, Button, Select, message, Space, Typography } from 'antd';
import { UploadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { getProjects, getVersions } from '../../services/projectVersion';
import { runSelfTest, runSelfTestWithUpload } from '../../services/rules';
import SelfTestLogViewer from './SelfTestLogViewer';
import type { UploadFile, UploadProps } from 'antd/es/upload/interface';
import type { Project, Version } from '../../types/projectVersion';

const { Option } = Select;
const { Text } = Typography;

interface SelfTestPanelProps {
  ruleKey: string;
  getDraftPayload?: () => Record<string, any>; // Function to get current draft content
}

const SelfTestPanel: React.FC<SelfTestPanelProps> = ({ ruleKey, getDraftPayload }) => {
  const [activeTab, setActiveTab] = useState('upload');
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  
  // For Upload
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  // For Project/Version
  const [projects, setProjects] = useState<Project[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [fetchingProjects, setFetchingProjects] = useState(false);
  const [fetchingVersions, setFetchingVersions] = useState(false);

  useEffect(() => {
    if (activeTab === 'version') {
      fetchProjects();
    }
  }, [activeTab]);

  useEffect(() => {
    if (selectedProject) {
      fetchVersions(selectedProject);
    } else {
      setVersions([]);
      setSelectedVersion(null);
    }
  }, [selectedProject]);

  const fetchProjects = async () => {
    setFetchingProjects(true);
    try {
      const res = await getProjects({ page: 1, page_size: 100 });
      setProjects(res.data.items);
    } catch (error) {
      message.error('Failed to load projects');
    } finally {
      setFetchingProjects(false);
    }
  };

  const fetchVersions = async (projectId: string) => {
    setFetchingVersions(true);
    try {
      const res = await getVersions(projectId, { page: 1, page_size: 100 });
      setVersions(res.data.items);
    } catch (error) {
      message.error('Failed to load versions');
    } finally {
      setFetchingVersions(false);
    }
  };

  const handleRun = async () => {
    setLoading(true);
    setJobId(null); // Reset job
    try {
      const draftContent = getDraftPayload ? getDraftPayload() : undefined;
      let res;
      if (activeTab === 'upload') {
        if (fileList.length === 0) {
          message.error('Please upload a file first');
          setLoading(false);
          return;
        }
        const file = fileList[0].originFileObj as File;
        res = await runSelfTestWithUpload(file, {
          rule_key: ruleKey,
          draft_payload: draftContent,
        });
      } else {
        if (!selectedVersion) {
          message.error('Please select a version');
          setLoading(false);
          return;
        }
        res = await runSelfTest({
          rule_key: ruleKey,
          draft_payload: draftContent,
          version_id: selectedVersion,
        });
      }
      if (res && res.selftest_job_id) {
          setJobId(res.selftest_job_id);
          message.success('Self-test started');
      } else {
          message.error('Failed to get job ID');
      }
    } catch (error) {
      console.error(error);
      message.error('Failed to start self-test');
    } finally {
      setLoading(false);
    }
  };

  const uploadProps: UploadProps = {
    onRemove: () => {
      setFileList([]);
    },
    beforeUpload: (file) => {
      setFileList([file]);
      return false; // Prevent automatic upload
    },
    fileList,
  };

  return (
    <Card title="Rule Self-Test" bordered={false} style={{ marginTop: 24 }}>
      <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ marginBottom: 16 }}>
        <Tabs.TabPane tab="Upload Archive" key="upload">
          <Upload {...uploadProps} maxCount={1}>
            <Button icon={<UploadOutlined />}>Select File (zip/tar.gz)</Button>
          </Upload>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">Upload a source code archive to test the rule against.</Text>
          </div>
        </Tabs.TabPane>
        <Tabs.TabPane tab="Select Project Version" key="version">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              placeholder="Select Project"
              style={{ width: '100%' }}
              onChange={setSelectedProject}
              loading={fetchingProjects}
              showSearch
              optionFilterProp="children"
            >
              {projects.map(p => (
                <Option key={p.id} value={p.id}>{p.name}</Option>
              ))}
            </Select>
            <Select
              placeholder="Select Version"
              style={{ width: '100%' }}
              onChange={setSelectedVersion}
              loading={fetchingVersions}
              disabled={!selectedProject}
            >
              {versions.map(v => (
                <Option key={v.id} value={v.id}>{v.name} ({v.status})</Option>
              ))}
            </Select>
          </Space>
        </Tabs.TabPane>
      </Tabs>

      <Button 
        type="primary" 
        icon={<PlayCircleOutlined />} 
        onClick={handleRun} 
        loading={loading}
        block
        style={{ marginBottom: 24 }}
      >
        Run Test
      </Button>

      {jobId && <SelfTestLogViewer jobId={jobId} />}
    </Card>
  );
};

export default SelfTestPanel;
