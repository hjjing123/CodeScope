import React, { useEffect, useMemo, useState } from 'react';
import { Layout, Breadcrumb, theme, Button, Space, message } from 'antd';
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import TaskList from '../components/ScanTasks/TaskList';
import CreateScanModal from '../components/ScanTasks/CreateScanModal';
import DeleteScanJobModal from '../components/ScanTasks/DeleteScanJobModal';
import ScanDetailDrawer from '../components/ScanTasks/ScanDetailDrawer';
import { useJobs } from '../hooks/useJobs';
import { ScanService } from '../services/scan';
import type { Job, ScanJobDeleteTarget } from '../types/scan';

const { Content } = Layout;

const ScanTasksPage: React.FC = () => {
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();
  const [searchParams] = useSearchParams();
  const initialProjectId = searchParams.get('project_id');
  const initialVersionId = searchParams.get('version_id');
  const shouldOpenCreate = searchParams.get('create') === '1';

  const [isModalOpen, setIsModalOpen] = useState(shouldOpenCreate);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [deleteTargetJob, setDeleteTargetJob] = useState<Job | null>(null);
  const [loadingAction, setLoadingAction] = useState<{
    jobId: string;
    action: 'cancel' | 'retry' | 'delete';
  } | null>(null);

  const initialJobParams = useMemo(
    () => ({
      page: 1,
      page_size: 10,
      job_type: 'SCAN',
      project_id: initialProjectId ?? undefined,
      version_id: initialVersionId ?? undefined,
    }),
    [initialProjectId, initialVersionId]
  );

  const { jobs, loading, total, params, setParams, refresh } = useJobs(initialJobParams);

  useEffect(() => {
    setParams({
      page: 1,
      project_id: initialProjectId ?? undefined,
      version_id: initialVersionId ?? undefined,
    });
  }, [initialProjectId, initialVersionId, setParams]);

  useEffect(() => {
    setIsModalOpen(shouldOpenCreate);
  }, [shouldOpenCreate]);

  const handlePageChange = (page: number, pageSize: number) => {
    setParams({ page, page_size: pageSize });
  };

  const handleViewDetails = (job: Job) => {
    setSelectedJobId(job.id);
    setDrawerVisible(true);
  };

  const handleCancelJob = async (job: Job) => {
    try {
      setLoadingAction({ jobId: job.id, action: 'cancel' });
      await ScanService.cancelJob(job.id);
      message.success('扫描任务已取消');
      refresh();
    } catch (error) {
      console.error('Failed to cancel scan job:', error);
      message.error('取消扫描任务失败');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRetryJob = async (job: Job) => {
    try {
      setLoadingAction({ jobId: job.id, action: 'retry' });
      const result = await ScanService.retryJob(job.id);
      message.success(`已创建重启任务：${result.job_id}`);
      refresh();
    } catch (error) {
      console.error('Failed to retry scan job:', error);
      message.error('重启扫描任务失败');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleDeleteJob = (job: Job) => {
    setDeleteTargetJob(job);
  };

  const submitDeleteJob = async (targets: ScanJobDeleteTarget[]) => {
    if (!deleteTargetJob) {
      return;
    }

    try {
      setLoadingAction({ jobId: deleteTargetJob.id, action: 'delete' });
      const result = await ScanService.deleteJob(deleteTargetJob.id, { targets });
      if (result.warnings.length > 0) {
        message.warning(result.warnings[0]);
      }
      message.success('扫描任务删除完成');
      if (selectedJobId === deleteTargetJob.id) {
        handleDrawerClose();
      }
      setDeleteTargetJob(null);
      refresh();
    } catch (error) {
      console.error('Failed to delete scan job content:', error);
      message.error('删除扫描任务内容失败');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleDrawerClose = () => {
    setDrawerVisible(false);
    setSelectedJobId(null);
  };

  return (
    <Layout style={{ padding: '0 24px 24px', background: 'transparent' }}>
      <Breadcrumb
        style={{ margin: '16px 0' }}
        items={[
          { title: '首页' },
          { title: '扫描任务' },
        ]}
      />
      <Content
        className="scan-tasks-container"
        style={{
          padding: 24,
          margin: 0,
          minHeight: 280,
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>扫描任务列表</h2>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setIsModalOpen(true)}
            >
              新建扫描任务
            </Button>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={() => refresh()} 
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        </div>
        <TaskList 
          jobs={jobs} 
          loading={loading} 
          total={total} 
          page={params.page || 1} 
          pageSize={params.page_size || 10} 
          onPageChange={handlePageChange}
          onViewDetails={handleViewDetails}
          onCancelJob={handleCancelJob}
          onRetryJob={handleRetryJob}
          onDeleteJob={handleDeleteJob}
          loadingAction={loadingAction}
        />
        <CreateScanModal
          open={isModalOpen}
          onCancel={() => setIsModalOpen(false)}
          onSuccess={() => {
            setIsModalOpen(false);
            refresh();
          }}
          initialProjectId={initialProjectId}
          initialVersionId={initialVersionId}
        />
        <ScanDetailDrawer
          visible={drawerVisible}
          jobId={selectedJobId}
          onClose={handleDrawerClose}
        />
        <DeleteScanJobModal
          open={deleteTargetJob !== null}
          job={deleteTargetJob}
          submitting={loadingAction?.action === 'delete'}
          onCancel={() => setDeleteTargetJob(null)}
          onConfirm={submitDeleteJob}
        />
      </Content>
    </Layout>
  );
};

export default ScanTasksPage;
