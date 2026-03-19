import React, { useState, useEffect } from 'react';
import { Layout, message, Button, Space, Typography } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftOutlined } from '@ant-design/icons';
import FindingFilterBar from '../components/Findings/FindingFilterBar';
import ScanResultFilterBar from '../components/Findings/ScanResultFilterBar';
import FindingListTable from '../components/Findings/FindingListTable';
import ScanResultListTable from '../components/Findings/ScanResultListTable';
import FindingDetailPanel from '../components/Findings/FindingDetailPanel';
import { createAssessmentSeedChatSession } from '../services/ai';
import { FindingService } from '../services/findings';
import type { Finding, FindingListParams, ScanResultRow, ScanResultListParams } from '../types/finding';

const { Content } = Layout;
const { Title } = Typography;

const FindingsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialJobId = searchParams.get('job_id');

  // View Mode: 'scan-list' or 'finding-list'
  const [viewMode, setViewMode] = useState<'scan-list' | 'finding-list'>(initialJobId ? 'finding-list' : 'scan-list');

  // Findings State
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

  // Scan Results State
  const [loadingScans, setLoadingScans] = useState(false);
  const [scanData, setScanData] = useState<ScanResultRow[]>([]);
  const [scanTotal, setScanTotal] = useState(0);
  const [scanFilters, setScanFilters] = useState<ScanResultListParams>({
    page: 1,
    page_size: 20,
  });

  // Sync viewMode with URL
  useEffect(() => {
    const jobId = searchParams.get('job_id');
    if (jobId) {
      setViewMode('finding-list');
      setFindingFilters(prev => ({ ...prev, job_id: jobId }));
    } else {
      setViewMode('scan-list');
    }
  }, [searchParams]);

  // Fetch Findings
  const fetchFindings = async () => {
    if (viewMode !== 'finding-list') return;
    setLoadingFindings(true);
    try {
      const res = await FindingService.listFindings(findingFilters);
      if (res) {
        setFindingsData(res.items);
        setFindingsTotal(res.total);
      }
    } catch (error) {
      console.error('Failed to fetch findings:', error);
      message.error('Failed to load findings');
    } finally {
      setLoadingFindings(false);
    }
  };

  useEffect(() => {
    fetchFindings();
  }, [findingFilters, viewMode]);

  // Fetch Scan Results
  const fetchScanResults = async () => {
    if (viewMode !== 'scan-list') return;
    setLoadingScans(true);
    try {
      const res = await FindingService.listScanResults(scanFilters);
      if (res) {
        setScanData(res.items);
        setScanTotal(res.total);
      }
    } catch (error) {
      console.error('Failed to fetch scan results:', error);
      message.error('Failed to load scan results');
    } finally {
      setLoadingScans(false);
    }
  };

  useEffect(() => {
    fetchScanResults();
  }, [scanFilters, viewMode]);

  // Handlers for Findings
  const handleFindingFilterChange = (newFilters: FindingListParams) => {
    setFindingFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const handleFindingTableChange = (pagination: any, _filters: any, sorter: any) => {
    setFindingFilters((prev) => ({
      ...prev,
      page: pagination.current,
      page_size: pagination.pageSize,
      sort_by: sorter.field,
      sort_order: sorter.order,
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

  const handleFindingUpdate = () => {
    fetchFindings(); // Refresh list after update
  };

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

  // Handlers for Scan Results
  const handleScanFilterChange = (newFilters: ScanResultListParams) => {
    setScanFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const handleScanTableChange = (pagination: any) => {
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
    // Reset finding filters except pagination defaults if needed, 
    // but keeping them might be better for UX if they return.
    // For now, just clearing the job_id is enough via setSearchParams
  };

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
              <Title level={4} style={{ margin: 0 }}>Findings</Title>
            </Space>
          </div>
          <FindingFilterBar onFilterChange={handleFindingFilterChange} />
          <div style={{ marginTop: 16, background: '#fff', padding: 24 }}>
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
        />
      )}
    </Content>
  );
};

export default FindingsPage;
