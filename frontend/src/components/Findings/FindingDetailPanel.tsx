import React, { useCallback, useEffect, useState } from 'react';
import { Drawer, Typography, Tag, Button, Space, message, Spin, Empty, Tabs } from 'antd';
import { BugOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, CodeOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { FindingService } from '../../services/findings';
import { getVersionFile } from '../../services/projectVersion';
import FindingPathViewer from './FindingPathViewer';
import CodeViewer from './CodeViewer';
import type { Finding, FindingPath, FindingPathStep, FindingLabelRequest } from '../../types/finding';
import { pickPreferredPathStep } from './findingPathGraph';
import { buildFallbackFindingPaths } from './findingPathFallback';
import { formatLocation } from '../../utils/findingLocation';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;
const DEFAULT_EMPTY_PATH_MESSAGE = 'No path available';

const getVulnDisplayName = (finding?: Finding | null) => {
  return finding?.vuln_display_name || finding?.vuln_type || finding?.rule_key || '-';
};

const getEntryDisplay = (finding?: Finding | null) => {
  if (!finding) {
    return '-';
  }
  return finding.entry_display || formatLocation(finding.file_path, finding.line_start);
};

const hasValidLine = (value?: number | null) => typeof value === 'number' && value > 0;

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
  const [pathEmptyMessage, setPathEmptyMessage] = useState(DEFAULT_EMPTY_PATH_MESSAGE);

  const resetPathState = useCallback((emptyMessage = DEFAULT_EMPTY_PATH_MESSAGE) => {
    setPaths([]);
    setSelectedPath(null);
    setSelectedStep(null);
    setSourceFileContent('');
    setSourceFileSummary('');
    setPathEmptyMessage(emptyMessage);
  }, []);

  const handlePathSelect = (path: FindingPath) => {
    setSelectedPath(path);
    const preferredStep = pickPreferredPathStep(path);
    if (preferredStep && finding) {
      void handleStepClick(preferredStep, path, finding.id, finding.version_id);
    }
  };

  const handleStepClick = useCallback(async (
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
  }, []);

  const applyPaths = useCallback(async (nextPaths: FindingPath[], activeFinding: Finding) => {
    setPaths(nextPaths);
    setPathEmptyMessage(DEFAULT_EMPTY_PATH_MESSAGE);

    const initialPath = nextPaths[0] ?? null;
    setSelectedPath(initialPath);

    if (!initialPath) {
      setSelectedStep(null);
      setSourceFileContent('');
      setSourceFileSummary('');
      return;
    }

    const preferredStep = pickPreferredPathStep(initialPath);
    if (preferredStep) {
      await handleStepClick(preferredStep, initialPath, activeFinding.id, activeFinding.version_id);
      return;
    }

    setSelectedStep(null);
    setSourceFileContent('// Select a propagation step to load the full source file');
    setSourceFileSummary('');
  }, [handleStepClick]);

  const resolvePathErrorMessage = (error: unknown) => {
    const responseData = (error as {
      response?: { data?: { error?: { message?: string }; message?: string } };
    })?.response?.data;
    return responseData?.error?.message || responseData?.message || DEFAULT_EMPTY_PATH_MESSAGE;
  };

  const fetchPaths = useCallback(async () => {
    if (!finding) return;

    setLoading(true);
    setPathEmptyMessage(DEFAULT_EMPTY_PATH_MESSAGE);

    try {
      if (!finding.has_path) {
        const fallbackPaths = buildFallbackFindingPaths(finding);
        if (fallbackPaths.length > 0) {
          await applyPaths(fallbackPaths, finding);
        } else {
          resetPathState();
        }
        return;
      }

      const res = await FindingService.getFindingPaths(finding.id, { mode: 'all', limit: 10 });
      const nextPaths = res?.items?.length ? res.items : buildFallbackFindingPaths(finding);

      if (nextPaths.length > 0) {
        await applyPaths(nextPaths, finding);
      } else {
        resetPathState();
      }
    } catch (error) {
      const fallbackPaths = buildFallbackFindingPaths(finding);
      if (fallbackPaths.length > 0) {
        await applyPaths(fallbackPaths, finding);
        return;
      }

      console.error('Failed to fetch finding paths:', error);
      resetPathState(resolvePathErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [applyPaths, finding, resetPathState]);

  useEffect(() => {
    if (visible && finding) {
      void fetchPaths();
    } else {
      resetPathState();
    }
  }, [visible, finding, fetchPaths, resetPathState]);

  const highlightedLines = selectedStep?.file && hasValidLine(selectedStep.line)
    ? [selectedStep.line as number]
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
            <span>{getVulnDisplayName(finding)}</span>
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 'normal' }}>
              {getEntryDisplay(finding)}
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
          <div className="code-browser-tree-panel" style={{ width: 360, borderRight: 'none', borderLeft: '1px solid #e5e7eb' }}>
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
                  description={<Text type="secondary">{pathEmptyMessage}</Text>} 
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
