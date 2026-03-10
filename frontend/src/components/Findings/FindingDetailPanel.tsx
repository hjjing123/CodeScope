import React, { useEffect, useState } from 'react';
import { Drawer, Typography, Tag, Button, Space, message, Spin, Empty, Tabs } from 'antd';
import { BugOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, CodeOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { FindingService } from '../../services/findings';
import FindingPathViewer from './FindingPathViewer';
import CodeViewer from './CodeViewer';
import type { Finding, FindingPath, FindingPathStep, FindingLabelRequest } from '../../types/finding';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;
const { TabPane } = Tabs;

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
  const [codeContext, setCodeContext] = useState<string>('');
  const [loadingContext, setLoadingContext] = useState(false);

  useEffect(() => {
    if (visible && finding) {
      fetchPaths();
    } else {
      setPaths([]);
      setSelectedPath(null);
      setSelectedStep(null);
      setCodeContext('');
    }
  }, [visible, finding]);

  const fetchPaths = async () => {
    if (!finding) return;
    setLoading(true);
    try {
      const res = await FindingService.getFindingPaths(finding.id);
      if (res && res.items && res.items.length > 0) {
        setPaths(res.items);
        setSelectedPath(res.items[0]);
        // Select first step of first path by default if available
        if (res.items[0].steps && res.items[0].steps.length > 0) {
          handleStepClick(res.items[0].steps[0], finding.id);
        }
      }
    } catch (error) {
      console.error('Failed to fetch finding paths:', error);
      message.error('Failed to load finding paths');
    } finally {
      setLoading(false);
    }
  };

  const handleStepClick = async (step: FindingPathStep, findingId: string) => {
    setSelectedStep(step);
    setLoadingContext(true);
    try {
      const context = await FindingService.getPathNodeContext(findingId, step.step_id);
      if (context && context.lines) {
        setCodeContext(context.lines.join('\n'));
      } else {
        setCodeContext('// No code context available');
      }
    } catch (error) {
      console.error('Failed to fetch code context:', error);
      setCodeContext('// Failed to load code context');
    } finally {
      setLoadingContext(false);
    }
  };

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
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 'normal' }}>{finding?.file_path}:{finding?.line_start}</Text>
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
                      {loadingContext ? (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                          <Spin />
                        </div>
                      ) : (
                        <div style={{ height: '100%', borderRadius: 8, border: '1px solid #d1d5db', overflow: 'hidden' }}>
                          <CodeViewer
                            code={codeContext || '// Select a path step to view code context'}
                            language="java"
                            fileName={selectedStep ? `${selectedStep.file}:${selectedStep.line}` : undefined}
                            highlightLines={selectedStep ? [selectedStep.line || 0] : []}
                            startLine={selectedStep ? Math.max(1, (selectedStep.line || 1) - 5) : 1}
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
                  path={selectedPath}
                  selectedStepId={selectedStep?.step_id}
                  onStepClick={(step) => handleStepClick(step, finding.id)}
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
