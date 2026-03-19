import React, { useState, useEffect, useRef } from 'react';
import { Modal, Button, Form, Input, Upload, message, Select, Space, Tag, Progress, Segmented, Steps, Alert } from 'antd';
import { GithubOutlined, InboxOutlined, LinkOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { testGitImport, triggerGitImport, uploadImportFile, getImportJob } from '../../services/projectVersion';
import type { GitImportTestResponse, ImportJob } from '../../types/projectVersion';

const { Dragger } = Upload;
const { TextArea } = Input;

interface ImportWizardProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
  projectId: string;
}

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { error?: { message?: string }; message?: string } } }).response;
    const backendMessage = response?.data?.error?.message || response?.data?.message;
    if (backendMessage) {
      return backendMessage;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
};

const ImportWizard: React.FC<ImportWizardProps> = ({ open, onCancel, onSuccess, projectId }) => {
  const [importType, setImportType] = useState<'upload' | 'git'>('upload');
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [testingGit, setTestingGit] = useState(false);
  const [gitTestResult, setGitTestResult] = useState<GitImportTestResponse | null>(null);
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const repoVisibility = Form.useWatch('repoVisibility', form) ?? 'public';
  const authType = Form.useWatch('authType', form) ?? (repoVisibility === 'private' ? 'https_token' : 'none');

  // Progress polling states
  const [importJobId, setImportJobId] = useState<string | null>(null);
  const [pollingJob, setPollingJob] = useState<ImportJob | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const reset = () => {
    setImportType('upload');
    setGitTestResult(null);
    setUploadProgress(null);
    setFileList([]);
    form.resetFields();
    form.setFieldsValue({
      repoVisibility: 'public',
      authType: 'none',
      refType: undefined,
      refValue: undefined,
    });
    setImportJobId(null);
    setPollingJob(null);
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  useEffect(() => {
    if (!open) {
      reset();
    }
  }, [open]);

  useEffect(() => {
    if (importType !== 'git') {
      return;
    }
    setGitTestResult(null);
    if (repoVisibility === 'public') {
      form.setFieldsValue({
        authType: 'none',
        username: undefined,
        accessToken: undefined,
        sshPrivateKey: undefined,
        sshPassphrase: undefined,
      });
      return;
    }
    if (!authType || authType === 'none') {
      form.setFieldsValue({ authType: 'https_token' });
    }
  }, [authType, form, importType, repoVisibility]);

  useEffect(() => {
    if (importJobId) {
      const poll = async () => {
        try {
          const res = await getImportJob(importJobId);
          setPollingJob(res.data);
          if (res.data.progress?.is_terminal) {
            if (pollTimerRef.current) {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
          }
        } catch (err) {
          console.error('Failed to poll import job', err);
        }
      };

      poll(); // initial call
      pollTimerRef.current = setInterval(() => { void poll(); }, 1500);

      return () => {
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      };
    }
  }, [importJobId]);

  const buildGitPayload = (values: Record<string, unknown>) => ({
    repo_url: String(values.repoUrl || ''),
    repo_visibility: String(values.repoVisibility || 'public') as 'public' | 'private',
    auth_type: String(values.authType || (values.repoVisibility === 'private' ? 'https_token' : 'none')) as 'none' | 'https_token' | 'ssh_key',
    username: values.username ? String(values.username) : undefined,
    access_token: values.accessToken ? String(values.accessToken) : undefined,
    ssh_private_key: values.sshPrivateKey ? String(values.sshPrivateKey) : undefined,
    ssh_passphrase: values.sshPassphrase ? String(values.sshPassphrase) : undefined,
    ref_type: values.refType ? String(values.refType) : undefined,
    ref_value: values.refValue ? String(values.refValue) : undefined,
    version_name: values.versionName ? String(values.versionName) : undefined,
    note: values.note ? String(values.note) : undefined,
  });

  const gitValidationFields = () => {
    const fields = ['repoUrl', 'repoVisibility', 'refType', 'refValue'];
    if (repoVisibility === 'private') {
      fields.push('authType');
      if (authType === 'https_token') {
        fields.push('accessToken');
      }
      if (authType === 'ssh_key') {
        fields.push('sshPrivateKey');
      }
    }
    return fields;
  };

  const renderResolvedRefLabel = (result: GitImportTestResponse) => {
    if (result.auto_detected) {
      return `已自动识别默认引用：${result.resolved_ref}`;
    }
    return `已解析引用：${result.resolved_ref}`;
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      let jobId = '';

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
        const res = await uploadImportFile(projectId, file, {
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
        jobId = res.data.import_job_id;
      } else {
        const res = await triggerGitImport(projectId, buildGitPayload(values));
        jobId = res.data.import_job_id;
      }

      setImportJobId(jobId);
    } catch (error) {
      setUploadProgress(null);
      message.error(`导入触发失败: ${getErrorMessage(error, '未知错误')}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTestGit = async () => {
    try {
      const values = await form.validateFields(gitValidationFields());
      setTestingGit(true);
      const response = await testGitImport(projectId, buildGitPayload(values));
      setGitTestResult(response.data);
      message.success('Git 仓库连通性测试成功');
    } catch (error) {
      setGitTestResult(null);
      message.error(`Git 测试失败: ${getErrorMessage(error, '未知错误')}`);
    } finally {
      setTestingGit(false);
    }
  };

  const renderFormView = () => (
    <>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <Segmented
          options={[
            { label: '上传压缩包', value: 'upload', icon: <InboxOutlined /> },
            { label: 'Git 仓库', value: 'git', icon: <GithubOutlined /> },
          ]}
          value={importType}
          onChange={(val) => setImportType(val as 'upload' | 'git')}
          size="large"
          block
        />
      </div>

      <Form form={form} layout="vertical">
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
              <p className="ant-upload-hint">支持单个文件上传，支持 Zip, Tar.gz 格式</p>
            </Dragger>
            {loading && uploadProgress !== null ? (
              <Progress percent={uploadProgress} size="small" style={{ marginTop: 12 }} />
            ) : null}
          </Form.Item>
        ) : (
          <>
            <Form.Item
              name="repoVisibility"
              label="仓库类型"
              initialValue="public"
              rules={[{ required: true, message: '请选择仓库类型' }]}
            >
              <Segmented
                options={[
                  { label: '公开仓库', value: 'public' },
                  { label: '私有仓库', value: 'private' },
                ]}
                block
              />
            </Form.Item>

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

            {repoVisibility === 'private' ? (
              <>
                <Form.Item
                  name="authType"
                  label="认证方式"
                  initialValue="https_token"
                  rules={[{ required: true, message: '请选择认证方式' }]}
                >
                  <Segmented
                    options={[
                      { label: 'HTTPS Token', value: 'https_token' },
                      { label: 'SSH Key', value: 'ssh_key' },
                    ]}
                    block
                  />
                </Form.Item>

                {authType === 'https_token' ? (
                  <>
                    <Form.Item name="username" label="用户名（可选）" initialValue="git">
                      <Input placeholder="默认 git / oauth2" />
                    </Form.Item>
                    <Form.Item
                      name="accessToken"
                      label="访问令牌"
                      rules={[{ required: true, message: '请输入访问令牌' }]}
                    >
                      <Input.Password placeholder="请输入 HTTPS Token" />
                    </Form.Item>
                  </>
                ) : (
                  <>
                    <Form.Item
                      name="sshPrivateKey"
                      label="SSH 私钥"
                      rules={[{ required: true, message: '请输入 SSH 私钥' }]}
                    >
                      <TextArea rows={6} placeholder="请输入 SSH 私钥内容" />
                    </Form.Item>
                    <Tag color="gold" style={{ marginBottom: 16, display: 'inline-block' }}>
                      当前暂不支持带口令的 SSH Key
                    </Tag>
                  </>
                )}
              </>
            ) : null}

            <Space style={{ display: 'flex' }} align="baseline">
              <Form.Item
                name="refType"
                label="引用类型"
                style={{ width: 120 }}
                rules={[
                  {
                    validator: async (_, value) => {
                      const refValue = form.getFieldValue('refValue');
                      if (refValue && !value) {
                        throw new Error('请先选择引用类型');
                      }
                    },
                  },
                ]}
              >
                <Select
                  allowClear
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
                style={{ flex: 1 }}
                rules={[
                  {
                    validator: async (_, value) => {
                      const refType = form.getFieldValue('refType');
                      if (value && !refType) {
                        throw new Error('请先选择引用类型');
                      }
                      if (refType && !value) {
                        throw new Error('请输入引用值，或清空引用类型使用默认分支');
                      }
                    },
                  },
                ]}
              >
                <Input placeholder="可选，例如 main / v1.0.0 / commit SHA；留空则自动识别默认分支" />
              </Form.Item>
            </Space>
            <Space size={8} style={{ marginBottom: 12 }}>
              <Button onClick={() => void handleTestGit()} loading={testingGit}>
                Git 测试
              </Button>
              {gitTestResult && (
                <Tag color="success">{renderResolvedRefLabel(gitTestResult)}</Tag>
              )}
            </Space>
          </>
        )}

        <Form.Item name="note" label="备注">
          <TextArea rows={3} placeholder="可选：输入代码快照备注信息" />
        </Form.Item>
      </Form>
    </>
  );

  const renderProgressView = () => {
    if (!pollingJob || !pollingJob.progress) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Progress type="circle" percent={0} status="active" />
          <div style={{ marginTop: 16 }}>任务初始化中...</div>
        </div>
      );
    }

    const { percent, stages } = pollingJob.progress;
    const isFailed = pollingJob.status === 'FAILED' || pollingJob.status === 'TIMEOUT';
    const isSucceeded = pollingJob.status === 'SUCCEEDED';

    const stepItems = stages.map(stage => {
      let stepStatus: 'wait' | 'process' | 'finish' | 'error' = 'wait';
      if (stage.status === 'SUCCEEDED') stepStatus = 'finish';
      else if (stage.status === 'FAILED' || stage.status === 'TIMEOUT') stepStatus = 'error';
      else if (stage.status === 'RUNNING') stepStatus = 'process';

      return {
        title: stage.display_name,
        status: stepStatus,
      };
    });

    return (
      <div style={{ padding: '20px 0' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Progress 
            type="circle" 
            percent={percent} 
            status={isFailed ? 'exception' : isSucceeded ? 'success' : 'active'} 
          />
          <div style={{ marginTop: 16, fontSize: 16, fontWeight: 500 }}>
            {isFailed ? '导入失败' : isSucceeded ? '导入完成' : '代码导入中...'}
          </div>
        </div>

        <Steps 
          direction="vertical" 
          size="small" 
          current={pollingJob.progress.completed_stages} 
          items={stepItems} 
          style={{ maxWidth: 400, margin: '0 auto' }}
        />

        {isFailed && (
          <Alert
            message="任务失败详情"
            description={pollingJob.failure_hint || pollingJob.failure_code || '未知错误'}
            type="error"
            showIcon
            style={{ marginTop: 24 }}
          />
        )}
      </div>
    );
  };

  return (
    <Modal
      title="导入代码"
      open={open}
      onCancel={() => {
        if (importJobId && !pollingJob?.progress?.is_terminal) {
          Modal.confirm({
            title: '正在导入中',
            content: '代码正在后台导入，关闭弹窗不会终止任务。是否确认关闭？',
            onOk: onCancel,
          });
        } else {
          onCancel();
        }
      }}
      width={600}
      footer={
        <div style={{ marginTop: 24 }}>
          {!importJobId ? (
            <>
              <Button style={{ margin: '0 8px' }} onClick={onCancel}>
                取消
              </Button>
              <Button type="primary" onClick={() => void handleSubmit()} loading={loading}>
                提交
              </Button>
            </>
          ) : (
            <>
              {(!pollingJob || !pollingJob.progress?.is_terminal) && (
                <Button onClick={onCancel}>后台运行</Button>
              )}
              {pollingJob?.status === 'FAILED' && (
                <Button onClick={() => setImportJobId(null)}>返回重试</Button>
              )}
              {pollingJob?.status === 'SUCCEEDED' && (
                <Button type="primary" onClick={() => {
                  message.success('代码快照导入成功');
                  onSuccess();
                }}>
                  完成
                </Button>
              )}
            </>
          )}
        </div>
      }
      destroyOnClose
    >
      <div className="import-wizard-content" style={{ minHeight: 300 }}>
        {!importJobId ? renderFormView() : renderProgressView()}
      </div>
    </Modal>
  );
};

export default ImportWizard;
