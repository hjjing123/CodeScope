import React, { useState } from 'react';
import { Modal, Steps, Button, Form, Input, Upload, message, Select, Card, Space, Tag, Progress } from 'antd';
import { GithubOutlined, InboxOutlined, LinkOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { testGitImport, triggerGitImport, uploadImportFile } from '../../services/projectVersion';

const { Dragger } = Upload;
const { TextArea } = Input;

interface ImportWizardProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
  projectId: string;
}

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
};

const ImportWizard: React.FC<ImportWizardProps> = ({ open, onCancel, onSuccess, projectId }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [importType, setImportType] = useState<'upload' | 'git'>('upload');
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [testingGit, setTestingGit] = useState(false);
  const [gitTestResult, setGitTestResult] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleNext = async () => {
    if (currentStep === 0) {
      setCurrentStep(1);
    } else if (currentStep === 1) {
      try {
        const values = await form.validateFields();
        setLoading(true);

        if (importType === 'upload') {
          if (fileList.length === 0) {
            message.error('请上传文件');
            setLoading(false);
            return;
          }
          const file = fileList[0].originFileObj;
          if (!file) {
            message.error('无法读取上传文件，请重新选择');
            setLoading(false);
            return;
          }
          setUploadProgress(0);
          await uploadImportFile(projectId, file, {
            version_name: values.versionName,
            note: values.note,
          }, {
            onUploadProgress: (event) => {
              if (!event.total || event.total <= 0) {
                return;
              }
              const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
              setUploadProgress(percent);
            },
          });
          setUploadProgress(100);
        } else {
          await triggerGitImport(projectId, {
            repo_url: values.repoUrl,
            ref_type: values.refType,
            ref_value: values.refValue,
            version_name: values.versionName,
            note: values.note,
          });
        }

        message.success('导入任务已触发');
        onSuccess();
        reset();
      } catch (error) {
        setUploadProgress(null);
        message.error(`导入失败: ${getErrorMessage(error, '未知错误')}`);
      } finally {
        setLoading(false);
      }
    }
  };

  const reset = () => {
    setCurrentStep(0);
    setImportType('upload');
    setGitTestResult(null);
    setUploadProgress(null);
    setFileList([]);
    form.resetFields();
    onCancel();
  };

  const handleTestGit = async () => {
    try {
      const values = await form.validateFields(['repoUrl', 'refType', 'refValue']);
      setTestingGit(true);
      const response = await testGitImport(projectId, {
        repo_url: values.repoUrl,
        ref_type: values.refType,
        ref_value: values.refValue,
      });
      setGitTestResult(response.data.resolved_ref);
      message.success('Git 仓库连通性测试成功');
    } catch (error) {
      setGitTestResult(null);
      message.error(`Git 测试失败: ${getErrorMessage(error, '未知错误')}`);
    } finally {
      setTestingGit(false);
    }
  };

  const steps: Array<{ title: string; content: React.ReactNode }> = [
    {
      title: '选择来源',
      content: (
        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <Space size="large">
            <Card 
              hoverable 
              style={{ width: 240, borderColor: importType === 'upload' ? '#1890ff' : undefined }}
              onClick={() => setImportType('upload')}
            >
              <InboxOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />
              <h3>上传压缩包</h3>
              <p>支持 Zip, Tar.gz 格式</p>
            </Card>
            <Card 
              hoverable 
              style={{ width: 240, borderColor: importType === 'git' ? '#1890ff' : undefined }}
              onClick={() => setImportType('git')}
            >
              <GithubOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />
              <h3>Git 仓库</h3>
              <p>支持 HTTP/HTTPS 协议</p>
            </Card>
          </Space>
        </div>
      ),
    },
    {
      title: '配置详情',
      content: (
        <Form form={form} layout="vertical" style={{ marginTop: 24 }}>
          <Form.Item
            name="versionName"
            label="代码快照名称"
            rules={[{ required: true, message: '请输入代码快照名称' }]}
            tooltip="建议使用语义化命名，如 snapshot-2026-03-07"
          >
            <Input placeholder="例如: snapshot-2026-03-07" />
          </Form.Item>

          {importType === 'upload' ? (
            <Form.Item label="文件上传" required>
              <Dragger
                name="file"
                maxCount={1}
                fileList={fileList}
                beforeUpload={(file) => {
                  // Auto-fill version name if empty
                  if (!form.getFieldValue('versionName')) {
                    form.setFieldsValue({ versionName: file.name.split('.')[0] });
                  }
                  return false;
                }}
                onChange={({ fileList: nextFileList }) => setFileList(nextFileList.slice(-1))}
                onRemove={() => {
                  setFileList([]);
                  setUploadProgress(null);
                }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                <p className="ant-upload-hint">支持单个文件上传，最大 500MB</p>
              </Dragger>
              {loading && uploadProgress !== null ? (
                <Progress percent={uploadProgress} size="small" style={{ marginTop: 12 }} />
              ) : null}
            </Form.Item>
          ) : (
            <>
              <Form.Item
                name="repoUrl"
                label="仓库地址"
                rules={[
                  { required: true, message: '请输入 Git 仓库地址' },
                  { type: 'url', message: '请输入有效的 URL' }
                ]}
              >
                <Input prefix={<LinkOutlined />} placeholder="https://github.com/user/repo.git" />
              </Form.Item>
              <Space style={{ display: 'flex' }} align="baseline">
                <Form.Item
                  name="refType"
                  label="引用类型"
                  initialValue="branch"
                  style={{ width: 120 }}
                >
                  <Select
                    options={[
                      { value: 'branch', label: '分支' },
                      { value: 'tag', label: '标签' },
                      { value: 'commit', label: 'Commit' },
                    ]}
                  />
                </Form.Item>
                <Form.Item
                  name="refValue"
                  label="引用值"
                  rules={[{ required: true, message: '请输入分支/标签/Commit' }]}
                  style={{ flex: 1 }}
                >
                  <Input placeholder="main" />
                </Form.Item>
              </Space>
              <Space size={8} style={{ marginBottom: 12 }}>
                <Button onClick={() => void handleTestGit()} loading={testingGit}>
                  Git 测试
                </Button>
                {gitTestResult && <Tag color="success">解析到 {gitTestResult}</Tag>}
              </Space>
            </>
          )}

          <Form.Item name="note" label="备注">
            <TextArea rows={3} placeholder="可选：输入代码快照备注信息" />
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <Modal
      title="导入代码"
      open={open}
      onCancel={reset}
      width={600}
      footer={
        <div style={{ marginTop: 24 }}>
          {currentStep > 0 && (
            <Button style={{ margin: '0 8px' }} onClick={() => setCurrentStep(currentStep - 1)}>
              上一步
            </Button>
          )}
          {currentStep < steps.length - 1 && (
            <Button type="primary" onClick={handleNext}>
              下一步
            </Button>
          )}
          {currentStep === steps.length - 1 && (
            <Button type="primary" onClick={handleNext} loading={loading}>
              提交
            </Button>
          )}
        </div>
      }
    >
      <Steps current={currentStep} items={steps.map((item) => ({ title: item.title }))} />
      <div className="steps-content">{steps[currentStep].content}</div>
    </Modal>
  );
};

export default ImportWizard;
