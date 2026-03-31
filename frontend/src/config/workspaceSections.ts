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
  RobotOutlined,
  SettingOutlined,
  TeamOutlined,
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
    route: 'code-management',
    path: '/code-management',
    label: '代码管理',
    tagline: '管理项目接入、代码快照与扫描上下文。',
    badge: 'Source Scope',
    intro:
      '代码管理是所有扫描任务的上游输入。该模块优先稳定项目列表、代码快照与导入能力，后续扩展关联分析。',
    icon: FolderOpenOutlined,
    highlights: ['项目生命周期状态管理', '代码快照与提交信息可追踪', '导入来源和凭据策略隔离'],
    blocks: [
      {
        title: '项目列表框架',
        description: '预置搜索、标签和状态过滤位置，后续可平滑接入分页和排序。',
        status: 'skeleton',
      },
      {
        title: '代码快照时间轴容器',
        description: '用于展示代码快照创建、扫描触发和结果产出时间节点。',
        status: 'planned',
      },
      {
        title: '导入任务侧边栏',
        description: '预留 Git/Zip 导入配置面板与安全校验提示区域。',
        status: 'next',
      },
    ],
    nextAction: '优先完成项目列表和代码快照时间轴的数据契约，再接入导入流程。',
  },
  {
    key: 'rules',
    route: 'rules',
    path: '/rules',
    label: '规则中心',
    tagline: '维护规则库、版本与启停策略。',
    badge: 'Rule Forge',
    intro:
      '规则中心已接入后端规则管理能力，支持规则列表、规则详情编辑、版本发布/回滚、规则集编排与规则自测。',
    icon: ControlOutlined,
    highlights: ['规则查看与启停', '规则集创建与绑定', '自定义规则草稿与自测'],
    blocks: [
      {
        title: '规则清单与统计',
        description: '已支持规则分页、启停、统计卡片与详情跳转。',
        status: 'next',
      },
      {
        title: '规则详情与发布',
        description: '已支持草稿保存、发布、回滚、状态切换与自测入口。',
        status: 'next',
      },
      {
        title: '规则集编排',
        description: '已支持规则集创建、编辑以及绑定规则列表。',
        status: 'planned',
      },
    ],
    nextAction: '下一步可补充规则变更审计可视化与规则集启停操作。',
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
    key: 'ai-center',
    route: 'ai-center',
    path: '/ai-center',
    label: 'AI 中心',
    tagline: '智能研判助手与模型管理。',
    badge: 'AI Nexus',
    intro:
      'AI 中心提供基于大模型的交互式研判能力，帮助分析复杂漏洞。同时提供本地模型（Ollama）的统一配置管理。',
    icon: RobotOutlined,
    highlights: ['上下文感知对话', '本地模型一键部署', '历史会话管理'],
    blocks: [
      {
        title: '交互式对话框',
        description: '类 ChatGPT 界面，支持针对漏洞上下文的多轮对话。',
        status: 'next',
      },
      {
        title: '模型配置面板',
        description: '管理员可在此管理 Ollama 服务地址与模型库。',
        status: 'next',
      },
      {
        title: '会话历史',
        description: '本地存储最近的研判会话，方便快速回溯。',
        status: 'next',
      },
    ],
    nextAction: '完善漏洞上下文注入逻辑，提升回答准确性。',
  },
  {
    key: 'reports',
    route: 'reports',
    path: '/reports',
    label: '报告中心',
    tagline: '查看报告生成记录与导出文件。',
    badge: 'Report Studio',
    intro:
      '报告中心当前聚焦已生成报告的历史记录、状态追踪与文件导出，便于统一回看输出结果。',
    icon: FileTextOutlined,
    highlights: ['报告生成历史', '导出状态追踪', '文件下载与回看'],
    blocks: [
      {
        title: '导出任务历史',
        description: '用于显示报告状态、创建时间和下载入口。',
        status: 'next',
      },
    ],
    nextAction: '继续补齐报告筛选、状态联动和导出体验细节。',
  },
  {
    key: 'log-center',
    route: 'log-center',
    path: '/log-center',
    label: '日志中心',
    tagline: '统一检索操作与任务日志，快速复盘问题链路。',
    badge: 'Trace Hub',
    intro:
      '日志中心用于调试和审计复盘。通过 request_id、task_id 和 project_id 组合检索，可以在同一页面快速还原系统行为与任务执行过程。',
    icon: FileSearchOutlined,
    highlights: ['操作日志快速检索与筛选', '任务阶段日志按类型聚合与下载', '关联追踪支持 request_id 全链路回放'],
    blocks: [
      {
        title: '系统日志检索区',
        description: '默认展示操作日志，支持按时间、动作、结果快速筛选。',
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
  {
    key: 'users',
    route: 'users',
    path: '/users',
    label: '用户管理',
    tagline: '管理系统用户与角色权限。',
    badge: 'User Admin',
    intro: '维护用户列表、重置密码及分配角色，仅管理员可见。',
    icon: TeamOutlined,
    highlights: ['用户列表与搜索', '角色权限分配', '状态启停管理'],
    blocks: [],
    nextAction: '对接用户管理 API。',
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
