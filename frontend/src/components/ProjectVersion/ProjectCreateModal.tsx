import React, { useState } from 'react';
import { Modal, Form, Input, message } from 'antd';
import { createProject } from '../../services/projectVersion';
import type { ProjectCreateRequest } from '../../types/projectVersion';

interface ProjectCreateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const ProjectCreateModal: React.FC<ProjectCreateModalProps> = ({ open, onClose, onSuccess }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (values: ProjectCreateRequest) => {
    setLoading(true);
    try {
      await createProject(values);
      message.success('Project created successfully');
      form.resetFields();
      onSuccess();
      onClose();
    } catch (error) {
      console.error('Failed to create project:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title="Create Project"
      open={open}
      onOk={() => form.submit()}
      onCancel={handleCancel}
      confirmLoading={loading}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
      >
        <Form.Item
          name="name"
          label="Project Name"
          rules={[{ required: true, message: 'Please input the project name!' }]}
        >
          <Input placeholder="Enter project name" />
        </Form.Item>
        <Form.Item
          name="description"
          label="Description"
        >
          <Input.TextArea placeholder="Enter project description" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default ProjectCreateModal;
