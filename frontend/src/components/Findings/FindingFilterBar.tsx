import React, { useEffect, useState } from 'react';
import { Form, Select, Input, Button, Space } from 'antd';
import { SearchOutlined, ClearOutlined } from '@ant-design/icons';
import { getProjects, getVersions } from '../../services/projectVersion';
import type { Project, Version } from '../../types/projectVersion';
import type { FindingListParams } from '../../types/finding';

const { Option } = Select;

interface FindingFilterBarProps {
  initialFilters?: FindingListParams;
  onFilterChange: (filters: FindingListParams) => void;
}

const FindingFilterBar: React.FC<FindingFilterBarProps> = ({
  initialFilters,
  onFilterChange,
}) => {
  const [form] = Form.useForm();
  const [projects, setProjects] = useState<Project[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);

  // Load projects on mount
  useEffect(() => {
    fetchProjects();
  }, []);

  // Load versions when project changes
  const handleProjectChange = (projectId: string) => {
    form.setFieldsValue({ version_id: undefined });
    setVersions([]);
    if (projectId) {
      fetchVersions(projectId);
    }
  };

  const fetchProjects = async () => {
    setLoadingProjects(true);
    try {
      const res = await getProjects({ page: 1, page_size: 100 });
      if (res && res.data && Array.isArray(res.data.items)) {
        setProjects(res.data.items);
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchVersions = async (projectId: string) => {
    setLoadingVersions(true);
    try {
      const res = await getVersions(projectId, { page: 1, page_size: 100 });
      if (res && res.data && Array.isArray(res.data.items)) {
        setVersions(res.data.items);
      }
    } catch (error) {
      console.error('Failed to fetch versions:', error);
    } finally {
      setLoadingVersions(false);
    }
  };

  const handleFinish = (values: any) => {
    // Filter out undefined/empty values
    const filters: FindingListParams = {};
    Object.keys(values).forEach((key) => {
      if (values[key] !== undefined && values[key] !== '' && values[key] !== null) {
        // @ts-ignore
        filters[key] = values[key];
      }
    });
    onFilterChange(filters);
  };

  const handleReset = () => {
    form.resetFields();
    setVersions([]);
    onFilterChange({});
  };

  return (
    <div style={{ padding: '16px 24px', background: '#fff', borderBottom: '1px solid #f0f0f0' }}>
      <Form
        form={form}
        layout="inline"
        onFinish={handleFinish}
        initialValues={initialFilters}
        style={{ gap: '8px' }}
      >
        <Form.Item name="project_id" style={{ minWidth: 200 }}>
          <Select
            placeholder="Select Project"
            allowClear
            loading={loadingProjects}
            onChange={handleProjectChange}
            showSearch
            filterOption={(input, option) =>
              (option?.children as unknown as string)
                ?.toLowerCase()
                .includes(input.toLowerCase())
            }
          >
            {projects.map((p) => (
              <Option key={p.id} value={p.id}>
                {p.name}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item name="version_id" style={{ minWidth: 200 }}>
          <Select
            placeholder="Select Version"
            allowClear
            loading={loadingVersions}
            disabled={!versions.length}
          >
            {versions.map((v) => (
              <Option key={v.id} value={v.id}>
                {v.name}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item name="severity" style={{ minWidth: 120 }}>
          <Select placeholder="Severity" allowClear>
            <Option value="HIGH">High</Option>
            <Option value="MED">Medium</Option>
            <Option value="LOW">Low</Option>
          </Select>
        </Form.Item>

        <Form.Item name="status" style={{ minWidth: 120 }}>
          <Select placeholder="Status" allowClear>
            <Option value="new">New</Option>
            <Option value="confirmed">Confirmed</Option>
            <Option value="false_positive">False Positive</Option>
            <Option value="wont_fix">Won't Fix</Option>
            <Option value="fixed">Fixed</Option>
          </Select>
        </Form.Item>

        <Form.Item name="q">
          <Input placeholder="Rule Key / ID" allowClear />
        </Form.Item>

        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
              Filter
            </Button>
            <Button onClick={handleReset} icon={<ClearOutlined />}>
              Reset
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </div>
  );
};

export default FindingFilterBar;
