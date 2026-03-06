import React, { useState, useEffect } from 'react';
import { Table, Button, Space, Modal, Form, Input, message, Select, Tooltip, Typography, Card } from 'antd';
import { PlusOutlined, EditOutlined } from '@ant-design/icons';
import type { TablePaginationConfig } from 'antd/es/table';
import { getRuleSets, createRuleSet, updateRuleSet, bindRuleSetRules, getRules, getRuleSet } from '../../services/rules';
import type { RuleSet, Rule } from '../../types/rule';

const { Option } = Select;
const { Text } = Typography;

const RuleSetList: React.FC = () => {
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

  // Fetch Rule Sets
  const fetchData = async (page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const res = await getRuleSets({ page, page_size: pageSize });
      setData(res.items);
      setPagination(prev => ({ ...prev, current: page, pageSize, total: res.total }));
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

  // Fetch all rules for selection
  const fetchRules = async () => {
    setLoadingRules(true);
    try {
      // Assuming fetching enough rules for now. 
      // In production, might need search functionality for Select if rules > 1000
      const res = await getRules({ page: 1, page_size: 1000 });
      setRules(res.items);
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

  const handleEdit = async (record: RuleSet) => {
    setEditingRuleSet(record);
    setModalOpen(true);
    form.resetFields();
    
    // Set initial values from record
    form.setFieldsValue({
      name: record.name,
      key: record.key,
      description: record.description,
      rules: [], // Clear rules initially
    });

    // Fetch detailed info including rules
    try {
      const detail = await getRuleSet(record.id);
      const ruleKeys = detail.items.map(item => item.rule_key);
      form.setFieldsValue({
        rules: ruleKeys,
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
        // Update
        await updateRuleSet(editingRuleSet.id, {
          name: values.name,
          description: values.description,
        });
        ruleSetId = editingRuleSet.id;
        message.success('更新规则集信息成功');
      } else {
        // Create
        const newRuleSet = await createRuleSet({
          key: values.key,
          name: values.name,
          description: values.description,
          enabled: true,
        });
        ruleSetId = newRuleSet.id;
        message.success('创建规则集成功');
      }
      
      // Bind rules for both create and update
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

  const columns: any = [
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
      render: (text: string) => <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{text}</Text>,
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
      render: (_: any, record: RuleSet) => (
        <Space size="middle">
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新建规则集
        </Button>
      </div>
      
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
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="请输入规则集名称" />
          </Form.Item>
          
          <Form.Item
            name="key"
            label="标识 (Key)"
            rules={[
              { required: true, message: '请输入标识' },
              { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅支持字母、数字、下划线和连字符' }
            ]}
            extra={editingRuleSet ? "标识不可修改" : "唯一标识，创建后不可修改"}
          >
            <Input placeholder="例如: owasp-top-10" disabled={!!editingRuleSet} />
          </Form.Item>
          
          <Form.Item
            name="description"
            label="描述"
          >
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
              {rules.map(rule => (
                <Option key={rule.rule_key} value={rule.rule_key} label={`${rule.name} (${rule.rule_key})`}>
                  {rule.name} <Text type="secondary" style={{ fontSize: 12 }}>({rule.rule_key})</Text>
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RuleSetList;
