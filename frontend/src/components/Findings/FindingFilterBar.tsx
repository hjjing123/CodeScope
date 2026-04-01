import React, { useEffect, useState } from 'react';
import { Form, Select, Button, Space } from 'antd';
import { SearchOutlined, ClearOutlined } from '@ant-design/icons';
import { getProjects } from '../../services/projectVersion';
import type { Project } from '../../types/projectVersion';
import type { FindingListParams } from '../../types/finding';
import { FINDING_STATUS_FILTER_OPTIONS } from '../../utils/findingStatus';

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
  const [loadingProjects, setLoadingProjects] = useState(false);

  // Load projects on mount
  useEffect(() => {
    fetchProjects();
  }, []);

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

  const handleFinish = (values: Record<string, unknown>) => {
    // Filter out undefined/empty values
    const filters: FindingListParams = {};
    Object.entries(values).forEach(([key, value]) => {
      if (value !== undefined && value !== '' && value !== null) {
        filters[key as keyof FindingListParams] = value as never;
      }
    });
    onFilterChange(filters);
  };

  const handleReset = () => {
    form.resetFields();
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

        <Form.Item name="severity" style={{ minWidth: 120 }}>
          <Select placeholder="Severity" allowClear>
            <Option value="HIGH">High</Option>
            <Option value="MED">Medium</Option>
            <Option value="LOW">Low</Option>
          </Select>
        </Form.Item>

        <Form.Item name="status" style={{ minWidth: 120 }}>
          <Select placeholder="Status" allowClear>
            {FINDING_STATUS_FILTER_OPTIONS.map((option) => (
              <Option key={option.value} value={option.value}>
                {option.label}
              </Option>
            ))}
          </Select>
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
