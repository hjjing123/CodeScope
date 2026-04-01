import React, { useEffect, useMemo, useState } from 'react';
import { Checkbox, Modal, Space, Typography } from 'antd';
import type { Job, ScanJobDeleteTarget } from '../../types/scan';

const { Paragraph, Text } = Typography;

const DELETE_OPTIONS: Array<{
  value: ScanJobDeleteTarget;
  label: string;
  description: string;
}> = [
  {
    value: 'job_record',
    label: '任务记录',
    description: '硬删除任务记录和步骤记录；若选择该项，将自动删除 Findings。',
  },
  {
    value: 'logs',
    label: '运行日志',
    description: '删除阶段日志和任务日志索引。',
  },
  {
    value: 'artifacts',
    label: '扫描产物/报告',
    description: '删除本次扫描归档和 external 结果目录，不影响代码快照归档。',
  },
  {
    value: 'workspace',
    label: '中间工作区',
    description: '删除任务运行过程中产生的临时工作区。',
  },
  {
    value: 'findings',
    label: '扫描结果 Findings',
    description: '删除本次扫描写入的漏洞结果及其标签。',
  },
];

interface DeleteScanJobModalProps {
  open: boolean;
  job: Job | null;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: (targets: ScanJobDeleteTarget[]) => void;
}

const DeleteScanJobModal: React.FC<DeleteScanJobModalProps> = ({
  open,
  job,
  submitting,
  onCancel,
  onConfirm,
}) => {
  const [selectedTargets, setSelectedTargets] = useState<ScanJobDeleteTarget[]>([]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSelectedTargets([]);
  }, [open, job?.id]);

  const effectiveTargets = useMemo(() => {
    const next = new Set<ScanJobDeleteTarget>(selectedTargets);
    if (next.has('job_record')) {
      next.add('findings');
    }
    return Array.from(next);
  }, [selectedTargets]);

  const isForcedFinding = selectedTargets.includes('job_record');

  const handleToggle = (target: ScanJobDeleteTarget, checked: boolean) => {
    setSelectedTargets((prev) => {
      if (checked) {
        return prev.includes(target) ? prev : [...prev, target];
      }
      return prev.filter((item) => item !== target);
    });
  };

  const handleOk = () => {
    if (effectiveTargets.length === 0) {
      return;
    }
    onConfirm(effectiveTargets);
  };

  return (
    <Modal
      title="删除扫描任务内容"
      open={open}
      destroyOnClose
      onCancel={onCancel}
      onOk={handleOk}
      okText="确认删除"
      okButtonProps={{ danger: true, disabled: effectiveTargets.length === 0 }}
      confirmLoading={submitting}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Paragraph style={{ marginBottom: 0 }}>
          {job ? (
            <>
              将删除任务 <Text code>{job.id}</Text> 关联的指定内容。此操作不可恢复。
            </>
          ) : (
            '请选择要删除的内容。'
          )}
        </Paragraph>

        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {DELETE_OPTIONS.map((option) => {
            const checked = effectiveTargets.includes(option.value);
            const disabled = option.value === 'findings' && isForcedFinding;
            return (
              <div
                key={option.value}
                style={{
                  border: '1px solid #f0f0f0',
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                <Checkbox
                  checked={checked}
                  disabled={disabled}
                  onChange={(event) => handleToggle(option.value, event.target.checked)}
                >
                  <Text strong>{option.label}</Text>
                </Checkbox>
                <div style={{ marginTop: 6, marginLeft: 24, color: '#595959' }}>
                  {option.description}
                </div>
                {disabled ? (
                  <div style={{ marginTop: 6, marginLeft: 24, color: '#fa8c16' }}>
                    因选择“任务记录”，本项已自动包含。
                  </div>
                ) : null}
              </div>
            );
          })}
        </Space>
      </Space>
    </Modal>
  );
};

export default DeleteScanJobModal;
