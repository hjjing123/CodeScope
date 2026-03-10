import React, { useState, useEffect } from 'react';
import { Layout, message } from 'antd';
import FindingFilterBar from '../components/Findings/FindingFilterBar';
import FindingListTable from '../components/Findings/FindingListTable';
import FindingDetailPanel from '../components/Findings/FindingDetailPanel';
import { FindingService } from '../services/findings';
import type { Finding, FindingListParams } from '../types/finding';

const { Content } = Layout;

const FindingsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Finding[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<FindingListParams>({
    page: 1,
    page_size: 20,
  });
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await FindingService.listFindings(filters);
      if (res) {
        setData(res.items);
        setTotal(res.total);
      }
    } catch (error) {
      console.error('Failed to fetch findings:', error);
      message.error('Failed to fetch findings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [filters]);

  const handleFilterChange = (newFilters: FindingListParams) => {
    setFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    setFilters((prev) => ({
      ...prev,
      page: pagination.current,
      page_size: pagination.pageSize,
      sort_by: sorter.field,
      sort_order: sorter.order,
    }));
  };

  const handleViewDetail = (finding: Finding) => {
    setSelectedFinding(finding);
    setDetailVisible(true);
  };

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setSelectedFinding(null);
  };

  const handleFindingUpdate = () => {
    fetchData(); // Refresh list after update
  };

  return (
    <Content style={{ padding: '24px', minHeight: 280 }}>
      <FindingFilterBar onFilterChange={handleFilterChange} />
      <div style={{ marginTop: 16, background: '#fff', padding: 24 }}>
        <FindingListTable
          loading={loading}
          data={data}
          total={total}
          currentPage={filters.page || 1}
          pageSize={filters.page_size || 20}
          onChange={handleTableChange}
          onViewDetail={handleViewDetail}
        />
      </div>
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
