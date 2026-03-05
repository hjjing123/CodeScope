import { createElement } from 'react';
import type { ComponentType } from 'react';
import type { MenuProps } from 'antd';
import type { AntdIconProps } from '@ant-design/icons/lib/components/AntdIcon';
import {
  BugOutlined,
  ControlOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  SettingOutlined,
} from '@ant-design/icons';

type IconComponent = ComponentType<AntdIconProps>;

export type SectionBlockStatus = 'skeleton' | 'planned' | 'next';

export interface WorkspaceSectionBlock {
  title: string;
  description: string;
  status: SectionBlockStatus;
}

export interface WorkspaceSection {
  key: string;
  route: string;
  path: string;
  label: string;
  tagline: string;
  badge: string;
  intro: string;
  icon: IconComponent;
  highlights: string[];
  blocks: WorkspaceSectionBlock[];
  nextAction: string;
}

export const workspaceSections: WorkspaceSection[] = [
  {
    key: 'dashboard',
    route: 'dashboard',
    path: '/dashboard',
    label: '安全概览',
    tagline: '统一查看风险热度、任务进度与审计活动。',
    badge: 'Control Hub',
    intro:
      '作为登录后的默认落点，概览页会持续聚合关键指标、趋势变化与高频动作入口，方便团队快速进入当天重点工作。',
    icon: DashboardOutlined,
    highlights: ['跨项目风险态势看板', '待处理告警与任务优先级分层', '审计流水与关键事件追踪'],
    blocks: [
      {
        title: '风险态势总览卡',
        description: '预留风险等级分布、趋势图与异常波动提醒，作为全局决策入口。',
        status: 'skeleton',
      },
      {
        title: '今日任务聚焦区',
        description: '展示进行中/阻塞任务与责任人，支持后续接入任务详情抽屉。',
        status: 'next',
      },
      {
        title: '近期审计活动',
        description: '对接操作日志后按时间线展示关键动作，满足追溯和复盘需求。',
        status: 'planned',
      },
    ],
    nextAction: '先接入概览统计接口，再补齐趋势图和任务筛选器。',
  },
  {
    key: 'projects',
    route: 'projects',
    path: '/projects',
    label: '项目与版本',
    tagline: '管理项目接入、版本快照与扫描上下文。',
    badge: 'Source Scope',
    intro:
      '项目与版本是所有扫描任务的上游输入。该模块优先稳定列表、筛选和版本详情，后续扩展导入与关联分析。',
    icon: FolderOpenOutlined,
    highlights: ['项目生命周期状态管理', '版本快照与提交信息可追踪', '导入来源和凭据策略隔离'],
    blocks: [
      {
        title: '项目列表框架',
        description: '预置搜索、标签和状态过滤位置，后续可平滑接入分页和排序。',
        status: 'skeleton',
      },
      {
        title: '版本时间轴容器',
        description: '用于展示版本创建、扫描触发和结果产出时间节点。',
        status: 'planned',
      },
      {
        title: '导入任务侧边栏',
        description: '预留 Git/Zip 导入配置面板与安全校验提示区域。',
        status: 'next',
      },
    ],
    nextAction: '优先完成项目列表和版本时间轴的数据契约，再接入导入流程。',
  },
  {
    key: 'rules',
    route: 'rules',
    path: '/rules',
    label: '规则中心',
    tagline: '维护规则库、版本与启停策略。',
    badge: 'Rule Forge',
    intro:
      '规则中心承载规则生命周期与执行策略。页面骨架已经按“规则清单 + 详情编辑 + 发布记录”组织，方便逐步填充。',
    icon: ControlOutlined,
    highlights: ['规则分组与标签体系', '规则版本发布记录', '生效范围与风险级别统一配置'],
    blocks: [
      {
        title: '规则清单区域',
        description: '预留批量启停、筛选和版本对比入口。',
        status: 'skeleton',
      },
      {
        title: '规则详情编辑区',
        description: '承接规则元信息、触发条件和修复建议编辑。',
        status: 'next',
      },
      {
        title: '发布与回滚记录',
        description: '后续用于展示规则变更日志和回滚操作。',
        status: 'planned',
      },
    ],
    nextAction: '先实现规则列表和详情面板联动，再补齐发布历史。',
  },
  {
    key: 'scans',
    route: 'scans',
    path: '/scans',
    label: '扫描任务',
    tagline: '调度任务队列，掌控执行状态与重试。',
    badge: 'Queue Lens',
    intro:
      '扫描任务模块将承接调度链路和执行反馈。当前骨架重点是状态看板、任务列表和任务详情三块，便于后续扩展。',
    icon: DeploymentUnitOutlined,
    highlights: ['任务状态泳道视图', '执行节点和耗时统计', '重试、取消与优先级控制'],
    blocks: [
      {
        title: '状态泳道板',
        description: '预留排队、运行、失败和完成任务分区。',
        status: 'skeleton',
      },
      {
        title: '任务明细容器',
        description: '用于显示阶段日志、失败原因与修复建议。',
        status: 'next',
      },
      {
        title: '批量操作工具栏',
        description: '后续接入重试、取消和导出动作。',
        status: 'planned',
      },
    ],
    nextAction: '优先对接任务列表与状态枚举，再补充任务详情联动。',
  },
  {
    key: 'findings',
    route: 'findings',
    path: '/findings',
    label: '结果研判',
    tagline: '集中处理漏洞结果、证据链与复核动作。',
    badge: 'Triage Board',
    intro:
      '结果研判页面会成为安全与研发协同的核心区域。框架已经预留筛选、证据定位与批量处置区域。',
    icon: BugOutlined,
    highlights: ['漏洞分级与状态迁移', '证据链定位与代码片段预览', '批量标记与责任分派'],
    blocks: [
      {
        title: '结果筛选条',
        description: '预留多维过滤、查询保存和视图切换入口。',
        status: 'skeleton',
      },
      {
        title: '漏洞列表容器',
        description: '后续承接分页列表、批量操作和快速状态变更。',
        status: 'next',
      },
      {
        title: '证据详情面板',
        description: '用于展示调用链、代码上下文和修复建议。',
        status: 'planned',
      },
    ],
    nextAction: '先完成漏洞列表 + 筛选，再接入证据定位详情。',
  },
  {
    key: 'reports',
    route: 'reports',
    path: '/reports',
    label: '报告中心',
    tagline: '管理报告模板、生成流程与导出记录。',
    badge: 'Report Studio',
    intro:
      '报告中心用于组织输出物和审计结论。骨架按模板区、预览区和导出历史三段划分，支持后续逐步接入。',
    icon: FileTextOutlined,
    highlights: ['报告模板配置与复用', '在线预览与章节重排', '导出记录与追踪下载'],
    blocks: [
      {
        title: '模板列表与标签',
        description: '预留模板筛选、复制和状态管理。',
        status: 'skeleton',
      },
      {
        title: '报告预览画布',
        description: '后续接入章节拖拽和实时预览。',
        status: 'planned',
      },
      {
        title: '导出任务历史',
        description: '用于显示导出状态、下载链接和失败重试。',
        status: 'next',
      },
    ],
    nextAction: '建议先做模板列表，再接入导出任务流水。',
  },
  {
    key: 'log-center',
    route: 'log-center',
    path: '/log-center',
    label: '日志中心',
    tagline: '统一检索操作、运行与任务日志，快速复盘问题链路。',
    badge: 'Trace Hub',
    intro:
      '日志中心用于调试和审计复盘。通过 request_id、task_id 和 project_id 组合检索，可以在同一页面快速还原系统行为与任务执行过程。',
    icon: FileSearchOutlined,
    highlights: ['操作与运行日志统一检索', '任务阶段日志按类型聚合与下载', '关联追踪支持 request_id 全链路回放'],
    blocks: [
      {
        title: '系统日志检索区',
        description: '支持操作日志与运行日志切换，按时间、动作、级别快速筛选。',
        status: 'skeleton',
      },
      {
        title: '任务日志查看区',
        description: '按任务类型与任务 ID 查询阶段日志，并支持按阶段或全量下载。',
        status: 'next',
      },
      {
        title: '关联追踪区',
        description: '根据 request_id/task_id 聚合审计、运行与任务日志元数据，便于定位根因。',
        status: 'planned',
      },
    ],
    nextAction: '优先接通告警联动与保存检索视图能力，提升日常排障效率。',
  },
  {
    key: 'settings',
    route: 'settings',
    path: '/settings',
    label: '系统设置',
    tagline: '维护账号、权限、通知与运行策略。',
    badge: 'Ops Panel',
    intro:
      '系统设置承担平台治理能力。框架已划分账号权限、通知策略和运行参数三大区域，方便后续持续扩展。',
    icon: SettingOutlined,
    highlights: ['账号与角色权限管理', '通知与告警策略配置', '平台运行参数与审计开关'],
    blocks: [
      {
        title: '账号权限面板',
        description: '预留用户列表、角色分配和权限矩阵区域。',
        status: 'skeleton',
      },
      {
        title: '通知策略配置',
        description: '承接邮件/Webhook 通知频率和路由设置。',
        status: 'planned',
      },
      {
        title: '运行参数开关',
        description: '用于维护系统级开关和降级策略。',
        status: 'next',
      },
    ],
    nextAction: '建议先落地权限配置页，再逐步补齐通知与运行参数。',
  },
];

export const DEFAULT_WORKSPACE_SECTION = workspaceSections[0];

export const getWorkspaceSectionByPath = (pathname: string): WorkspaceSection => {
  const matched = workspaceSections.find(
    (section) => pathname === section.path || pathname.startsWith(`${section.path}/`)
  );

  return matched ?? DEFAULT_WORKSPACE_SECTION;
};

export const getWorkspaceSectionByKey = (key: string): WorkspaceSection => {
  return workspaceSections.find((section) => section.key === key) ?? DEFAULT_WORKSPACE_SECTION;
};

export const workspaceMenuItems: MenuProps['items'] = workspaceSections.map((section) => ({
  key: section.key,
  icon: createElement(section.icon),
  label: section.label,
}));
