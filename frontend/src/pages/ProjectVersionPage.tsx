import React, { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FileOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  PlusOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  archiveVersion,
  createProject,
  createVersion,
  deleteProject,
  deleteVersion,
  downloadImportJobLogs,
  downloadVersionSnapshot,
  getImportJob,
  getImportJobLogs,
  getProjects,
  getVersionFile,
  getVersionTree,
  getVersions,
  setVersionBaseline,
  testGitImportSource,
  triggerGitImport,
  triggerGitSync,
  updateProject,
  uploadImportArchive,
} from '../services/projectVersion';
import type {
  GitImportRequest,
  ImportJobPayload,
  ProjectCreateRequest,
  ProjectPayload,
  ProjectUpdateRequest,
  TaskLogPayload,
  VersionCreateRequest,
  VersionPayload,
  VersionTreeEntryPayload,
} from '../types/projectVersion';
import { useAuthStore } from '../store/useAuthStore';
import './ProjectVersionPage.css';

const { Dragger } = Upload;
const { Text } = Typography;

const PROJECT_ROLE_LABEL: Record<string, string> = {
  Owner: 'Owner',
  Maintainer: 'Maintainer',
  Reader: 'Reader',
};

const PROJECT_STATUS_COLOR: Record<string, string> = {
  NEW: 'default',
  IMPORTED: 'processing',
  SCANNABLE: 'success',
};

const VERSION_STATUS_COLOR: Record<string, string> = {
  READY: 'success',
  ARCHIVED: 'default',
  DELETED: 'error',
};

const IMPORT_STATUS_COLOR: Record<string, string> = {
  PENDING: 'default',
  RUNNING: 'processing',
  SUCCEEDED: 'success',
  FAILED: 'error',
  CANCELED: 'warning',
  TIMEOUT: 'error',
};

const TERMINAL_IMPORT_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELED', 'TIMEOUT']);

interface UploadImportFormValues {
  version_name?: string;
  note?: string;
  idempotency_key?: string;
}

interface GitImportFormValues extends GitImportRequest {
  idempotency_key?: string;
}

interface GitSyncFormValues {
  note?: string;
  idempotency_key?: string;
}

interface FilePreviewState {
  path: string;
  content: string;
  truncated: boolean;
  total_lines: number;
}

const normalizeText = (value: string | null | undefined): string | undefined => {
  const trimmed = (value ?? '').trim();
  return trimmed ? trimmed : undefined;
};

const formatTime = (value: string | null | undefined): string => {
  if (!value) {
    return '--';
  }
  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return value;
  }
  return parsed.format('YYYY-MM-DD HH:mm:ss');
};

const upsertImportJob = (items: ImportJobPayload[], incoming: ImportJobPayload): ImportJobPayload[] => {
  const index = items.findIndex((item) => item.id === incoming.id);
  if (index === -1) {
    return [incoming, ...items].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }

  const next = [...items];
  next[index] = incoming;
  return next.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
};

const ProjectVersionPage: React.FC = () => {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'Admin';

  const [projectLoading, setProjectLoading] = useState(false);
  const [projectKeyword, setProjectKeyword] = useState('');
  const [projectStatusFilter, setProjectStatusFilter] = useState<'ALL' | 'NEW' | 'IMPORTED' | 'SCANNABLE'>('ALL');
  const [projectItems, setProjectItems] = useState<ProjectPayload[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [editProjectOpen, setEditProjectOpen] = useState(false);
  const [createProjectSubmitting, setCreateProjectSubmitting] = useState(false);
  const [editProjectSubmitting, setEditProjectSubmitting] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);

  const [versionLoading, setVersionLoading] = useState(false);
  const [versions, setVersions] = useState<VersionPayload[]>([]);
  const [baselineVersionId, setBaselineVersionId] = useState<string | null>(null);
  const [manualVersionOpen, setManualVersionOpen] = useState(false);
  const [manualVersionSubmitting, setManualVersionSubmitting] = useState(false);
  const [versionActionId, setVersionActionId] = useState<string | null>(null);

  const [browseVersionId, setBrowseVersionId] = useState<string | null>(null);
  const [browsePath, setBrowsePath] = useState('');
  const [treeItems, setTreeItems] = useState<VersionTreeEntryPayload[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [filePreviewOpen, setFilePreviewOpen] = useState(false);
  const [filePreviewLoading, setFilePreviewLoading] = useState(false);
  const [filePreview, setFilePreview] = useState<FilePreviewState | null>(null);

  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [gitSubmitting, setGitSubmitting] = useState(false);
  const [gitTesting, setGitTesting] = useState(false);
  const [gitSyncSubmitting, setGitSyncSubmitting] = useState(false);

  const [importJobs, setImportJobs] = useState<ImportJobPayload[]>([]);
  const [importLogsOpen, setImportLogsOpen] = useState(false);
  const [importLogsLoading, setImportLogsLoading] = useState(false);
  const [activeImportJobId, setActiveImportJobId] = useState<string | null>(null);
  const [activeImportLogs, setActiveImportLogs] = useState<TaskLogPayload | null>(null);
  const [autoRefreshImports, setAutoRefreshImports] = useState(true);
  const [importStatusFilter, setImportStatusFilter] = useState<
    'ALL' | 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELED' | 'TIMEOUT'
  >('ALL');

  const [createProjectForm] = Form.useForm<ProjectCreateRequest>();
  const [editProjectForm] = Form.useForm<ProjectUpdateRequest>();
  const [manualVersionForm] = Form.useForm<VersionCreateRequest>();
  const [uploadImportForm] = Form.useForm<UploadImportFormValues>();
  const [gitImportForm] = Form.useForm<GitImportFormValues>();
  const [gitSyncForm] = Form.useForm<GitSyncFormValues>();

  const selectedProject = useMemo(
    () => projectItems.find((project) => project.id === selectedProjectId) ?? null,
    [projectItems, selectedProjectId]
  );

  const activeImportJob = useMemo(
    () => importJobs.find((job) => job.id === activeImportJobId) ?? null,
    [importJobs, activeImportJobId]
  );

  const filteredProjects = useMemo(() => {
    const keyword = normalizeText(projectKeyword)?.toLowerCase();
    return projectItems.filter((project) => {
      const matchedKeyword =
        !keyword ||
        project.name.toLowerCase().includes(keyword) ||
        (project.description ?? '').toLowerCase().includes(keyword);
      const matchedStatus = projectStatusFilter === 'ALL' || project.status === projectStatusFilter;
      return matchedKeyword && matchedStatus;
    });
  }, [projectItems, projectKeyword, projectStatusFilter]);

  const selectedProjectImportJobs = useMemo(() => {
    if (!selectedProject) {
      return [];
    }
    return importJobs.filter((job) => {
      const matchedProject = job.project_id === selectedProject.id;
      const matchedStatus = importStatusFilter === 'ALL' || job.status === importStatusFilter;
      return matchedProject && matchedStatus;
    });
  }, [importJobs, importStatusFilter, selectedProject]);

  const canProjectWrite = useMemo(() => {
    if (!selectedProject) {
      return false;
    }
    if (isAdmin) {
      return true;
    }
    return selectedProject.my_project_role === 'Owner' || selectedProject.my_project_role === 'Maintainer';
  }, [isAdmin, selectedProject]);

  const canProjectDelete = useMemo(() => {
    if (!selectedProject) {
      return false;
    }
    if (isAdmin) {
      return true;
    }
    return selectedProject.my_project_role === 'Owner';
  }, [isAdmin, selectedProject]);

  const canVersionArchive = isAdmin;

  const loadProjects = async (preserveSelection = true): Promise<void> => {
    setProjectLoading(true);
    try {
      const response = await getProjects({ page: 1, page_size: 200 });
      const items = response.data.items;
      setProjectItems(items);

      const keepCurrent =
        preserveSelection &&
        selectedProjectId !== null &&
        items.some((project) => project.id === selectedProjectId);

      const nextSelectedProjectId = keepCurrent ? selectedProjectId : (items[0]?.id ?? null);
      setSelectedProjectId(nextSelectedProjectId);
    } finally {
      setProjectLoading(false);
    }
  };

  const loadVersions = async (projectId: string): Promise<void> => {
    setVersionLoading(true);
    try {
      const response = await getVersions(projectId, { page: 1, page_size: 200 });
      const nextVersions = response.data.items;
      setVersions(nextVersions);
      setBaselineVersionId(response.data.baseline_version_id);
      setBrowseVersionId((current) => {
        if (current && nextVersions.some((item) => item.id === current)) {
          return current;
        }
        return nextVersions[0]?.id ?? null;
      });
    } finally {
      setVersionLoading(false);
    }
  };

  const loadTree = async (versionId: string, path?: string): Promise<void> => {
    setTreeLoading(true);
    try {
      const response = await getVersionTree(versionId, normalizeText(path));
      setTreeItems(response.data.items);
      setBrowsePath(response.data.root_path || '');
    } finally {
      setTreeLoading(false);
    }
  };

  const openFile = async (path: string): Promise<void> => {
    if (!browseVersionId) {
      return;
    }
    setFilePreviewLoading(true);
    try {
      const response = await getVersionFile(browseVersionId, path);
      setFilePreview(response.data);
      setFilePreviewOpen(true);
    } finally {
      setFilePreviewLoading(false);
    }
  };

  const refreshImportJob = async (jobId: string): Promise<void> => {
    try {
      const response = await getImportJob(jobId);
      const refreshed = response.data;
      setImportJobs((items) => upsertImportJob(items, refreshed));

      if (refreshed.status === 'SUCCEEDED' && selectedProjectId === refreshed.project_id) {
        await loadVersions(refreshed.project_id);
      }

      if (importLogsOpen && activeImportJobId === refreshed.id) {
        const logResponse = await getImportJobLogs(refreshed.id, { tail: 300 });
        setActiveImportLogs(logResponse.data);
      }
    } catch (error) {
      void error;
    }
  };

  const trackImportJob = async (jobId: string): Promise<void> => {
    await refreshImportJob(jobId);
    setActiveImportJobId(jobId);
  };

  const openImportLogs = async (jobId: string): Promise<void> => {
    setImportLogsOpen(true);
    setActiveImportJobId(jobId);
    setImportLogsLoading(true);
    try {
      const response = await getImportJobLogs(jobId, { tail: 300 });
      setActiveImportLogs(response.data);
    } finally {
      setImportLogsLoading(false);
    }
  };

  React.useEffect(() => {
    void loadProjects(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (!selectedProjectId) {
      setVersions([]);
      setBaselineVersionId(null);
      setBrowseVersionId(null);
      setTreeItems([]);
      return;
    }
    void loadVersions(selectedProjectId);
  }, [selectedProjectId]);

  React.useEffect(() => {
    if (!browseVersionId) {
      setTreeItems([]);
      setBrowsePath('');
      return;
    }
    void loadTree(browseVersionId, '');
  }, [browseVersionId]);

  React.useEffect(() => {
    if (!autoRefreshImports) {
      return;
    }

    const runningJobs = importJobs.filter((job) => !TERMINAL_IMPORT_STATUSES.has(job.status));
    if (runningJobs.length === 0) {
      return;
    }

    const timer = window.setInterval(() => {
      runningJobs.forEach((job) => {
        void refreshImportJob(job.id);
      });
    }, 4000);

    return () => {
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importJobs, selectedProjectId, importLogsOpen, activeImportJobId, autoRefreshImports]);

  const handleCreateProject = async (values: ProjectCreateRequest): Promise<void> => {
    setCreateProjectSubmitting(true);
    try {
      await createProject({
        name: values.name,
        description: normalizeText(values.description) ?? null,
      });
      message.success('项目已创建');
      setCreateProjectOpen(false);
      createProjectForm.resetFields();
      await loadProjects(false);
    } finally {
      setCreateProjectSubmitting(false);
    }
  };

  const handleOpenEditProject = (): void => {
    if (!selectedProject) {
      return;
    }
    editProjectForm.setFieldsValue({ description: selectedProject.description ?? '' });
    setEditProjectOpen(true);
  };

  const handleUpdateProject = async (values: ProjectUpdateRequest): Promise<void> => {
    if (!selectedProject) {
      return;
    }
    setEditProjectSubmitting(true);
    try {
      await updateProject(selectedProject.id, {
        description: normalizeText(values.description) ?? null,
      });
      message.success('项目说明已更新');
      setEditProjectOpen(false);
      await loadProjects(true);
    } finally {
      setEditProjectSubmitting(false);
    }
  };

  const handleDeleteProject = async (project: ProjectPayload): Promise<void> => {
    setDeletingProjectId(project.id);
    try {
      await deleteProject(project.id);
      message.success('项目已删除');
      setImportJobs((jobs) => jobs.filter((job) => job.project_id !== project.id));
      if (activeImportJobId && importJobs.some((job) => job.id === activeImportJobId && job.project_id === project.id)) {
        setActiveImportJobId(null);
        setActiveImportLogs(null);
      }
      await loadProjects(false);
    } finally {
      setDeletingProjectId(null);
    }
  };

  const handleCreateManualVersion = async (values: VersionCreateRequest): Promise<void> => {
    if (!selectedProject) {
      return;
    }

    setManualVersionSubmitting(true);
    try {
      await createVersion(selectedProject.id, {
        name: values.name,
        source: values.source,
        snapshot_object_key: values.snapshot_object_key,
        note: normalizeText(values.note) ?? null,
        tag: normalizeText(values.tag) ?? null,
        git_repo_url: normalizeText(values.git_repo_url) ?? null,
        git_ref: normalizeText(values.git_ref) ?? null,
        baseline_of_version_id: values.baseline_of_version_id ?? null,
      });
      message.success('版本创建成功');
      setManualVersionOpen(false);
      manualVersionForm.resetFields();
      await loadVersions(selectedProject.id);
      await loadProjects(true);
    } finally {
      setManualVersionSubmitting(false);
    }
  };

  const handleSetBaseline = async (version: VersionPayload): Promise<void> => {
    setVersionActionId(version.id);
    try {
      await setVersionBaseline(version.id);
      message.success('已设置为基线版本');
      if (selectedProjectId) {
        await loadVersions(selectedProjectId);
        await loadProjects(true);
      }
    } finally {
      setVersionActionId(null);
    }
  };

  const handleArchiveVersion = async (version: VersionPayload): Promise<void> => {
    setVersionActionId(version.id);
    try {
      await archiveVersion(version.id);
      message.success('版本已归档');
      if (selectedProjectId) {
        await loadVersions(selectedProjectId);
        await loadProjects(true);
      }
    } finally {
      setVersionActionId(null);
    }
  };

  const handleDeleteVersion = async (version: VersionPayload): Promise<void> => {
    setVersionActionId(version.id);
    try {
      await deleteVersion(version.id);
      message.success('版本已删除');
      if (selectedProjectId) {
        await loadVersions(selectedProjectId);
        await loadProjects(true);
      }
    } finally {
      setVersionActionId(null);
    }
  };

  const handleUploadImport = async (values: UploadImportFormValues): Promise<void> => {
    if (!selectedProject) {
      return;
    }
    const file = uploadFileList[0]?.originFileObj;
    if (!file) {
      message.warning('请先选择上传文件');
      return;
    }

    setUploadSubmitting(true);
    try {
      const response = await uploadImportArchive(
        selectedProject.id,
        file,
        {
          version_name: normalizeText(values.version_name),
          note: normalizeText(values.note),
        },
        normalizeText(values.idempotency_key)
      );

      await trackImportJob(response.data.import_job_id);
      message.success(response.data.idempotent_replay ? '命中幂等复用，已返回已有任务' : '导入任务已提交');
      if (!response.data.idempotent_replay) {
        uploadImportForm.resetFields();
        setUploadFileList([]);
      }
    } finally {
      setUploadSubmitting(false);
    }
  };

  const handleTestGitImport = async (): Promise<void> => {
    if (!selectedProject) {
      return;
    }
    const values = await gitImportForm.validateFields(['repo_url', 'ref_type', 'ref_value']);
    setGitTesting(true);
    try {
      const response = await testGitImportSource(selectedProject.id, {
        repo_url: values.repo_url,
        ref_type: values.ref_type,
        ref_value: values.ref_value,
      });
      message.success(`引用校验通过，resolved_ref=${response.data.resolved_ref}`);
    } finally {
      setGitTesting(false);
    }
  };

  const handleGitImport = async (values: GitImportFormValues): Promise<void> => {
    if (!selectedProject) {
      return;
    }
    setGitSubmitting(true);
    try {
      const response = await triggerGitImport(
        selectedProject.id,
        {
          repo_url: values.repo_url,
          ref_type: values.ref_type,
          ref_value: values.ref_value,
          credential_id: normalizeText(values.credential_id) ?? null,
          version_name: normalizeText(values.version_name) ?? null,
          note: normalizeText(values.note) ?? null,
        },
        normalizeText(values.idempotency_key)
      );

      await trackImportJob(response.data.import_job_id);
      message.success(response.data.idempotent_replay ? '命中幂等复用，已返回已有任务' : 'Git 导入任务已提交');
    } finally {
      setGitSubmitting(false);
    }
  };

  const handleGitSync = async (values: GitSyncFormValues): Promise<void> => {
    if (!selectedProject) {
      return;
    }
    setGitSyncSubmitting(true);
    try {
      const response = await triggerGitSync(
        selectedProject.id,
        normalizeText(values.note),
        normalizeText(values.idempotency_key)
      );
      await trackImportJob(response.data.import_job_id);
      message.success(response.data.idempotent_replay ? '命中幂等复用，已返回已有任务' : 'Git 同步任务已提交');
    } finally {
      setGitSyncSubmitting(false);
    }
  };

  const handleDownloadImportLogs = async (stage?: string): Promise<void> => {
    if (!activeImportJobId) {
      return;
    }
    const fileName = await downloadImportJobLogs(activeImportJobId, stage);
    message.success(`已下载 ${fileName}`);
  };

  const handleDownloadSnapshot = async (versionId: string): Promise<void> => {
    const fileName = await downloadVersionSnapshot(versionId);
    message.success(`已下载 ${fileName}`);
  };

  const versionColumns: ColumnsType<VersionPayload> = [
    {
      title: '版本名称',
      dataIndex: 'name',
      width: 180,
      render: (value: string, record) => (
        <Space size={8}>
          <span className="project-version-mono">{value}</span>
          {record.id === baselineVersionId ? <Tag color="success">Baseline</Tag> : null}
        </Space>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (value: string) => <Tag color={VERSION_STATUS_COLOR[value] ?? 'default'}>{value}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => <span className="project-version-mono">{formatTime(value)}</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 360,
      render: (_, record) => (
        <Space size={6} wrap>
          <Button
            type="default"
            size="small"
            loading={versionActionId === record.id}
            disabled={record.status !== 'READY' || record.id === baselineVersionId}
            onClick={() => {
              void handleSetBaseline(record);
            }}
          >
            设为基线
          </Button>
          <Button
            type="default"
            size="small"
            icon={<CodeOutlined />}
            onClick={() => {
              setBrowseVersionId(record.id);
            }}
          >
            浏览代码
          </Button>
          <Button
            type="default"
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => {
              void handleDownloadSnapshot(record.id);
            }}
          >
            下载快照
          </Button>
          <Button
            type="default"
            size="small"
            icon={<BranchesOutlined />}
            loading={versionActionId === record.id}
            disabled={!canVersionArchive || record.status === 'ARCHIVED'}
            onClick={() => {
              void handleArchiveVersion(record);
            }}
          >
            归档
          </Button>
          <Popconfirm
            title="确认删除该版本吗？"
            description="删除后将从版本列表隐藏，且不能再读取该版本。"
            onConfirm={() => {
              void handleDeleteVersion(record);
            }}
            okText="确认"
            cancelText="取消"
            disabled={!canVersionArchive}
          >
            <Button
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={versionActionId === record.id}
              disabled={!canVersionArchive}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const importColumns: ColumnsType<ImportJobPayload> = [
    {
      title: '导入任务 ID',
      dataIndex: 'id',
      ellipsis: true,
      width: 240,
      render: (value: string) => <span className="project-version-mono">{value}</span>,
    },
    {
      title: '类型',
      dataIndex: 'import_type',
      width: 90,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag color={IMPORT_STATUS_COLOR[value] ?? 'default'}>{value}</Tag>,
    },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (value: string) => <span className="project-version-mono">{value}</span>,
    },
    {
      title: '版本 ID',
      dataIndex: 'version_id',
      ellipsis: true,
      width: 180,
      render: (value: string | null) => <span className="project-version-mono">{value || '--'}</span>,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (value: string) => <span className="project-version-mono">{formatTime(value)}</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space size={6}>
          <Button
            type="default"
            size="small"
            icon={<FileOutlined />}
            onClick={() => {
              void openImportLogs(record.id);
            }}
          >
            日志
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="project-version-page">
      <section className="project-version-overview" aria-label="页面概览">
        <div className="project-version-overview-main">
          <div>
            <h2>项目与版本管理</h2>
            <p>统一管理项目、版本、导入任务与快照浏览。</p>
          </div>

          <div className="project-version-toolbar-context">
            <Text type="secondary">当前项目</Text>
            <span className="project-version-toolbar-project">{selectedProject?.name ?? '未选择'}</span>
          </div>
        </div>

        <div className="project-version-overview-stats" aria-label="关键指标">
          <article className="project-version-stat-card">
            <span>项目总数</span>
            <strong>{projectItems.length}</strong>
          </article>
          <article className="project-version-stat-card">
            <span>当前项目版本</span>
            <strong>{versions.length}</strong>
          </article>
          <article className="project-version-stat-card">
            <span>会话导入任务</span>
            <strong>{importJobs.length}</strong>
          </article>
        </div>
      </section>

      <section className="project-version-workspace" aria-label="项目与版本操作区">
        <aside className="project-version-projects-panel">
          <div className="project-version-panel-head">
            <div className="project-version-panel-heading">
              <h3>项目目录</h3>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setCreateProjectOpen(true);
                }}
              >
                新建项目
              </Button>
            </div>

            <div className="project-version-panel-filters">
              <Input
                allowClear
                value={projectKeyword}
                onChange={(event) => setProjectKeyword(event.target.value)}
                placeholder="搜索项目名称或说明"
              />
              <Select
                value={projectStatusFilter}
                onChange={(value) => setProjectStatusFilter(value)}
                options={[
                  { label: '全部状态', value: 'ALL' },
                  { label: 'NEW', value: 'NEW' },
                  { label: 'IMPORTED', value: 'IMPORTED' },
                  { label: 'SCANNABLE', value: 'SCANNABLE' },
                ]}
              />
            </div>
            <Text type="secondary">匹配项目：{filteredProjects.length}</Text>
          </div>

          {projectLoading ? (
            <div className="project-version-spin-wrap">
              <Spin />
            </div>
          ) : (
            <List
              className="project-version-project-list"
              dataSource={filteredProjects}
              locale={{ emptyText: <Empty description="暂无项目" /> }}
              renderItem={(project) => {
                const roleLabel = project.my_project_role
                  ? PROJECT_ROLE_LABEL[project.my_project_role] ?? project.my_project_role
                  : isAdmin
                    ? 'Admin'
                    : '--';

                return (
                  <List.Item
                    key={project.id}
                    className={`project-version-project-item${selectedProjectId === project.id ? ' is-active' : ''}`}
                    onClick={() => setSelectedProjectId(project.id)}
                  >
                    <div className="project-version-project-item-head">
                      <h4>{project.name}</h4>
                      <Tag color={PROJECT_STATUS_COLOR[project.status] ?? 'default'}>{project.status}</Tag>
                    </div>
                    <p>{project.description || '暂无项目说明'}</p>
                    <div className="project-version-project-item-foot">
                      <span className="project-version-mono">{project.id}</span>
                      <Tag>{roleLabel}</Tag>
                    </div>
                  </List.Item>
                );
              }}
            />
          )}
        </aside>

        <div className="project-version-detail-panel">
          {!selectedProject ? (
            <Card className="project-version-empty-card" bordered={false}>
              <Empty description="请先选择或创建项目" />
            </Card>
          ) : (
            <>
              <Card className="project-version-project-card" bordered={false}>
                <div className="project-version-project-card-head">
                  <div className="project-version-project-main">
                    <h3>{selectedProject.name}</h3>
                    <p>{selectedProject.description || '暂无项目说明'}</p>
                  </div>
                  <Space className="project-version-project-actions" size={8} wrap>
                    <Tag color={PROJECT_STATUS_COLOR[selectedProject.status] ?? 'default'}>{selectedProject.status}</Tag>
                    {selectedProject.baseline_version_id ? (
                      <Tag icon={<CheckCircleOutlined />} color="success">
                        Baseline 已设置
                      </Tag>
                    ) : (
                      <Tag icon={<ClockCircleOutlined />} color="default">
                        Baseline 未设置
                      </Tag>
                    )}
                    <Button
                      type="default"
                      icon={<EditOutlined />}
                      onClick={handleOpenEditProject}
                      disabled={!canProjectWrite}
                    >
                      编辑说明
                    </Button>
                    <Popconfirm
                      title="确认删除该项目吗？"
                      description="删除后会级联清理该项目的版本、任务和快照。"
                      okText="确认"
                      cancelText="取消"
                      disabled={!canProjectDelete}
                      onConfirm={() => {
                        void handleDeleteProject(selectedProject);
                      }}
                    >
                      <Button
                        danger
                        icon={<DeleteOutlined />}
                        loading={deletingProjectId === selectedProject.id}
                        disabled={!canProjectDelete}
                      >
                        删除项目
                      </Button>
                    </Popconfirm>
                  </Space>
                </div>

                <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="project-version-project-meta">
                  <Descriptions.Item label="Project ID">
                    <span className="project-version-mono project-version-project-id">{selectedProject.id}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="创建时间">{formatTime(selectedProject.created_at)}</Descriptions.Item>
                  <Descriptions.Item label="更新时间">{formatTime(selectedProject.updated_at)}</Descriptions.Item>
                </Descriptions>
              </Card>

              <Tabs
                className="project-version-tabs"
                items={[
                  {
                    key: 'versions',
                    label: '版本管理',
                    children: (
                      <div className="project-version-tab-pane">
                        <Card bordered={false} className="project-version-card">
                          <div className="project-version-card-head">
                            <h4>版本列表</h4>
                            <Space>
                              <Button
                                type="primary"
                                icon={<PlusOutlined />}
                                disabled={!canProjectWrite}
                                onClick={() => {
                                  manualVersionForm.setFieldsValue({ source: 'UPLOAD' });
                                  setManualVersionOpen(true);
                                }}
                              >
                                手动创建版本
                              </Button>
                            </Space>
                          </div>

                          <Table<VersionPayload>
                            className="project-version-table"
                            rowKey="id"
                            size="middle"
                            loading={versionLoading}
                            columns={versionColumns}
                            dataSource={versions}
                            scroll={{ x: 1160 }}
                            pagination={false}
                            locale={{ emptyText: '暂无版本' }}
                          />
                        </Card>
                      </div>
                    ),
                  },
                  {
                    key: 'imports',
                    label: '导入任务',
                    children: (
                      <div className="project-version-tab-pane">
                        <div className="project-version-import-grid">
                          <Card bordered={false} className="project-version-card" title="上传压缩包导入">
                            <Form form={uploadImportForm} layout="vertical" onFinish={(values) => void handleUploadImport(values)}>
                              <Form.Item label="导入文件" required>
                                <Dragger
                                  multiple={false}
                                  maxCount={1}
                                  fileList={uploadFileList}
                                  beforeUpload={() => false}
                                  onChange={({ fileList }) => {
                                    setUploadFileList(fileList.slice(-1));
                                  }}
                                >
                                  <p className="ant-upload-drag-icon">
                                    <InboxOutlined />
                                  </p>
                                  <p className="ant-upload-text">点击或拖拽 zip / tar.gz 到此上传</p>
                                  <p className="ant-upload-hint">上传后会异步执行安全解压与快照归档</p>
                                </Dragger>
                              </Form.Item>
                              <Form.Item name="version_name" label="版本名称（可选）">
                                <Input placeholder="例如: release-2026-03" />
                              </Form.Item>
                              <Form.Item name="note" label="备注（可选）">
                                <Input.TextArea rows={2} placeholder="导入说明" />
                              </Form.Item>
                              <Form.Item name="idempotency_key" label="幂等键（可选）">
                                <Input placeholder="例如: import-upload-001" />
                              </Form.Item>
                              <Button type="primary" htmlType="submit" loading={uploadSubmitting} icon={<UploadOutlined />}>
                                提交 Upload 导入
                              </Button>
                            </Form>
                          </Card>

                          <Card bordered={false} className="project-version-card" title="Git 导入与同步">
                            <Form form={gitImportForm} layout="vertical" onFinish={(values) => void handleGitImport(values)}>
                              <Form.Item name="repo_url" label="仓库地址" rules={[{ required: true, message: '请输入仓库地址' }]}>
                                <Input placeholder="本地路径或 Git URL" />
                              </Form.Item>
                              <div className="project-version-inline-grid">
                                <Form.Item
                                  name="ref_type"
                                  label="引用类型"
                                  initialValue="branch"
                                  rules={[{ required: true, message: '请选择引用类型' }]}
                                >
                                  <Select
                                    options={[
                                      { label: 'branch', value: 'branch' },
                                      { label: 'tag', value: 'tag' },
                                      { label: 'commit', value: 'commit' },
                                    ]}
                                  />
                                </Form.Item>
                                <Form.Item name="ref_value" label="引用值" rules={[{ required: true, message: '请输入引用值' }]}>
                                  <Input placeholder="例如: main / v1.0.0 / commit sha" />
                                </Form.Item>
                              </div>
                              <div className="project-version-inline-grid">
                                <Form.Item name="version_name" label="版本名称（可选）">
                                  <Input placeholder="例如: git-v1" />
                                </Form.Item>
                                <Form.Item name="idempotency_key" label="幂等键（可选）">
                                  <Input placeholder="例如: git-import-001" />
                                </Form.Item>
                              </div>
                              <Form.Item name="note" label="备注（可选）">
                                <Input.TextArea rows={2} placeholder="导入说明" />
                              </Form.Item>
                              <Space wrap>
                                <Button
                                  type="default"
                                  icon={<CheckCircleOutlined />}
                                  loading={gitTesting}
                                  onClick={() => {
                                    void handleTestGitImport();
                                  }}
                                >
                                  测试 Git 引用
                                </Button>
                                <Button type="primary" htmlType="submit" loading={gitSubmitting} icon={<UploadOutlined />}>
                                  提交 Git 导入
                                </Button>
                              </Space>
                            </Form>

                            <div className="project-version-sync-card">
                              <Form form={gitSyncForm} layout="inline" onFinish={(values) => void handleGitSync(values)}>
                                <Form.Item name="note" label="同步备注">
                                  <Input placeholder="本次同步备注" className="project-version-sync-note" />
                                </Form.Item>
                                <Form.Item name="idempotency_key" label="幂等键">
                                  <Input placeholder="sync-001" className="project-version-sync-key" />
                                </Form.Item>
                                <Form.Item>
                                  <Button type="default" htmlType="submit" loading={gitSyncSubmitting} icon={<SyncOutlined />}>
                                    触发 Git 同步
                                  </Button>
                                </Form.Item>
                              </Form>
                            </div>
                          </Card>
                        </div>

                        <Card bordered={false} className="project-version-card" title="导入任务跟踪（当前会话）">
                          <div className="project-version-import-head">
                            <Space size={8} wrap>
                              <Text type="secondary">状态筛选</Text>
                              <Select
                                className="project-version-import-status"
                                value={importStatusFilter}
                                onChange={(value) => setImportStatusFilter(value)}
                                options={[
                                  { label: '全部', value: 'ALL' },
                                  { label: 'PENDING', value: 'PENDING' },
                                  { label: 'RUNNING', value: 'RUNNING' },
                                  { label: 'SUCCEEDED', value: 'SUCCEEDED' },
                                  { label: 'FAILED', value: 'FAILED' },
                                  { label: 'CANCELED', value: 'CANCELED' },
                                  { label: 'TIMEOUT', value: 'TIMEOUT' },
                                ]}
                              />
                              <Text type="secondary">自动刷新</Text>
                              <Switch checked={autoRefreshImports} onChange={setAutoRefreshImports} />
                            </Space>
                          </div>

                          <Alert
                            type="info"
                            showIcon
                            className="project-version-alert"
                            message="后端当前未提供按项目分页查询导入任务接口，此处展示你在当前页面触发并跟踪的任务。"
                          />

                          <Table<ImportJobPayload>
                            className="project-version-table"
                            rowKey="id"
                            size="middle"
                            columns={importColumns}
                            dataSource={selectedProjectImportJobs}
                            scroll={{ x: 980 }}
                            pagination={false}
                            locale={{ emptyText: '当前会话暂无导入任务' }}
                          />
                        </Card>
                      </div>
                    ),
                  },
                  {
                    key: 'snapshot',
                    label: '快照浏览',
                    children: (
                      <div className="project-version-tab-pane">
                        <Card bordered={false} className="project-version-card">
                          <div className="project-version-card-head">
                            <h4>版本快照浏览器</h4>
                            <Space wrap>
                              <Select
                                className="project-version-browser-select"
                                value={browseVersionId ?? undefined}
                                placeholder="请选择版本"
                                options={versions.map((version) => ({
                                  label: `${version.name} (${version.status})`,
                                  value: version.id,
                                }))}
                                onChange={(value) => setBrowseVersionId(value)}
                              />
                              <Button
                                type="default"
                                disabled={!browseVersionId}
                                onClick={() => {
                                  if (!browseVersionId) {
                                    return;
                                  }
                                  const segments = browsePath.split('/').filter(Boolean);
                                  segments.pop();
                                  void loadTree(browseVersionId, segments.join('/'));
                                }}
                              >
                                返回上级
                              </Button>
                              <Button
                                type="default"
                                icon={<DownloadOutlined />}
                                disabled={!browseVersionId}
                                onClick={() => {
                                  if (browseVersionId) {
                                    void handleDownloadSnapshot(browseVersionId);
                                  }
                                }}
                              >
                                下载当前版本快照
                              </Button>
                            </Space>
                          </div>

                          <div className="project-version-browser-path">
                            <Text type="secondary">当前路径：</Text>
                            <span className="project-version-mono">/{browsePath || ''}</span>
                          </div>

                          {treeLoading ? (
                            <div className="project-version-spin-wrap">
                              <Spin />
                            </div>
                          ) : (
                            <Table<VersionTreeEntryPayload>
                              className="project-version-table"
                              rowKey="path"
                              size="middle"
                              dataSource={treeItems}
                              scroll={{ x: 920 }}
                              pagination={false}
                              locale={{ emptyText: browseVersionId ? '目录为空' : '请选择版本后浏览快照' }}
                              columns={[
                                {
                                  title: '名称',
                                  dataIndex: 'name',
                                  render: (value: string, record) => (
                                    <Space size={8}>
                                      {record.node_type === 'dir' ? <FolderOpenOutlined /> : <FileOutlined />}
                                      <span>{value}</span>
                                    </Space>
                                  ),
                                },
                                {
                                  title: '路径',
                                  dataIndex: 'path',
                                  render: (value: string) => <span className="project-version-mono">{value}</span>,
                                },
                                {
                                  title: '类型',
                                  dataIndex: 'node_type',
                                  width: 100,
                                  render: (value: string) => <Tag>{value}</Tag>,
                                },
                                {
                                  title: '大小',
                                  dataIndex: 'size_bytes',
                                  width: 120,
                                  render: (value: number | null) => (value == null ? '--' : `${value} B`),
                                },
                                {
                                  title: '操作',
                                  key: 'actions',
                                  width: 130,
                                  render: (_, record) => {
                                    if (!browseVersionId) {
                                      return null;
                                    }
                                    if (record.node_type === 'dir') {
                                      return (
                                        <Button
                                          type="default"
                                          size="small"
                                          icon={<FolderOpenOutlined />}
                                          onClick={() => {
                                            void loadTree(browseVersionId, record.path);
                                          }}
                                        >
                                          打开
                                        </Button>
                                      );
                                    }
                                    return (
                                      <Button
                                        type="default"
                                        size="small"
                                        icon={<CodeOutlined />}
                                        onClick={() => {
                                          void openFile(record.path);
                                        }}
                                      >
                                        预览
                                      </Button>
                                    );
                                  },
                                },
                              ]}
                            />
                          )}
                        </Card>
                      </div>
                    ),
                  },
                ]}
              />
            </>
          )}
        </div>
      </section>

      <Modal
        open={createProjectOpen}
        title="新建项目"
        onCancel={() => setCreateProjectOpen(false)}
        onOk={() => {
          void createProjectForm.submit();
        }}
        confirmLoading={createProjectSubmitting}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createProjectForm} layout="vertical" onFinish={(values) => void handleCreateProject(values)}>
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input maxLength={255} placeholder="例如: payment-service" />
          </Form.Item>
          <Form.Item name="description" label="项目说明">
            <Input.TextArea rows={3} maxLength={1024} placeholder="可选：描述项目目标与边界" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={editProjectOpen}
        title="编辑项目说明"
        onCancel={() => setEditProjectOpen(false)}
        onOk={() => {
          void editProjectForm.submit();
        }}
        confirmLoading={editProjectSubmitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editProjectForm} layout="vertical" onFinish={(values) => void handleUpdateProject(values)}>
          <Form.Item name="description" label="项目说明">
            <Input.TextArea rows={4} maxLength={1024} placeholder="项目说明" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={manualVersionOpen}
        title="手动创建版本"
        width={720}
        onCancel={() => setManualVersionOpen(false)}
        onOk={() => {
          void manualVersionForm.submit();
        }}
        confirmLoading={manualVersionSubmitting}
        okText="创建版本"
        cancelText="取消"
      >
        <Form form={manualVersionForm} layout="vertical" onFinish={(values) => void handleCreateManualVersion(values)}>
          <div className="project-version-inline-grid">
            <Form.Item
              name="name"
              label="版本名称"
              rules={[{ required: true, message: '请输入版本名称' }]}
            >
              <Input maxLength={255} placeholder="例如: release-2026-03-04" />
            </Form.Item>
            <Form.Item
              name="source"
              label="来源"
              initialValue="UPLOAD"
              rules={[{ required: true, message: '请选择来源' }]}
            >
              <Select
                options={[
                  { label: 'UPLOAD', value: 'UPLOAD' },
                  { label: 'GIT', value: 'GIT' },
                  { label: 'PATCHED', value: 'PATCHED' },
                ]}
              />
            </Form.Item>
          </div>
          <Form.Item
            name="snapshot_object_key"
            label="snapshot_object_key"
            rules={[{ required: true, message: '请输入 snapshot_object_key' }]}
            extra="格式示例：snapshots/<version_id>/snapshot.tar.gz"
          >
            <Input placeholder="snapshots/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/snapshot.tar.gz" />
          </Form.Item>
          <div className="project-version-inline-grid">
            <Form.Item name="baseline_of_version_id" label="基线对比版本（可选）">
              <Select
                allowClear
                placeholder="选择当前项目已有版本"
                options={versions.map((version) => ({ label: `${version.name} (${version.id})`, value: version.id }))}
              />
            </Form.Item>
            <Form.Item name="tag" label="标签（可选）">
              <Input maxLength={64} placeholder="例如: prod" />
            </Form.Item>
          </div>
          <div className="project-version-inline-grid">
            <Form.Item name="git_repo_url" label="Git 仓库（可选）">
              <Input maxLength={1024} placeholder="https://..." />
            </Form.Item>
            <Form.Item name="git_ref" label="Git 引用（可选）">
              <Input maxLength={255} placeholder="branch:main" />
            </Form.Item>
          </div>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} maxLength={1024} placeholder="版本说明" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        open={importLogsOpen}
        width={760}
        onClose={() => setImportLogsOpen(false)}
        title="导入任务日志"
        className="project-version-drawer"
      >
        <Space className="project-version-drawer-head" direction="vertical" size={8}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="任务 ID">
              <span className="project-version-mono">{activeImportJob?.id ?? '--'}</span>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {activeImportJob ? (
                <Tag color={IMPORT_STATUS_COLOR[activeImportJob.status] ?? 'default'}>{activeImportJob.status}</Tag>
              ) : (
                '--'
              )}
            </Descriptions.Item>
            <Descriptions.Item label="阶段">
              <span className="project-version-mono">{activeImportJob?.stage ?? '--'}</span>
            </Descriptions.Item>
            <Descriptions.Item label="失败原因">
              {activeImportJob?.failure_hint || activeImportJob?.failure_code || '--'}
            </Descriptions.Item>
          </Descriptions>
          <Space>
            <Button
              type="default"
              icon={<DownloadOutlined />}
              disabled={!activeImportJobId}
              onClick={() => {
                void handleDownloadImportLogs();
              }}
            >
              下载全部日志
            </Button>
          </Space>
        </Space>

        {importLogsLoading ? (
          <div className="project-version-spin-wrap">
            <Spin />
          </div>
        ) : !activeImportLogs || activeImportLogs.items.length === 0 ? (
          <Alert type="info" showIcon message="暂无日志内容" />
        ) : (
          <Collapse
            items={activeImportLogs.items.map((item) => ({
              key: item.stage,
              label: (
                <div className="project-version-stage-title">
                  <span className="project-version-mono">{item.stage}</span>
                  <span>{item.line_count} 行</span>
                  {item.truncated ? <Tag color="gold">已截断</Tag> : null}
                </div>
              ),
              children: (
                <div className="project-version-log-stage">
                  <div className="project-version-log-toolbar">
                    <Button
                      type="default"
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={() => {
                        void handleDownloadImportLogs(item.stage);
                      }}
                    >
                      下载该阶段日志
                    </Button>
                  </div>
                  <div className="project-version-log-lines" role="log" aria-live="polite">
                    {item.lines.map((line, index) => (
                      <p key={`${item.stage}-${index}`} className="project-version-log-line">
                        <span className="project-version-log-line-no">{index + 1}</span>
                        <span className="project-version-log-line-text">{line}</span>
                      </p>
                    ))}
                  </div>
                </div>
              ),
            }))}
          />
        )}
      </Drawer>

      <Drawer
        open={filePreviewOpen}
        width={780}
        onClose={() => setFilePreviewOpen(false)}
        title="文件预览"
        className="project-version-drawer"
      >
        {filePreviewLoading ? (
          <div className="project-version-spin-wrap">
            <Spin />
          </div>
        ) : filePreview ? (
          <>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="路径">
                <span className="project-version-mono">{filePreview.path}</span>
              </Descriptions.Item>
              <Descriptions.Item label="总行数">{filePreview.total_lines}</Descriptions.Item>
              <Descriptions.Item label="状态">
                {filePreview.truncated ? <Tag color="warning">内容已截断</Tag> : <Tag color="success">完整</Tag>}
              </Descriptions.Item>
            </Descriptions>
            <div className="project-version-file-preview">
              <pre>{filePreview.content}</pre>
            </div>
          </>
        ) : (
          <Alert type="info" showIcon message="暂无文件内容" />
        )}
      </Drawer>
    </div>
  );
};

export default ProjectVersionPage;
