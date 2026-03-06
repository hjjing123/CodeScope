import React, { useEffect, useState, useRef } from 'react';
import { Card, List, Tag, Typography, Button, Empty, Alert } from 'antd';
import { ReloadOutlined, DownloadOutlined } from '@ant-design/icons';
import { getSelfTestLogs } from '../../services/rules';
import { downloadTaskLogs } from '../../services/logCenter';
import dayjs from 'dayjs';

const { Text } = Typography;

interface LogItem {
  timestamp: string;
  level: string;
  message: string;
  stage: string;
}

interface SelfTestLogViewerProps {
  jobId?: string;
  autoRefresh?: boolean;
  style?: React.CSSProperties;
}

const SelfTestLogViewer: React.FC<SelfTestLogViewerProps> = ({ jobId, autoRefresh = true, style }) => {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = async () => {
    if (!jobId) return;
    try {
      setLoading(true);
      const res = await getSelfTestLogs(jobId);
      setLogs(res.items || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      // Don't show error on every poll failure to avoid flickering if temporary network issue
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (jobId) {
      fetchLogs();
      if (autoRefresh) {
        timerRef.current = setInterval(fetchLogs, 3000);
      }
    } else {
        setLogs([]);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [jobId, autoRefresh]);

  const handleDownload = () => {
      if (jobId) {
          downloadTaskLogs('SELFTEST', jobId);
      }
  };

  if (!jobId) {
      return <Empty description="No active test job" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <Card 
      title="Test Execution Logs" 
      size="small"
      extra={
        <>
            <Button type="text" icon={<ReloadOutlined />} onClick={fetchLogs} loading={loading} />
            <Button type="text" icon={<DownloadOutlined />} onClick={handleDownload} />
        </>
      }
      style={{ ...style }}
      bodyStyle={{ padding: 0, maxHeight: '400px', overflowY: 'auto', backgroundColor: '#fafafa' }}
    >
        {error && <Alert message={error} type="error" showIcon banner />}
        <List
            size="small"
            dataSource={logs}
            renderItem={(item) => (
                <List.Item style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
                    <div style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <Text type="secondary" style={{ fontSize: '12px', fontFamily: 'monospace' }}>
                                {dayjs(item.timestamp).format('HH:mm:ss.SSS')}
                            </Text>
                            <Tag color={item.level === 'ERROR' ? 'red' : (item.level === 'WARN' ? 'orange' : 'blue')} style={{ marginRight: 0 }}>
                                {item.level}
                            </Tag>
                        </div>
                        <div style={{ fontFamily: 'monospace', fontSize: '13px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                            <Text strong style={{ color: '#666', marginRight: 8 }}>[{item.stage}]</Text>
                            {item.message}
                        </div>
                    </div>
                </List.Item>
            )}
            locale={{ emptyText: 'No logs yet' }}
        />
    </Card>
  );
};

export default SelfTestLogViewer;
