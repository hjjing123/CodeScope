import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import {
  bindRuleSetRules,
  createRuleSet,
  getRuleSet,
  getRuleSets,
  getRules,
  updateRuleSet,
} from '../../services/rules';
import type { Rule, RuleSet, RuleSetDetail } from '../../types/rule';

const { Option } = Select;
const { Text } = Typography;

interface RuleSetListProps {
  canManageRuleSets?: boolean;
}

const RuleSetList: React.FC<RuleSetListProps> = ({ canManageRuleSets = true }) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<RuleSet[]>([]);
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    pageSize: 10,
    showSizeChanger: true,
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [editingRuleSet, setEditingRuleSet] = useState<RuleSet | null>(null);
  const [form] = Form.useForm();

  const [rules, setRules] = useState<Rule[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailRuleSet, setDetailRuleSet] = useState<RuleSet | null>(null);
  const [detailItems, setDetailItems] = useState<RuleSetDetail['items']>([]);

  const ruleNameMap = useMemo(
    () => new Map(rules.map((rule) => [rule.rule_key, rule.name])),
    [rules]
  );

  const fetchData = async (page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const res = await getRuleSets({ page, page_size: pageSize });
      setData(res.items);
      setPagination((prev) => ({ ...prev, current: page, pageSize, total: res.total }));
    } catch (error) {
      console.error(error);
      message.error('获取规则集列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(pagination.current, pagination.pageSize);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchRules = async () => {
    setLoadingRules(true);
    try {
      const pageSize = 200;
      let page = 1;
      let total = 0;
      const allRules: Rule[] = [];

      do {
        const res = await getRules({ page, page_size: pageSize });
        allRules.push(...res.items);
        total = res.total;
        page += 1;
        if (res.items.length === 0) {
          break;
        }
      } while (allRules.length < total);

      setRules(allRules);
    } catch (error) {
      console.error(error);
      message.error('获取规则列表失败');
    } finally {
      setLoadingRules(false);
    }
  };

  useEffect(() => {
    fetchRules();
  }, []);

  const handleTableChange = (newPagination: TablePaginationConfig) => {
    fetchData(newPagination.current, newPagination.pageSize);
  };

  const closeDetailModal = () => {
    setDetailOpen(false);
    setDetailLoading(false);
    setDetailRuleSet(null);
    setDetailItems([]);
  };

  const handleView = async (record: RuleSet) => {
    setDetailRuleSet(record);
    setDetailItems([]);
    setDetailOpen(true);
    setDetailLoading(true);

    try {
      const detail = await getRuleSet(record.id);
      setDetailRuleSet({
        ...record,
        name: detail.name,
        key: detail.key,
        description: detail.description,
        enabled: detail.enabled,
        created_at: detail.created_at,
        updated_at: detail.updated_at,
        rule_count: detail.items.length,
      });
      setDetailItems(detail.items);
    } catch (error) {
      console.error(error);
      message.error('获取规则集详情失败');
      closeDetailModal();
    } finally {
      setDetailLoading(false);
    }
  };

  const handleEdit = async (record: RuleSet) => {
    setEditingRuleSet(record);
    setModalOpen(true);
    form.resetFields();

    form.setFieldsValue({
      name: record.name,
      key: record.key,
      description: record.description,
      rules: [],
    });

    try {
      const detail = await getRuleSet(record.id);
      form.setFieldsValue({
        rules: detail.items.map((item) => item.rule_key),
      });
    } catch (error) {
      console.error(error);
      message.error('获取规则集详情失败');
    }
  };

  const handleCreate = () => {
    setEditingRuleSet(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);

      let ruleSetId = '';

      if (editingRuleSet) {
        await updateRuleSet(editingRuleSet.id, {
          name: values.name,
          description: values.description,
        });
        ruleSetId = editingRuleSet.id;
        message.success('更新规则集信息成功');
      } else {
        const newRuleSet = await createRuleSet({
          key: values.key,
          name: values.name,
          description: values.description,
          enabled: true,
        });
        ruleSetId = newRuleSet.id;
        message.success('创建规则集成功');
      }

      if (ruleSetId) {
        await bindRuleSetRules(ruleSetId, values.rules || []);
      }

      setModalOpen(false);
      fetchData(pagination.current, pagination.pageSize);
    } catch (error) {
      console.error(error);
      message.error('操作失败');
    } finally {
      setConfirmLoading(false);
    }
  };

  const columns: ColumnsType<RuleSet> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '标识 (Key)',
      dataIndex: 'key',
      key: 'key',
      render: (text: string) => (
        <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{text}</Text>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '规则数量',
      dataIndex: 'rule_count',
      key: 'rule_count',
      align: 'center',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="查看">
            <Button
              type="text"
              icon={<EyeOutlined />}
              aria-label={`查看规则集 ${record.name}`}
              onClick={() => handleView(record)}
            />
          </Tooltip>
          {canManageRuleSets ? (
            <Tooltip title="编辑">
              <Button
                type="text"
                icon={<EditOutlined />}
                aria-label={`编辑规则集 ${record.name}`}
                onClick={() => handleEdit(record)}
              />
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {canManageRuleSets ? (
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建规则集
          </Button>
        </div>
      ) : null}

      <Card bodyStyle={{ padding: 0 }} bordered={false}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          pagination={{
            ...pagination,
            showTotal: (total) => `共 ${total} 条`,
          }}
          loading={loading}
          onChange={handleTableChange}
          size="middle"
        />
      </Card>

      <Modal
        title={editingRuleSet ? '编辑规则集' : '新建规则集'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => setModalOpen(false)}
        width={700}
        confirmLoading={confirmLoading}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="请输入规则集名称" />
          </Form.Item>

          <Form.Item
            name="key"
            label="标识 (Key)"
            rules={[
              { required: true, message: '请输入标识' },
              {
                pattern: /^[a-zA-Z0-9_-]+$/,
                message: '仅支持字母、数字、下划线和连字符',
              },
            ]}
            extra={editingRuleSet ? '标识不可修改' : '唯一标识，创建后不可修改'}
          >
            <Input placeholder="例如: owasp-top-10" disabled={!!editingRuleSet} />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="请输入规则集描述" />
          </Form.Item>

          <Form.Item
            name="rules"
            label="包含规则"
            rules={[{ required: true, message: '请至少选择一个规则' }]}
          >
            <Select
              mode="multiple"
              placeholder="请选择规则"
              loading={loadingRules}
              style={{ width: '100%' }}
              optionFilterProp="label"
            >
              {rules.map((rule) => (
                <Option
                  key={rule.rule_key}
                  value={rule.rule_key}
                  label={`${rule.name} (${rule.rule_key})`}
                >
                  {rule.name}{' '}
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    ({rule.rule_key})
                  </Text>
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={detailRuleSet ? `查看规则集：${detailRuleSet.name}` : '查看规则集'}
        open={detailOpen}
        onCancel={closeDetailModal}
        footer={[
          <Button key="close" aria-label="关闭" onClick={closeDetailModal}>
            关闭
          </Button>,
        ]}
        width={720}
        destroyOnClose
      >
        {detailLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
            <Spin />
          </div>
        ) : detailRuleSet ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="名称">{detailRuleSet.name}</Descriptions.Item>
              <Descriptions.Item label="标识 (Key)">
                <Text code>{detailRuleSet.key}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="规则数量">
                {detailItems.length}
              </Descriptions.Item>
              <Descriptions.Item label="描述">
                {detailRuleSet.description?.trim() || '暂无描述'}
              </Descriptions.Item>
            </Descriptions>

            <div>
              <Text strong>包含规则</Text>
              {detailItems.length > 0 ? (
                <div
                  style={{
                    marginTop: 12,
                    border: '1px solid #f0f0f0',
                    borderRadius: 8,
                    overflow: 'hidden',
                  }}
                >
                  {detailItems.map((item, index) => {
                    const ruleName = ruleNameMap.get(item.rule_key);
                    const isLast = index === detailItems.length - 1;
                    return (
                      <div
                        key={item.id}
                        style={{
                          padding: 12,
                          borderBottom: isLast ? 'none' : '1px solid #f0f0f0',
                        }}
                      >
                        <Space direction="vertical" size={2} style={{ width: '100%' }}>
                          <Text strong>{ruleName ?? item.rule_key}</Text>
                          <Text type="secondary" code>
                            {item.rule_key}
                          </Text>
                        </Space>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ marginTop: 12 }}>
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无规则" />
                </div>
              )}
            </div>
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无规则集详情" />
        )}
      </Modal>
    </div>
  );
};

export default RuleSetList;
