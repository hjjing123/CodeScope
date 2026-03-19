import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  List,
  Modal,
  Space,
  Spin,
  Tag,
  Typography,
  Timeline,
  message,
} from 'antd';
import { LinkOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import AIProviderSelectFields from '../AI/AIProviderSelectFields';
import {
  createAssessmentSeedChatSession,
  createChatSession,
  getLatestFindingAIAssessment,
  getLatestFindingAIAssessmentContext,
  getMyAIOptions,
  listFindingChatSessions,
  retryFindingAI,
} from '../../services/ai';
import type {
  AIChatSessionPayload,
  AIProviderOptionsPayload,
  AIProviderSelectionRequest,
  FindingAIAssessmentContextPayload,
  FindingAIAssessmentPayload,
} from '../../types/ai';
import type { Finding } from '../../types/finding';

const { Paragraph, Text, Title } = Typography;

const toRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

interface FindingAIReviewPanelProps {
  finding: Finding;
}

const FindingAIReviewPanel: React.FC<FindingAIReviewPanelProps> = ({ finding }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<FindingAIAssessmentPayload | null>(null);
  const [assessmentContext, setAssessmentContext] = useState<FindingAIAssessmentContextPayload | null>(null);
  const [sessions, setSessions] = useState<AIChatSessionPayload[]>([]);
  const [options, setOptions] = useState<AIProviderOptionsPayload | null>(null);
  const [selection, setSelection] = useState<AIProviderSelectionRequest>({});
  const [actionModal, setActionModal] = useState<'retry' | 'chat' | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const verdict = useMemo(() => {
    const raw = String(assessment?.summary_json?.verdict || '').toUpperCase();
    return raw || 'PENDING';
  }, [assessment?.summary_json]);

  const confidence = String(assessment?.summary_json?.confidence || '').toLowerCase();
  const summary = String(assessment?.summary_json?.summary || '').trim();
  const riskReason = String(assessment?.summary_json?.risk_reason || '').trim();
  const falsePositiveSignals = Array.isArray(assessment?.summary_json?.false_positive_signals)
    ? (assessment?.summary_json?.false_positive_signals as string[])
    : [];
  const fixSuggestions = Array.isArray(assessment?.summary_json?.fix_suggestions)
    ? (assessment?.summary_json?.fix_suggestions as string[])
    : [];
  const promptMeta = toRecord(assessmentContext?.summary_json?.prompt_meta);
  const contextSnapshot = toRecord(assessmentContext?.context_snapshot);
  const analysisFocus = toRecord(contextSnapshot.analysis_focus);
  const dataFlowChain = Array.isArray(analysisFocus.data_flow_chain)
    ? (analysisFocus.data_flow_chain as Array<Record<string, unknown>>)
    : [];
  const requestMessages = Array.isArray(assessmentContext?.request_messages)
    ? (assessmentContext?.request_messages as Array<Record<string, unknown>>)
    : [];

  const refresh = async () => {
    setLoading(true);
    try {
      const [latest, chatSessions, providerOptions] = await Promise.all([
        getLatestFindingAIAssessment(finding.id),
        listFindingChatSessions(finding.id),
        getMyAIOptions(),
      ]);
      const latestContext = latest
        ? await getLatestFindingAIAssessmentContext(finding.id).catch(() => null)
        : null;
      setAssessment(latest);
      setAssessmentContext(latestContext);
      setSessions(chatSessions.items);
      setOptions(providerOptions);
      setSelection({
        ai_source: providerOptions.default_selection.ai_source as AIProviderSelectionRequest['ai_source'],
        ai_provider_id: providerOptions.default_selection.ai_provider_id as string | undefined,
        ai_model: providerOptions.default_selection.ai_model as string | undefined,
      });
    } catch (error) {
      console.error('Failed to load finding AI review', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [finding.id]);

  const openChatSession = async () => {
    setSubmitting(true);
    try {
      if (assessment?.id && assessment.status === 'SUCCEEDED') {
        const seeded = await createAssessmentSeedChatSession(finding.id);
        message.success(seeded.idempotent_replay ? '已打开承接会话' : '已创建承接会话');
        setActionModal(null);
        navigate(`/ai-center?tab=workspace&finding_id=${finding.id}&session_id=${seeded.session_id}`);
        return;
      }
      const session = await createChatSession(finding.id, {
        ...selection,
        title: `${finding.vuln_display_name || finding.vuln_type || finding.rule_key} · AI 会话`,
      });
      message.success('已创建聊天会话');
      setActionModal(null);
      navigate(`/ai-center?tab=workspace&finding_id=${finding.id}&session_id=${session.id}`);
    } catch (error) {
      console.error('Failed to create finding chat session', error);
    } finally {
      setSubmitting(false);
    }
  };

  const retryAssessment = async () => {
    setSubmitting(true);
    try {
      const result = await retryFindingAI(finding.id, selection);
      message.success(`已提交重跑任务 ${result.job_id.slice(0, 8)}`);
      setActionModal(null);
      await refresh();
    } catch (error) {
      console.error('Failed to retry finding AI', error);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            AI 研判与上下文对话
          </Title>
          <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>
            查看扫描后异步生成的 AI 结论，并围绕当前漏洞继续追问。
          </Paragraph>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<RobotOutlined />} onClick={() => setActionModal('chat')}>
            开始聊天
          </Button>
          <Button onClick={() => setActionModal('retry')}>重跑研判</Button>
        </Space>
      </div>

      {loading ? <Spin /> : null}

      {assessment ? (
        <Card style={{ borderRadius: 18 }}>
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Space wrap>
              <Tag color={verdict === 'TP' ? 'red' : verdict === 'FP' ? 'green' : 'gold'}>
                {verdict}
              </Tag>
              <Tag>{confidence || 'unknown confidence'}</Tag>
              <Tag>{assessment.provider_label}</Tag>
              <Tag>{assessment.model_name}</Tag>
            </Space>

            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="状态">{assessment.status}</Descriptions.Item>
              <Descriptions.Item label="生成时间">
                {new Date(assessment.updated_at).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="摘要" span={2}>
                {summary || '暂无摘要'}
              </Descriptions.Item>
              <Descriptions.Item label="风险依据" span={2}>
                {riskReason || '暂无风险依据'}
              </Descriptions.Item>
            </Descriptions>

            {falsePositiveSignals.length > 0 ? (
              <div>
                <Text strong>误报线索</Text>
                <ul style={{ margin: '8px 0 0 18px' }}>
                  {falsePositiveSignals.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {fixSuggestions.length > 0 ? (
              <div>
                <Text strong>修复建议</Text>
                <ul style={{ margin: '8px 0 0 18px' }}>
                  {fixSuggestions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {assessment.error_code ? (
              <Alert type="error" showIcon message={assessment.error_code} description={assessment.error_message} />
            ) : null}

            {assessmentContext ? (
              <Card size="small" title="研判输入与链路快照" bordered={false} style={{ background: '#fafafa' }}>
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Space wrap>
                    {promptMeta.profile ? <Tag color="purple">模板: {String(promptMeta.profile)}</Tag> : null}
                    {promptMeta.input_tokens_estimate ? (
                      <Tag color="blue">
                        输入预算: {String(promptMeta.input_tokens_estimate)}/{String(promptMeta.max_input_tokens || '-')}
                      </Tag>
                    ) : null}
                    {promptMeta.rule_hint_applied ? <Tag color="gold">规则专项增强</Tag> : null}
                  </Space>

                  {analysisFocus.key_path_summary ? (
                    <div>
                      <Text strong>关键路径摘要</Text>
                      <Paragraph style={{ marginBottom: 0, marginTop: 6 }}>
                        {String(analysisFocus.key_path_summary)}
                      </Paragraph>
                    </div>
                  ) : null}

                  {dataFlowChain.length > 0 ? (
                    <div>
                      <Text strong>数据传播链路</Text>
                      <Timeline
                        style={{ marginTop: 8 }}
                        items={dataFlowChain.map((item, index) => ({
                          children: (
                            <div>
                              <Text strong>{String(item.display_name || `步骤 ${index + 1}`)}</Text>
                              <br />
                              <Text type="secondary">{String(item.location || '-')}</Text>
                              {item.edge_to_next ? (
                                <div style={{ marginTop: 4 }}>
                                  <Tag>{String(item.edge_to_next)}</Tag>
                                </div>
                              ) : null}
                            </div>
                          ),
                        }))}
                      />
                    </div>
                  ) : null}

                  {requestMessages.length > 0 ? (
                    <div>
                      <Text strong>实际发送内容</Text>
                      <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
                        {requestMessages.map((item, index) => (
                          <Card
                            key={`${item.role || 'role'}-${index}`}
                            size="small"
                            title={String(item.role || 'user').toUpperCase()}
                          >
                            <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }} copyable>
                              {String(item.content || '')}
                            </Paragraph>
                          </Card>
                        ))}
                      </Space>
                    </div>
                  ) : null}

                  {assessmentContext.response_text ? (
                    <div>
                      <Text strong>模型原始返回</Text>
                      <Paragraph style={{ marginBottom: 0, marginTop: 6, whiteSpace: 'pre-wrap' }} copyable>
                        {assessmentContext.response_text}
                      </Paragraph>
                    </div>
                  ) : null}
                </Space>
              </Card>
            ) : null}
          </Space>
        </Card>
      ) : (
        <Alert
          type="info"
          showIcon
          message="这条漏洞还没有 AI 研判结果"
          description="如果扫描时没有开启 AI，或者异步任务还未执行完成，可以在这里发起重跑。"
        />
      )}

      <Card style={{ borderRadius: 18 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Text strong>关联聊天会话</Text>
          {sessions.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前漏洞还没有聊天会话" />
          ) : (
            <List
              dataSource={sessions}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key={item.id}
                      type="link"
                      icon={<LinkOutlined />}
                      onClick={() =>
                        navigate(
                          `/ai-center?tab=workspace&finding_id=${finding.id}&session_id=${item.id}`
                        )
                      }
                    >
                      打开
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.title || `会话 ${item.id.slice(0, 8)}`}
                    description={`${item.provider_label} · ${item.model_name} · ${new Date(item.updated_at).toLocaleString()}`}
                  />
                </List.Item>
              )}
            />
          )}
        </Space>
      </Card>

      <Modal
        title={actionModal === 'retry' ? '重跑 AI 研判' : '新建 AI 聊天会话'}
        open={actionModal !== null}
        onCancel={() => setActionModal(null)}
        onOk={() => {
          if (actionModal === 'retry') {
            void retryAssessment();
            return;
          }
          void openChatSession();
        }}
        confirmLoading={submitting}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="会自动固化当前所选 Provider 快照"
            description="这样后续的任务重试和会话回放不会受你之后修改模型、地址或密钥影响。"
          />
          <AIProviderSelectFields options={options} value={selection} onChange={setSelection} />
        </Space>
      </Modal>
    </div>
  );
};

export default FindingAIReviewPanel;
