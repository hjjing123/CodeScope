import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Layout, message, Button, Space, Typography } from 'antd';
import type { TablePaginationConfig } from 'antd/es/table';
import type { FilterValue, SorterResult } from 'antd/es/table/interface';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftOutlined, FileTextOutlined } from '@ant-design/icons';
import FindingFilterBar from '../components/Findings/FindingFilterBar';
import ScanResultFilterBar from '../components/Findings/ScanResultFilterBar';
import FindingListTable from '../components/Findings/FindingListTable';
import ScanResultListTable from '../components/Findings/ScanResultListTable';
import FindingDetailPanel from '../components/Findings/FindingDetailPanel';
import ReportGenerationModal, {
  type ReportGenerationContext,
} from '../components/reports/ReportGenerationModal';
import { createAssessmentSeedChatSession } from '../services/ai';
import { FindingService } from '../services/findings';
import { ReportService } from '../services/report';
import { triggerBrowserDownload } from '../utils/download';
import type {
  Finding,
  FindingListParams,
  ScanResultRow,
  ScanResultListParams,
} from '../types/finding';
import type { ReportJobTriggerPayload } from '../types/report';

const { Content } = Layout;
const { Title, Text } = Typography;

const REPORT_TERMINAL_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELED', 'TIMEOUT']);
const REPORT_POLL_INTERVAL_MS = 3000;
const REPORT_POLL_RETRY_INTERVAL_MS = 5000;

interface LatestReportJobState {
  reportJobId: string;
  jobId: string;
  bundleExpected: boolean;
  status: 'SUBMITTED' | 'SUCCEEDED' | 'FAILED';
  failureMessage?: string;
  bundleArtifactId?: string;
  bundleFileName?: string;
}

const getShortId = (value: string) => value.slice(0, 8);

const getArtifactFileName = (displayName?: string) => {
  if (!displayName) {
    return 'report_bundle.zip';
  }
  const segments = displayName.split('/');
  return segments[segments.length - 1] || 'report_bundle.zip';
};

const getErrorMessage = (error: unknown, fallback: string) => {
  const responseData = (error as {
    response?: { data?: { error?: { message?: string }; message?: string } };
  })?.response?.data;
  return responseData?.error?.message || responseData?.message || fallback;
};

const getReportNoticePalette = (status: LatestReportJobState['status']) => {
  if (status === 'FAILED') {
    return {
      background: '#fef2f2',
      border: '#fecaca',
      accent: '#b91c1c',
    };
  }

  if (status === 'SUCCEEDED') {
    return {
      background: '#ecfeff',
      border: '#a5f3fc',
      accent: '#0f766e',
    };
  }

  return {
    background: '#eff6ff',
    border: '#bfdbfe',
    accent: '#1d4ed8',
  };
};

const FindingsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialJobId = searchParams.get('job_id');

  const [viewMode, setViewMode] = useState<'scan-list' | 'finding-list'>(
    initialJobId ? 'finding-list' : 'scan-list'
  );

  const [loadingFindings, setLoadingFindings] = useState(false);
  const [findingsData, setFindingsData] = useState<Finding[]>([]);
  const [findingsTotal, setFindingsTotal] = useState(0);
  const [findingFilters, setFindingFilters] = useState<FindingListParams>({
    page: 1,
    page_size: 20,
    job_id: initialJobId || undefined,
  });
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [openingFindingId, setOpeningFindingId] = useState<string | null>(null);
  const [selectedFindingIds, setSelectedFindingIds] = useState<string[]>([]);
  const [reportModalContext, setReportModalContext] =
    useState<ReportGenerationContext | null>(null);
  const [latestReportJob, setLatestReportJob] = useState<LatestReportJobState | null>(null);
  const [downloadingBundleJobId, setDownloadingBundleJobId] = useState<string | null>(null);

  const [loadingScans, setLoadingScans] = useState(false);
  const [scanData, setScanData] = useState<ScanResultRow[]>([]);
  const [scanTotal, setScanTotal] = useState(0);
  const [scanFilters, setScanFilters] = useState<ScanResultListParams>({
    page: 1,
    page_size: 20,
  });

  const reportPollTimersRef = useRef<Map<string, number>>(new Map());
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      reportPollTimersRef.current.forEach((timer) => {
        window.clearTimeout(timer);
      });
      reportPollTimersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const jobId = searchParams.get('job_id');
    if (jobId) {
      setViewMode('finding-list');
      setFindingFilters((prev) => ({ ...prev, job_id: jobId }));
    } else {
      setViewMode('scan-list');
    }
  }, [searchParams]);

  const fetchFindings = useCallback(async () => {
    if (viewMode !== 'finding-list') {
      return;
    }

    setLoadingFindings(true);
    try {
      const res = await FindingService.listFindings(findingFilters);
      setFindingsData(res.items);
      setFindingsTotal(res.total);
    } catch (error) {
      console.error('Failed to fetch findings:', error);
      message.error('Failed to load findings');
    } finally {
      setLoadingFindings(false);
    }
  }, [findingFilters, viewMode]);

  useEffect(() => {
    void fetchFindings();
  }, [fetchFindings]);

  const fetchScanResults = useCallback(async () => {
    if (viewMode !== 'scan-list') {
      return;
    }

    setLoadingScans(true);
    try {
      const res = await FindingService.listScanResults(scanFilters);
      setScanData(res.items);
      setScanTotal(res.total);
    } catch (error) {
      console.error('Failed to fetch scan results:', error);
      message.error('Failed to load scan results');
    } finally {
      setLoadingScans(false);
    }
  }, [scanFilters, viewMode]);

  useEffect(() => {
    void fetchScanResults();
  }, [fetchScanResults]);

  useEffect(() => {
    setSelectedFindingIds((prev) => {
      const availableIds = new Set(findingsData.map((item) => item.id));
      return prev.filter((id) => availableIds.has(id));
    });
  }, [findingsData]);

  useEffect(() => {
    if (viewMode !== 'finding-list') {
      setSelectedFindingIds([]);
    }
  }, [viewMode]);

  const selectedFindings = useMemo(() => {
    const selectedIdSet = new Set(selectedFindingIds);
    return findingsData.filter((item) => selectedIdSet.has(item.id));
  }, [findingsData, selectedFindingIds]);

  const stopReportJobPolling = useCallback((reportJobId: string) => {
    const timer = reportPollTimersRef.current.get(reportJobId);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      reportPollTimersRef.current.delete(reportJobId);
    }
  }, []);

  const scheduleReportJobPolling = useCallback(
    (reportJobId: string, poll: () => Promise<void>, delayMs = REPORT_POLL_INTERVAL_MS) => {
      if (!isMountedRef.current) {
        return;
      }

      stopReportJobPolling(reportJobId);
      const timer = window.setTimeout(() => {
        void poll();
      }, delayMs);
      reportPollTimersRef.current.set(reportJobId, timer);
    },
    [stopReportJobPolling]
  );

  const handleViewReportCenter = useCallback(
    (reportJobId?: string, jobId?: string) => {
      const params = new URLSearchParams();
      if (reportJobId) {
        params.set('report_job_id', reportJobId);
      }
      if (jobId) {
        params.set('job_id', jobId);
      }
      const query = params.toString();
      navigate(query ? `/reports?${query}` : '/reports');
    },
    [navigate]
  );

  const handleDownloadBundle = useCallback(async (
    reportJobId: string,
    artifactId: string,
    fileName: string
  ) => {
    try {
      setDownloadingBundleJobId(reportJobId);
      const blob = await ReportService.downloadReportJobArtifact(reportJobId, artifactId);
      triggerBrowserDownload(blob, fileName);
      message.success('打包文件下载开始');
    } catch (error) {
      console.error('Failed to download bundle artifact:', error);
      message.error(getErrorMessage(error, '打包文件下载失败'));
    } finally {
      if (isMountedRef.current) {
        setDownloadingBundleJobId(null);
      }
    }
  }, []);

  const monitorReportJob = useCallback(
    (payload: ReportJobTriggerPayload) => {
      const poll = async () => {
        try {
          const job = await ReportService.getReportJob(payload.report_job_id);
          if (!REPORT_TERMINAL_STATUSES.has(job.status)) {
            scheduleReportJobPolling(payload.report_job_id, poll);
            return;
          }

          stopReportJobPolling(payload.report_job_id);
          if (!isMountedRef.current) {
            return;
          }

          if (job.status === 'SUCCEEDED') {
            let bundleArtifactId: string | undefined;
            let bundleFileName: string | undefined;

            if (payload.bundle_expected) {
              try {
                const artifacts = await ReportService.listReportJobArtifacts(payload.report_job_id);
                const bundle = artifacts.items.find((item) => item.artifact_type === 'BUNDLE');
                bundleArtifactId = bundle?.artifact_id;
                bundleFileName = getArtifactFileName(bundle?.display_name);
              } catch (error) {
                console.warn('Failed to load report artifacts:', error);
              }
            }

            setLatestReportJob((current) => {
              if (!current || current.reportJobId !== payload.report_job_id) {
                return current;
              }

              return {
                ...current,
                status: 'SUCCEEDED',
                bundleArtifactId,
                bundleFileName,
              };
            });

            message.success(
              payload.bundle_expected && bundleArtifactId
                ? '报告已生成，打包文件已就绪。'
                : '报告已生成，可前往报告中心查看。'
            );
            return;
          }

          const failureMessage =
            job.failure_hint ||
            job.failure_code ||
            `报告任务 ${getShortId(payload.report_job_id)} 生成失败`;

          setLatestReportJob((current) => {
            if (!current || current.reportJobId !== payload.report_job_id) {
              return current;
            }

            return {
              ...current,
              status: 'FAILED',
              failureMessage,
            };
          });
          message.error(failureMessage);
        } catch (error) {
          console.warn('Failed to poll report job:', error);
          scheduleReportJobPolling(
            payload.report_job_id,
            poll,
            REPORT_POLL_RETRY_INTERVAL_MS
          );
        }
      };

      void poll();
    },
    [scheduleReportJobPolling, stopReportJobPolling]
  );

  const buildFindingSetContext = useCallback((items: Finding[]) => {
    if (items.length === 0) {
      message.warning('请先选择至少一条漏洞');
      return null;
    }

    const seed = items[0];
    const mixedJobs = items.some(
      (item) =>
        item.project_id !== seed.project_id ||
        item.version_id !== seed.version_id ||
        item.job_id !== seed.job_id
    );

    if (mixedJobs) {
      message.warning('仅支持同一扫描任务下的漏洞批量生成报告');
      return null;
    }

    return {
      projectId: seed.project_id,
      versionId: seed.version_id,
      jobId: seed.job_id,
      generationMode: 'FINDING_SET' as const,
      findings: items,
      findingCount: items.length,
    };
  }, []);

  const handleFindingFilterChange = (newFilters: FindingListParams) => {
    setFindingFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const handleFindingTableChange = (
    pagination: TablePaginationConfig,
    _filters: Record<string, FilterValue | null>,
    sorter: SorterResult<Finding> | SorterResult<Finding>[]
  ) => {
    const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter;
    const sortField = activeSorter?.field;

    setFindingFilters((prev) => ({
      ...prev,
      page: pagination.current,
      page_size: pagination.pageSize,
      sort_by:
        typeof sortField === 'string' || typeof sortField === 'number'
          ? String(sortField)
          : undefined,
      sort_order: activeSorter?.order || undefined,
    }));
  };

  const handleViewFindingDetail = (finding: Finding) => {
    setSelectedFinding(finding);
    setDetailVisible(true);
  };

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setSelectedFinding(null);
  };

  const handleFindingUpdate = useCallback(() => {
    void fetchFindings();
  }, [fetchFindings]);

  const handleOpenAIReview = async (finding: Finding) => {
    try {
      setOpeningFindingId(finding.id);
      const result = await createAssessmentSeedChatSession(finding.id);
      navigate(`/ai-center?tab=workspace&finding_id=${finding.id}&session_id=${result.session_id}`);
    } catch (error) {
      message.error('打开 AI 承接会话失败');
    } finally {
      setOpeningFindingId(null);
    }
  };

  const handleOpenSelectedReportModal = useCallback(() => {
    const context = buildFindingSetContext(selectedFindings);
    if (context) {
      setReportModalContext(context);
    }
  }, [buildFindingSetContext, selectedFindings]);

  const handleOpenSingleReportModal = useCallback(
    (finding: Finding) => {
      const context = buildFindingSetContext([finding]);
      if (context) {
        setReportModalContext(context);
      }
    },
    [buildFindingSetContext]
  );

  const handleOpenJobAllReportModal = useCallback(() => {
    const seedFinding = findingsData[0];
    if (!findingFilters.job_id || !seedFinding || findingsTotal === 0) {
      message.warning('当前扫描任务暂无可生成的漏洞报告');
      return;
    }

    setReportModalContext({
      projectId: seedFinding.project_id,
      versionId: seedFinding.version_id,
      jobId: seedFinding.job_id,
      generationMode: 'JOB_ALL',
      findings: findingsData,
      findingCount: findingsTotal,
    });
  }, [findingFilters.job_id, findingsData, findingsTotal]);

  const handleReportJobCreated = useCallback(
    (payload: ReportJobTriggerPayload, context: ReportGenerationContext) => {
      setReportModalContext(null);
      setLatestReportJob({
        reportJobId: payload.report_job_id,
        jobId: context.jobId,
        bundleExpected: payload.bundle_expected,
        status: 'SUBMITTED',
      });
      setSelectedFindingIds([]);
      message.success(`已提交报告任务 ${getShortId(payload.report_job_id)}，正在后台生成。`);
      monitorReportJob(payload);
    },
    [monitorReportJob]
  );

  const handleScanFilterChange = (newFilters: ScanResultListParams) => {
    setScanFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const handleScanTableChange = (pagination: { current?: number; pageSize?: number }) => {
    setScanFilters((prev) => ({
      ...prev,
      page: pagination.current,
      page_size: pagination.pageSize,
    }));
  };

  const handleViewScanFindings = (jobId: string) => {
    setSearchParams({ job_id: jobId });
  };

  const handleBackToScans = () => {
    setSearchParams({});
  };

  const reportNoticePalette = latestReportJob
    ? getReportNoticePalette(latestReportJob.status)
    : null;

  return (
    <Content style={{ padding: '24px', minHeight: 280 }}>
      {viewMode === 'scan-list' ? (
        <>
          <ScanResultFilterBar onFilterChange={handleScanFilterChange} />
          <div style={{ marginTop: 16, background: '#fff', padding: 24 }}>
            <div style={{ marginBottom: 16 }}>
              <Title level={4}>Scan Results</Title>
            </div>
            <ScanResultListTable
              loading={loadingScans}
              data={scanData}
              total={scanTotal}
              currentPage={scanFilters.page || 1}
              pageSize={scanFilters.page_size || 20}
              onChange={handleScanTableChange}
              onViewDetails={handleViewScanFindings}
            />
          </div>
        </>
      ) : (
        <>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button icon={<ArrowLeftOutlined />} onClick={handleBackToScans}>
                Back to Scans
              </Button>
              <Title level={4} style={{ margin: 0 }}>
                Findings
              </Title>
            </Space>
          </div>
          <FindingFilterBar onFilterChange={handleFindingFilterChange} />
          <div style={{ marginTop: 16, background: '#fff', padding: 24 }}>
            {latestReportJob && reportNoticePalette && (
              <div
                style={{
                  marginBottom: 16,
                  padding: '12px 16px',
                  border: `1px solid ${reportNoticePalette.border}`,
                  borderRadius: 8,
                  background: reportNoticePalette.background,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <Space direction="vertical" size={2}>
                    <Text strong style={{ color: reportNoticePalette.accent }}>
                      报告任务 {getShortId(latestReportJob.reportJobId)}
                    </Text>
                    <Text type="secondary">
                      {latestReportJob.status === 'SUBMITTED'
                        ? '任务已提交，正在后台生成。'
                        : latestReportJob.status === 'SUCCEEDED'
                          ? latestReportJob.bundleExpected
                            ? latestReportJob.bundleArtifactId
                              ? '报告已生成，可直接下载打包文件或进入报告中心查看。'
                              : '报告已生成，可进入报告中心查看导出记录。'
                            : '报告已生成，可进入报告中心下载。'
                          : latestReportJob.failureMessage || '报告生成失败，请稍后重试。'}
                    </Text>
                  </Space>
                  <Space wrap>
                    {latestReportJob.status === 'SUCCEEDED' &&
                      latestReportJob.bundleArtifactId &&
                      latestReportJob.bundleFileName && (
                        <Button
                          loading={downloadingBundleJobId === latestReportJob.reportJobId}
                          onClick={() =>
                            void handleDownloadBundle(
                              latestReportJob.reportJobId,
                              latestReportJob.bundleArtifactId as string,
                              latestReportJob.bundleFileName as string
                            )
                          }
                        >
                          下载打包文件
                        </Button>
                      )}
                    <Button
                      type="primary"
                      ghost
                      onClick={() =>
                        handleViewReportCenter(
                          latestReportJob.reportJobId,
                          latestReportJob.jobId
                        )
                      }
                    >
                      查看报告中心
                    </Button>
                    <Button type="text" onClick={() => setLatestReportJob(null)}>
                      关闭
                    </Button>
                  </Space>
                </div>
              </div>
            )}

            <div
              style={{
                marginBottom: 16,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <Space wrap>
                <Button
                  icon={<FileTextOutlined />}
                  disabled={selectedFindingIds.length === 0}
                  onClick={handleOpenSelectedReportModal}
                >
                  生成选中报告
                </Button>
                {findingFilters.job_id && (
                  <Button
                    type="primary"
                    ghost
                    icon={<FileTextOutlined />}
                    disabled={loadingFindings || findingsTotal === 0 || findingsData.length === 0}
                    onClick={handleOpenJobAllReportModal}
                  >
                    生成当前任务报告
                  </Button>
                )}
              </Space>

              <Space wrap>
                {selectedFindingIds.length > 0 && (
                  <Text type="secondary">已选 {selectedFindingIds.length} 项</Text>
                )}
                <Button type="link" onClick={() => handleViewReportCenter()}>
                  查看报告中心
                </Button>
              </Space>
            </div>

            <FindingListTable
              loading={loadingFindings}
              data={findingsData}
              total={findingsTotal}
              currentPage={findingFilters.page || 1}
              pageSize={findingFilters.page_size || 20}
              onChange={handleFindingTableChange}
              onViewDetail={handleViewFindingDetail}
              onOpenAIReview={(record) => {
                void handleOpenAIReview(record);
              }}
              openingFindingId={openingFindingId}
              selectedRowKeys={selectedFindingIds}
              onSelectionChange={setSelectedFindingIds}
            />
          </div>
        </>
      )}

      {selectedFinding && (
        <FindingDetailPanel
          visible={detailVisible}
          finding={selectedFinding}
          onClose={handleCloseDetail}
          onUpdate={handleFindingUpdate}
          onGenerateReport={handleOpenSingleReportModal}
        />
      )}

      <ReportGenerationModal
        open={reportModalContext !== null}
        context={reportModalContext}
        onCancel={() => setReportModalContext(null)}
        onSuccess={handleReportJobCreated}
      />
    </Content>
  );
};

export default FindingsPage;
