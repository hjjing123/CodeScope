import React, { useEffect, useState } from 'react';
import { Drawer, Typography, Tag, Button, Space, message, Spin, Empty, Tabs } from 'antd';
import { BugOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, CodeOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { FindingService } from '../../services/findings';
import { getVersionFile } from '../../services/projectVersion';
import FindingPathViewer from './FindingPathViewer';
import CodeViewer from './CodeViewer';
import type { Finding, FindingPath, FindingPathStep, FindingLabelRequest } from '../../types/finding';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;

const hasValidLine = (value?: number | null) => typeof value === 'number' && value > 0;

const formatLocation = (filePath?: string | null, line?: number | null) => {
  if (!filePath) {
    return '-';
  }
  return hasValidLine(line) ? `${filePath}:${line}` : filePath;
};

interface FindingDetailPanelProps {
  visible: boolean;
  finding: Finding | null;
  onClose: () => void;
  onUpdate: () => void;
}

const FindingDetailPanel: React.FC<FindingDetailPanelProps> = ({
  visible,
  finding,
  onClose,
  onUpdate,
}) => {
  const [loading, setLoading] = useState(false);
  const [paths, setPaths] = useState<FindingPath[]>([]);
  const [selectedPath, setSelectedPath] = useState<FindingPath | null>(null);
  const [selectedStep, setSelectedStep] = useState<FindingPathStep | null>(null);
  const [sourceFileContent, setSourceFileContent] = useState<string>('');
  const [sourceFileSummary, setSourceFileSummary] = useState<string>('');
  const [loadingSourceFile, setLoadingSourceFile] = useState(false);

  useEffect(() => {
    if (visible && finding) {
      fetchPaths();
    } else {
      setPaths([]);
      setSelectedPath(null);
      setSelectedStep(null);
      setSourceFileContent('');
      setSourceFileSummary('');
    }
  }, [visible, finding]);

  const fetchPaths = async () => {
    if (!finding) return;
    setLoading(true);
    try {
      const res = await FindingService.getFindingPaths(finding.id, { mode: 'all', limit: 10 });
      if (res && res.items && res.items.length > 0) {
        setPaths(res.items);
        setSelectedPath(res.items[0]);
        if (res.items[0].steps && res.items[0].steps.length > 0) {
          void handleStepClick(res.items[0].steps[0], res.items[0], finding.id, finding.version_id);
        }
      } else {
        setPaths([]);
        setSelectedPath(null);
        setSelectedStep(null);
        setSourceFileContent('');
        setSourceFileSummary('');
      }
    } catch (error) {
      console.error('Failed to fetch finding paths:', error);
      message.error('Failed to load finding paths');
    } finally {
      setLoading(false);
    }
  };

  const handlePathSelect = (path: FindingPath) => {
    setSelectedPath(path);
    if (path.steps.length > 0 && finding) {
      void handleStepClick(path.steps[0], path, finding.id, finding.version_id);
    }
  };

  const handleStepClick = async (
    step: FindingPathStep,
    path: FindingPath,
    _findingId: string,
    versionId: string
  ) => {
    setSelectedPath(path);
    setSelectedStep(step);
    if (!step.file) {
      setSourceFileContent('// No source file available for this propagation step');
      setSourceFileSummary('No source file available');
      setLoadingSourceFile(false);
      return;
    }
    setLoadingSourceFile(true);
    try {
      const response = await getVersionFile(versionId, step.file);
      const fileData = response.data;
      setSourceFileContent(fileData.content || '// No source available');
      setSourceFileSummary(
        fileData.truncated
          ? `Showing ${fileData.content.split('\n').length}/${fileData.total_lines} lines`
          : `${fileData.total_lines} lines`
      );
    } catch (error) {
      console.error('Failed to fetch source file:', error);
      setSourceFileContent('// Failed to load full source file');
      setSourceFileSummary('Source preview unavailable');
    } finally {
      setLoadingSourceFile(false);
    }
  };

  const highlightedLines = selectedPath && selectedStep?.file
    ? Array.from(
        new Set(
          selectedPath.steps
            .filter((step) => step.file === selectedStep.file && hasValidLine(step.line))
            .map((step) => step.line as number)
        )
      ).sort((left, right) => left - right)
    : [];

  const handleStatusUpdate = async (status: string, fp_reason?: string) => {
    if (!finding) return;
    try {
      const payload: FindingLabelRequest = { status, fp_reason };
      await FindingService.labelFinding(finding.id, payload);
      message.success(`Finding marked as ${status}`);
      onUpdate();
      onClose();
    } catch (error) {
      console.error('Failed to update finding status:', error);
      message.error('Failed to update status');
    }
  };

  const renderTriageActions = () => (
    <Space>
      <Button
        type={finding?.status === 'confirmed' ? 'primary' : 'default'}
        danger
        size="small"
        icon={<BugOutlined />}
        onClick={() => handleStatusUpdate('confirmed')}
      >
        Confirm
      </Button>
      <Button
        type={finding?.status === 'false_positive' ? 'primary' : 'default'}
        size="small"
        icon={<CloseCircleOutlined />}
        onClick={() => handleStatusUpdate('false_positive', 'Manually marked as FP')}
      >
        Ignore
      </Button>
      <Button
        type={finding?.status === 'wont_fix' ? 'primary' : 'default'}
        size="small"
        icon={<WarningOutlined />}
        onClick={() => handleStatusUpdate('wont_fix', 'Accepted Risk')}
      >
        Risk
      </Button>
      <Button
        type={finding?.status === 'fixed' ? 'primary' : 'default'}
        size="small"
        icon={<CheckCircleOutlined />}
        onClick={() => handleStatusUpdate('fixed')}
      >
        Fixed
      </Button>
    </Space>
  );

  return (
    <Drawer
      title={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          <div className="code-browser-title">
            <Tag color={finding?.severity === 'HIGH' ? 'red' : finding?.severity === 'MED' ? 'orange' : 'blue'}>
              {finding?.severity}
            </Tag>
            <span>{finding?.rule_key}</span>
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 'normal' }}>
              {formatLocation(finding?.file_path, finding?.line_start)}
            </Text>
          </div>
          <div style={{ marginRight: 32 }}>
            {renderTriageActions()}
          </div>
        </div>
      }
      placement="right"
      width="85%"
      onClose={onClose}
      open={visible}
      className="code-browser-drawer"
    >
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
          <Spin size="large" />
        </div>
      ) : finding ? (
        <div className="code-browser-layout">
          {/* Left Pane: Code Viewer (Main) */}
          <div className="code-browser-viewer-panel" style={{ background: '#ffffff' }}>
             <Tabs
              defaultActiveKey="code"
              size="small"
              tabBarStyle={{ margin: 0, paddingLeft: 16, borderBottom: '1px solid #f0f0f0' }}
              items={[
                {
                  key: 'code',
                  label: (<span><CodeOutlined /> Source Code</span>),
                  children: (
                    <div style={{ height: 'calc(100vh - 110px)', background: '#f8fafc', padding: 12 }}>
                      {loadingSourceFile ? (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                          <Spin />
                        </div>
                      ) : (
                        <div style={{ height: '100%', borderRadius: 8, border: '1px solid #d1d5db', overflow: 'hidden' }}>
                         <CodeViewer
                            code={sourceFileContent || '// Select a propagation step to load the full source file'}
                            language="java"
                            fileName={selectedStep ? formatLocation(selectedStep.file, selectedStep.line) : undefined}
                            highlightLines={highlightedLines}
                            focusLine={selectedStep?.line ?? null}
                            startLine={1}
                            summary={sourceFileSummary}
                          />
                        </div>
                      )}
                    </div>
                  ),
                },
                {
                   key: 'details',
                   label: (<span><InfoCircleOutlined /> Raw Details</span>),
                   children: (
                     <div style={{ height: 'calc(100vh - 110px)', background: '#f8fafc', padding: 12 }}>
                       <div style={{ height: '100%', borderRadius: 8, border: '1px solid #d1d5db', overflow: 'hidden' }}>
                         <CodeViewer
                           code={JSON.stringify(finding, null, 2)}
                           language="json"
                           fileName="finding_details.json"
                         />
                       </div>
                     </div>
                   )
                }
              ]}
            />
          </div>

          {/* Right Pane: Propagation Path (Sidebar) */}
          <div className="code-browser-tree-panel" style={{ width: 280, borderRight: 'none', borderLeft: '1px solid #e5e7eb' }}>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              {paths.length > 0 && selectedPath ? (
                <FindingPathViewer
                  paths={paths}
                  selectedPathId={selectedPath.path_id}
                  selectedStepId={selectedStep?.step_id}
                  onPathSelect={handlePathSelect}
                  onStepClick={(step) => handleStepClick(step, selectedPath, finding.id, finding.version_id)}
                />
              ) : (
                <Empty 
                  description={<Text type="secondary">No path available</Text>} 
                  style={{ marginTop: 64 }} 
                  image={Empty.PRESENTED_IMAGE_SIMPLE} 
                />
              )}
            </div>
          </div>
        </div>
      ) : (
        <Empty description="No finding selected" style={{ marginTop: 100 }} />
      )}
    </Drawer>
  );
};

export default FindingDetailPanel;
