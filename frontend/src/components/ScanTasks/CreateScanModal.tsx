import React, { useState, useEffect } from 'react';
import { Alert, Form, Input, Modal, Select, Switch, message } from 'antd';
import { getProjects, getVersions } from '../../services/projectVersion';
import AIProviderSelectFields from '../AI/AIProviderSelectFields';
import { getMyAIOptions } from '../../services/ai';
import { getRules, getRuleSets } from '../../services/rules';
import { ScanService } from '../../services/scan';
import type { AIProviderOptionsPayload, AIProviderSelectionRequest } from '../../types/ai';
import type { ScanJobCreateRequest } from '../../types/scan';
import type { Project, Version } from '../../types/projectVersion';
import type { Rule, RuleSet } from '../../types/rule';

interface CreateScanModalProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
  initialProjectId?: string | null;
  initialVersionId?: string | null;
}

interface CreateScanFormValues {
  project_id: string;
  version_id: string;
  rule_set_keys?: string[];
  rule_keys?: string[];
  note?: string;
  ai_enabled?: boolean;
}

const CreateScanModal: React.FC<CreateScanModalProps> = ({
  open,
  onCancel,
  onSuccess,
  initialProjectId,
  initialVersionId,
}) => {
  const [form] = Form.useForm();
  const [projects, setProjects] = useState<Project[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [ruleSets, setRuleSets] = useState<RuleSet[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [loadingRuleOptions, setLoadingRuleOptions] = useState(false);
  const [loadingAIOptions, setLoadingAIOptions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [aiOptions, setAiOptions] = useState<AIProviderOptionsPayload | null>(null);
  const [aiSelection, setAiSelection] = useState<AIProviderSelectionRequest>({});
  const [aiEnabled, setAiEnabled] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }

    form.resetFields();
    form.setFieldsValue({
      project_id: initialProjectId ?? undefined,
      version_id: initialVersionId ?? undefined,
      rule_set_keys: [],
      rule_keys: [],
      note: '',
      ai_enabled: false,
    });
    setAiEnabled(false);
    setVersions([]);
    setSelectedProjectId(initialProjectId ?? null);

    void fetchProjects();
    void fetchRuleOptions();
    void fetchAIOptions();
    if (initialProjectId) {
      void fetchVersions(initialProjectId, initialVersionId ?? undefined);
    }
  }, [open, form, initialProjectId, initialVersionId]);

  const fetchProjects = async () => {
    try {
      setLoadingProjects(true);
      const res = await getProjects({ page: 1, page_size: 100 });
      if (res && res.data && res.data.items) {
        setProjects(res.data.items);
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
      message.error('获取项目列表失败');
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchRuleOptions = async () => {
    try {
      setLoadingRuleOptions(true);
      const [ruleSetResponse, ruleResponse] = await Promise.all([
        getRuleSets({ page: 1, page_size: 100 }),
        getRules({ enabled: true, page: 1, page_size: 200 }),
      ]);
      setRuleSets(ruleSetResponse.items.filter((item) => item.enabled));
      setRules(ruleResponse.items.filter((item) => item.enabled));
    } catch (error) {
      console.error('Failed to fetch scan rule options:', error);
      message.error('获取扫描规则配置失败');
    } finally {
      setLoadingRuleOptions(false);
    }
  };

  const fetchVersions = async (projectId: string, preferredVersionId?: string) => {
    try {
      setLoadingVersions(true);
      const res = await getVersions(projectId, { page: 1, page_size: 100 });
      if (res && res.data && res.data.items) {
        const nextVersions = res.data.items;
        setVersions(nextVersions);
        if (preferredVersionId && nextVersions.some((item) => item.id === preferredVersionId)) {
          form.setFieldValue('version_id', preferredVersionId);
        }
      }
    } catch (error) {
      console.error('Failed to fetch versions:', error);
      message.error('获取版本列表失败');
    } finally {
      setLoadingVersions(false);
    }
  };

  const fetchAIOptions = async () => {
    try {
      setLoadingAIOptions(true);
      const payload = await getMyAIOptions();
      setAiOptions(payload);
      setAiSelection({
        ai_source: payload.default_selection.ai_source as AIProviderSelectionRequest['ai_source'],
        ai_provider_id: payload.default_selection.ai_provider_id as string | undefined,
        ai_model: payload.default_selection.ai_model as string | undefined,
      });
    } catch (error) {
      console.error('Failed to fetch AI options:', error);
      setAiOptions(null);
    } finally {
      setLoadingAIOptions(false);
    }
  };

  const handleProjectChange = (value: string) => {
    setSelectedProjectId(value);
    setVersions([]);
    form.setFieldsValue({ version_id: undefined });
    void fetchVersions(value);
  };

  const handleOk = async () => {
    try {
      const values = (await form.validateFields()) as CreateScanFormValues;
      setSubmitting(true);

      const payload: ScanJobCreateRequest = {
        project_id: values.project_id,
        version_id: values.version_id,
        rule_set_keys: values.rule_set_keys ?? [],
        rule_keys: values.rule_keys ?? [],
        note: values.note?.trim() || undefined,
        ai_enabled: Boolean(values.ai_enabled),
        ...(values.ai_enabled ? aiSelection : {}),
      };

      await ScanService.createScanJob(values.project_id, payload);

      message.success('扫描任务已创建');
      onSuccess();
    } catch (error) {
      console.error('Failed to create scan job:', error);
      message.error('创建扫描任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="新建扫描任务"
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      confirmLoading={submitting}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        name="create_scan_form"
        initialValues={{
          rule_set_keys: [],
          rule_keys: [],
          note: '',
          ai_enabled: false,
        }}
      >
        <Form.Item
          name="project_id"
          label="选择项目"
          rules={[{ required: true, message: '请选择项目' }]}
        >
          <Select
            placeholder="请选择项目"
            loading={loadingProjects}
            onChange={handleProjectChange}
            showSearch
            optionFilterProp="children"
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
            options={projects.map(p => ({ label: p.name, value: p.id }))}
          />
        </Form.Item>

        <Form.Item
          name="version_id"
          label="选择版本"
          rules={[{ required: true, message: '请选择版本' }]}
        >
          <Select
            placeholder="请选择版本"
            loading={loadingVersions}
            disabled={!selectedProjectId}
            options={versions.map(v => ({ label: v.name, value: v.id }))}
          />
        </Form.Item>

        <Form.Item
          name="rule_set_keys"
          label="规则集"
          extra="可选；与附加规则都不选择时，默认扫描全部已启用规则。"
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            maxTagCount="responsive"
            loading={loadingRuleOptions}
            optionFilterProp="label"
            options={ruleSets.map((item) => ({
              label: `${item.name} (${item.key})`,
              value: item.key,
            }))}
          />
        </Form.Item>

        <Form.Item
          name="rule_keys"
          label="附加规则"
          extra="可选；会与规则集展开结果合并去重。"
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            maxTagCount="responsive"
            loading={loadingRuleOptions}
            optionFilterProp="label"
            options={rules.map((item) => ({
              label: `${item.name} (${item.rule_key})`,
              value: item.rule_key,
            }))}
          />
        </Form.Item>

        <Form.Item name="note" label="备注">
          <Input.TextArea rows={3} maxLength={1024} showCount />
        </Form.Item>

        <Form.Item name="ai_enabled" label="扫描后 AI 异步研判" valuePropName="checked">
          <Switch
            checked={aiEnabled}
            onChange={(checked) => {
              setAiEnabled(checked);
              form.setFieldValue('ai_enabled', checked);
            }}
          />
        </Form.Item>

        {aiEnabled ? (
          <div
            style={{
              padding: 16,
              borderRadius: 16,
              border: '1px solid rgba(2,132,199,0.12)',
              background: 'linear-gradient(180deg, rgba(240,249,255,0.75), rgba(255,255,255,0.98))',
            }}
          >
            <Alert
              type="info"
              showIcon
              message="扫描完成后会异步创建 AI 研判任务"
              description="AI 不会阻塞扫描结果入库；如果 AI 不可用，扫描任务仍会正常完成。"
              style={{ marginBottom: 16 }}
            />
            {loadingAIOptions ? (
              <Alert type="info" showIcon message="正在加载 AI Provider 选项" />
            ) : (
              <AIProviderSelectFields options={aiOptions} value={aiSelection} onChange={setAiSelection} />
            )}
          </div>
        ) : null}
      </Form>
    </Modal>
  );
};

export default CreateScanModal;
