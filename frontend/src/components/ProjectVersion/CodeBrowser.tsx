import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Drawer, Tree, Spin, Empty, Alert, Button, Tag, Tooltip, message } from 'antd';
import {
  FileOutlined,
  FolderOutlined,
  CodeOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import type { DataNode, TreeProps } from 'antd/es/tree';
import hljs from 'highlight.js/lib/common';
import { getVersionTree, getVersionFile } from '../../services/projectVersion';
import type { VersionTreeEntry } from '../../types/projectVersion';
import './CodeBrowser.css';

const { DirectoryTree } = Tree;

interface CodeBrowserProps {
  open: boolean;
  onClose: () => void;
  versionId: string;
  versionName: string;
}

interface SelectedFileMeta {
  truncated: boolean;
  totalLines: number;
}

const getTreePanelLimits = (containerWidth: number): { min: number; max: number } => {
  const min = containerWidth < 720 ? 170 : 220;
  const maxPreferred = containerWidth < 720 ? 320 : 560;
  const max = Math.max(min, Math.min(maxPreferred, containerWidth - 220));
  return { min, max };
};

const clampTreePanelWidth = (value: number, containerWidth: number): number => {
  const { min, max } = getTreePanelLimits(containerWidth);
  return Math.min(max, Math.max(min, Math.round(value)));
};

const getDefaultTreePanelWidth = (containerWidth: number): number => {
  const ratio = containerWidth < 720 ? 0.42 : 0.3;
  return clampTreePanelWidth(containerWidth * ratio, containerWidth);
};

const getContainerWidth = (container: HTMLDivElement | null): number => {
  const fallbackWidth = Math.floor(window.innerWidth * 0.85);
  return container?.clientWidth ?? fallbackWidth;
};

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  java: 'java',
  go: 'go',
  rs: 'rust',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  hh: 'cpp',
  cs: 'csharp',
  php: 'php',
  rb: 'ruby',
  swift: 'swift',
  kt: 'kotlin',
  kts: 'kotlin',
  sql: 'sql',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  json: 'json',
  yml: 'yaml',
  yaml: 'yaml',
  xml: 'xml',
  html: 'xml',
  svg: 'xml',
  css: 'css',
  scss: 'scss',
  less: 'less',
  md: 'markdown',
  dockerfile: 'dockerfile',
  toml: 'ini',
  ini: 'ini',
};

const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const getLanguageFromPath = (path: string | null): string | null => {
  if (!path) {
    return null;
  }

  const normalized = path.toLowerCase();
  if (normalized.endsWith('dockerfile')) {
    return 'dockerfile';
  }

  const extension = normalized.split('.').pop();
  if (!extension) {
    return null;
  }

  return LANGUAGE_BY_EXTENSION[extension] ?? null;
};

const CodeBrowser: React.FC<CodeBrowserProps> = ({ open, onClose, versionId, versionName }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const resizeCleanupRef = useRef<(() => void) | null>(null);

  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedFileMeta, setSelectedFileMeta] = useState<SelectedFileMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [treePanelWidth, setTreePanelWidth] = useState(300);

  const highlightedLines = useMemo(() => {
    if (!selectedFileContent) {
      return [];
    }

    const language = getLanguageFromPath(selectedFilePath);
    return selectedFileContent.split('\n').map((line) => {
      if (!line) {
        return '&nbsp;';
      }

      try {
        if (language && hljs.getLanguage(language)) {
          return hljs.highlight(line, { language, ignoreIllegals: true }).value;
        }
        return hljs.highlightAuto(line).value;
      } catch {
        return escapeHtml(line);
      }
    });
  }, [selectedFileContent, selectedFilePath]);

  const lineSummary = useMemo(() => {
    if (!selectedFileMeta) {
      return null;
    }

    if (selectedFileMeta.truncated) {
      return `显示 ${highlightedLines.length}/${selectedFileMeta.totalLines} 行`;
    }

    return `${selectedFileMeta.totalLines} 行`;
  }, [selectedFileMeta, highlightedLines.length]);

  useEffect(() => {
    if (open && versionId) {
      void loadTreeData('');
      setSelectedFileContent(null);
      setSelectedFilePath(null);
      setSelectedFileMeta(null);

      const containerWidth = getContainerWidth(containerRef.current);
      setTreePanelWidth((previous) =>
        clampTreePanelWidth(previous || getDefaultTreePanelWidth(containerWidth), containerWidth)
      );
    }
  }, [open, versionId]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const target = containerRef.current;
    if (!target || typeof ResizeObserver === 'undefined') {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (!width) {
        return;
      }

      setTreePanelWidth((previous) => {
        const base = previous > 0 ? previous : getDefaultTreePanelWidth(width);
        return clampTreePanelWidth(base, width);
      });
    });

    observer.observe(target);
    return () => {
      observer.disconnect();
    };
  }, [open]);

  useEffect(() => {
    return () => {
      if (resizeCleanupRef.current) {
        resizeCleanupRef.current();
      }
    };
  }, []);

  const loadTreeData = async (path: string) => {
    try {
      setLoadingTree(true);
      setError(null);
      const res = await getVersionTree(versionId, path);
      const nodes = convertToTreeNodes(res.data.items);

      if (!path) {
        setTreeData(nodes);
      } else {
        setTreeData((origin) => updateTreeData(origin, path, nodes));
      }
    } catch (loadError: unknown) {
      if (loadError instanceof Error && loadError.message) {
        setError(loadError.message);
      } else {
        setError('Failed to load file tree');
      }
    } finally {
      setLoadingTree(false);
    }
  };

  const convertToTreeNodes = (items: VersionTreeEntry[]): DataNode[] => {
    return items.map((item) => ({
      title: item.name,
      key: item.path,
      isLeaf: item.node_type === 'file',
      icon: item.node_type === 'file' ? <FileOutlined /> : <FolderOutlined />,
      children: item.node_type === 'dir' ? [] : undefined,
    }));
  };

  const updateTreeData = (list: DataNode[], key: React.Key, children: DataNode[]): DataNode[] => {
    return list.map((node) => {
      if (node.key === key) {
        return { ...node, children };
      }
      if (node.children) {
        return { ...node, children: updateTreeData(node.children, key, children) };
      }
      return node;
    });
  };

  const onLoadData: TreeProps['loadData'] = async ({ key, children }) => {
    if (children && children.length > 0) {
      return;
    }
    await loadTreeData(key as string);
  };

  const onSelect: TreeProps['onSelect'] = (selectedKeys, info) => {
    if (selectedKeys.length === 0) {
      return;
    }

    const key = selectedKeys[0] as string;
    const node = info.node;

    if (node.isLeaf) {
      setSelectedFilePath(key);
      setSelectedFileContent(null);
      setSelectedFileMeta(null);
      void loadFileContent(key);
    }
  };

  const loadFileContent = async (path: string) => {
    try {
      setLoadingFile(true);
      const res = await getVersionFile(versionId, path);
      setSelectedFileContent(res.data.content);
      setSelectedFileMeta({
        truncated: res.data.truncated,
        totalLines: res.data.total_lines,
      });
    } catch (loadError: unknown) {
      if (loadError instanceof Error && loadError.message) {
        setSelectedFileContent(`Error loading file: ${loadError.message}`);
      } else {
        setSelectedFileContent('Error loading file: unknown error');
      }
      setSelectedFileMeta(null);
    } finally {
      setLoadingFile(false);
    }
  };

  const handleCopyContent = async () => {
    if (!selectedFileContent) {
      return;
    }

    try {
      await navigator.clipboard.writeText(selectedFileContent);
      message.success('文件内容已复制');
    } catch {
      message.error('复制失败，请手动复制');
    }
  };

  const handleResizeKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (event) => {
    if (!containerRef.current) {
      return;
    }

    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return;
    }

    event.preventDefault();
    const delta = event.key === 'ArrowLeft' ? -24 : 24;
    const containerWidth = containerRef.current.clientWidth;
    setTreePanelWidth((previous) => clampTreePanelWidth(previous + delta, containerWidth));
  };

  const handleResizeStart: React.PointerEventHandler<HTMLDivElement> = (event) => {
    if (!containerRef.current) {
      return;
    }

    event.preventDefault();

    const containerWidth = containerRef.current.clientWidth;
    const startWidth = clampTreePanelWidth(treePanelWidth, containerWidth);
    const startX = event.clientX;

    const cleanup = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      resizeCleanupRef.current = null;
    };

    const onPointerMove = (moveEvent: PointerEvent) => {
      if (!containerRef.current) {
        return;
      }

      const deltaX = moveEvent.clientX - startX;
      const nextWidth = clampTreePanelWidth(startWidth + deltaX, containerRef.current.clientWidth);
      setTreePanelWidth(nextWidth);
    };

    const onPointerUp = () => {
      cleanup();
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    resizeCleanupRef.current = cleanup;
  };

  const treePanelLimits = getTreePanelLimits(getContainerWidth(containerRef.current));

  return (
    <Drawer
      className="code-browser-drawer"
      title={
        <div className="code-browser-title">
          <CodeOutlined />
          <span>代码浏览 - {versionName}</span>
        </div>
      }
      placement="right"
      width="85%"
      onClose={onClose}
      open={open}
    >
      <div ref={containerRef} className="code-browser-layout">
        <div className="code-browser-tree-panel" style={{ width: treePanelWidth }}>
          <div className="code-browser-tree-header">
            <span className="code-browser-tree-title">项目目录</span>
            <Tag className="code-browser-tree-width">{treePanelWidth}px</Tag>
          </div>

          <div className="code-browser-tree-body">
            {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 12 }} />}
            {loadingTree && !treeData.length ? (
              <div className="code-browser-tree-loading">
                <Spin tip="加载目录中..." />
              </div>
            ) : (
              <DirectoryTree
                className="code-browser-tree"
                showIcon
                expandAction="click"
                loadData={onLoadData}
                treeData={treeData}
                onSelect={onSelect}
              />
            )}
          </div>
        </div>

        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整目录宽度"
          aria-valuemin={treePanelLimits.min}
          aria-valuemax={treePanelLimits.max}
          aria-valuenow={treePanelWidth}
          tabIndex={0}
          onPointerDown={handleResizeStart}
          onKeyDown={handleResizeKeyDown}
          className="code-browser-resizer"
        >
          <div className="code-browser-resizer-handle" />
        </div>

        <div className="code-browser-viewer-panel">
          {selectedFilePath ? (
            <>
              <div className="code-browser-file-toolbar">
                <div className="code-browser-file-path" title={selectedFilePath}>
                  {selectedFilePath}
                </div>
                <div className="code-browser-toolbar-actions">
                  {lineSummary && <Tag className="code-browser-info-tag">{lineSummary}</Tag>}
                  {selectedFileMeta?.truncated && (
                    <Tag color="warning" className="code-browser-info-tag">
                      已截断
                    </Tag>
                  )}
                  <Tooltip title="复制文件内容">
                    <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyContent()} />
                  </Tooltip>
                </div>
              </div>

              <div className="code-browser-code-shell">
                {loadingFile ? (
                  <div className="code-browser-file-loading">
                    <Spin size="large" tip="加载文件内容中..." />
                  </div>
                ) : (
                  <div className="code-browser-code-scroll">
                    {highlightedLines.length ? (
                      <div className="code-browser-code-grid">
                        {highlightedLines.map((lineHtml, index) => (
                          <div className="code-browser-code-row" key={`${selectedFilePath}-${index}`}>
                            <span className="code-browser-line-number">{index + 1}</span>
                            <pre
                              className="code-browser-code-line"
                              dangerouslySetInnerHTML={{ __html: lineHtml }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="code-browser-empty-file">当前文件为空</div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="code-browser-empty-state">
              <Empty description="选择文件以查看内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
};

export default CodeBrowser;
