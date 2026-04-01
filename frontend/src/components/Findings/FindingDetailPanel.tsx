import React, { useCallback, useEffect, useState } from 'react';
import { Drawer, Typography, Tag, Button, Space, message, Spin, Empty, Tabs } from 'antd';
import { BugOutlined, CloseCircleOutlined, WarningOutlined, CodeOutlined, InfoCircleOutlined, RobotOutlined, FileTextOutlined } from '@ant-design/icons';
import { FindingService } from '../../services/findings';
import { getVersionFile } from '../../services/projectVersion';
import FindingPathViewer from './FindingPathViewer';
import FindingAIReviewPanel from './FindingAIReviewPanel';
import CodeViewer from './CodeViewer';
import type {
  Finding,
  FindingHighlightRange,
  FindingPath,
  FindingPathNodeContext,
  FindingPathStep,
  FindingLabelRequest,
  ManualFindingLabelStatus,
} from '../../types/finding';
import { pickPreferredPathStep } from './findingPathGraph';
import { buildFallbackFindingPaths } from './findingPathFallback';
import {
  FINDING_STATUS_LABELS,
  MANUAL_FINDING_STATUS_ACTIONS,
} from '../../utils/findingStatus';
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

const summarizeContext = (context: FindingPathNodeContext) => {
  const rangeLabel = `Lines ${context.start_line}-${context.end_line}`;
  const precise = context.highlight_ranges?.length ? 'precise highlight' : 'line highlight';
  return `${rangeLabel} · ${precise}`;
};

const summarizeFullFile = (totalLines: number, precise: boolean, truncated: boolean) => {
  const coverage = truncated ? `Showing partial file (${totalLines} total lines)` : `Full file · ${totalLines} lines`;
  return `${coverage} · ${precise ? 'precise highlight' : 'line highlight'}`;
};

interface FindingDetailPanelProps {
  visible: boolean;
  finding: Finding | null;
  onClose: () => void;
  onUpdate: () => void;
  onGenerateReport?: (finding: Finding) => void;
}

const FindingDetailPanel: React.FC<FindingDetailPanelProps> = ({
  visible,
  finding,
  onClose,
  onUpdate,
  onGenerateReport,
}) => {
  const [loading, setLoading] = useState(false);
  const [paths, setPaths] = useState<FindingPath[]>([]);
  const [selectedPath, setSelectedPath] = useState<FindingPath | null>(null);
  const [selectedStep, setSelectedStep] = useState<FindingPathStep | null>(null);
  const [sourceFileContent, setSourceFileContent] = useState<string>('');
  const [sourceFileSummary, setSourceFileSummary] = useState<string>('');
  const [sourceStartLine, setSourceStartLine] = useState<number>(1);
  const [highlightRanges, setHighlightRanges] = useState<FindingHighlightRange[]>([]);
  const [focusRange, setFocusRange] = useState<FindingHighlightRange | null>(null);
  const [loadingSourceFile, setLoadingSourceFile] = useState(false);
  const [pathEmptyMessage, setPathEmptyMessage] = useState(DEFAULT_EMPTY_PATH_MESSAGE);

  const applySourceContext = useCallback((context: FindingPathNodeContext, step: FindingPathStep) => {
    setSourceFileContent(context.lines.join('\n') || '// No source available');
    setSourceFileSummary(summarizeContext(context));
    setSourceStartLine(context.start_line || step.line || 1);
    setHighlightRanges(context.highlight_ranges || []);
    setFocusRange(context.focus_range || null);
  }, []);

  const applyFullFilePreview = useCallback((
    content: string,
    totalLines: number,
    truncated: boolean,
    ranges: FindingHighlightRange[],
    focus: FindingHighlightRange | null,
    fallbackLine?: number | null
  ) => {
    setSourceFileContent(content || '// No source available');
    setSourceFileSummary(summarizeFullFile(totalLines, ranges.length > 0, truncated));
    setSourceStartLine(1);
    setHighlightRanges(ranges);
    if (focus) {
      setFocusRange(focus);
      return;
    }
    if (fallbackLine && fallbackLine > 0) {
      setFocusRange({
        start_line: fallbackLine,
        start_column: 1,
        end_line: fallbackLine,
        end_column: 1,
        text: null,
        kind: 'line',
        confidence: 'low',
      });
      return;
    }
    setFocusRange(null);
  }, []);

  const resetPathState = useCallback((emptyMessage = DEFAULT_EMPTY_PATH_MESSAGE) => {
    setPaths([]);
    setSelectedPath(null);
    setSelectedStep(null);
    setSourceFileContent('');
    setSourceFileSummary('');
    setSourceStartLine(1);
    setHighlightRanges([]);
    setFocusRange(null);
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
      setSourceStartLine(1);
      setHighlightRanges([]);
      setFocusRange(null);
      setLoadingSourceFile(false);
      return;
    }
    setLoadingSourceFile(true);
    let context: FindingPathNodeContext | null = null;
    try {
      context = await FindingService.getPathNodeContext(_findingId, step.step_id);
    } catch (error) {
      console.warn('Failed to fetch precise path-node context:', error);
    }

    try {
      const response = await getVersionFile(versionId, step.file, { full: true });
      const fileData = response.data;
      applyFullFilePreview(
        fileData.content || '// No source available',
        fileData.total_lines,
        fileData.truncated,
        context?.highlight_ranges || [],
        context?.focus_range || null,
        step.line
      );
    } catch (error) {
      console.error('Failed to fetch full source file:', error);
      if (context) {
        applySourceContext(context, step);
      } else {
        setSourceFileContent('// Failed to load full source file');
        setSourceFileSummary('Source preview unavailable');
        setSourceStartLine(1);
        setHighlightRanges([]);
        setFocusRange(null);
      }
    } finally {
      setLoadingSourceFile(false);
    }
  }, [applyFullFilePreview, applySourceContext]);

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
    && highlightRanges.length === 0
    ? [selectedStep.line as number]
    : [];

  const resolveStatusErrorMessage = (error: unknown) => {
    const responseData = (error as {
      response?: { data?: { error?: { message?: string }; message?: string } };
    })?.response?.data;
    return responseData?.error?.message || responseData?.message || 'Failed to update status';
  };

  const handleStatusUpdate = async (status: ManualFindingLabelStatus, fp_reason?: string) => {
    if (!finding) return;
    try {
      const payload: FindingLabelRequest = { status, fp_reason };
      await FindingService.labelFinding(finding.id, payload);
      message.success(`Finding marked as ${FINDING_STATUS_LABELS[status]}`);
      onUpdate();
      onClose();
    } catch (error) {
      console.error('Failed to update finding status:', error);
      message.error(resolveStatusErrorMessage(error));
    }
  };

  const renderHeaderActions = () => (
    <Space wrap>
      {finding && onGenerateReport && (
        <Button
          size="small"
          icon={<FileTextOutlined />}
          onClick={() => onGenerateReport(finding)}
        >
          生成报告
        </Button>
      )}
      {MANUAL_FINDING_STATUS_ACTIONS.map((action) => {
        const icon = action.value === 'TP'
          ? <BugOutlined />
          : action.value === 'FP'
            ? <CloseCircleOutlined />
            : <WarningOutlined />;

        return (
          <Button
            key={action.value}
            type={finding?.status === action.value ? 'primary' : 'default'}
            danger={action.danger}
            size="small"
            icon={icon}
            onClick={() => handleStatusUpdate(action.value, action.fpReason)}
          >
            {action.label}
          </Button>
        );
      })}
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
            {renderHeaderActions()}
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
                            highlightRanges={highlightRanges}
                            focusRange={focusRange}
                            focusLine={selectedStep?.line ?? null}
                            startLine={sourceStartLine}
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
                },
                {
                   key: 'ai',
                   label: (<span><RobotOutlined /> AI Review</span>),
                   children: (
                     <div style={{ height: 'calc(100vh - 110px)', overflow: 'auto', background: '#f8fafc' }}>
                       <FindingAIReviewPanel finding={finding} />
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
