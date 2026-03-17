import React, { useEffect, useMemo, useRef } from 'react';
import hljs from 'highlight.js/lib/common';
import { FileTextOutlined } from '@ant-design/icons';
import type { FindingHighlightRange } from '../../types/finding';
import '../ProjectVersion/CodeBrowser.css';

// Manual HTML escaping to match CodeBrowser implementation
const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

interface CodeViewerProps {
  code: string;
  language?: string;
  fileName?: string;
  highlightLines?: number[];
  highlightRanges?: FindingHighlightRange[];
  startLine?: number;
  focusLine?: number | null;
  focusRange?: FindingHighlightRange | null;
  summary?: string;
}

const escapePreservingWhitespace = (value: string) => {
  const escaped = escapeHtml(value);
  return escaped.length > 0 ? escaped : '&nbsp;';
};

const clampColumn = (value: number, min: number, max: number) => {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
};

const lineRanges = (ranges: FindingHighlightRange[], line: number, lineLength: number) => {
  const segments = ranges
    .filter((range) => range.start_line <= line && line <= range.end_line)
    .map((range) => {
      const startColumn = line === range.start_line ? range.start_column : 1;
      const endColumn = line === range.end_line ? range.end_column : lineLength;
      const start = clampColumn(startColumn - 1, 0, lineLength);
      const endExclusive = clampColumn(endColumn, start, lineLength);
      return {
        start,
        endExclusive,
        confidence: range.confidence,
      };
    })
    .filter((range) => range.endExclusive > range.start)
    .sort((left, right) => left.start - right.start);

  const merged: Array<{ start: number; endExclusive: number; confidence?: string | null }> = [];
  segments.forEach((segment) => {
    const previous = merged[merged.length - 1];
    if (!previous || segment.start > previous.endExclusive) {
      merged.push(segment);
      return;
    }
    previous.endExclusive = Math.max(previous.endExclusive, segment.endExclusive);
  });
  return merged;
};

const renderHighlightedLine = (
  rawLine: string,
  ranges: FindingHighlightRange[],
  absoluteLine: number,
  isFocusLine: boolean
) => {
  const segments = lineRanges(ranges, absoluteLine, rawLine.length);
  if (!segments.length) {
    return escapePreservingWhitespace(rawLine);
  }
  let cursor = 0;
  let html = '';
  segments.forEach((segment) => {
    if (segment.start > cursor) {
      html += escapePreservingWhitespace(rawLine.slice(cursor, segment.start));
    }
    const confidence = segment.confidence || 'high';
    const background = isFocusLine
      ? 'rgba(250, 204, 21, 0.55)'
      : confidence === 'low'
        ? 'rgba(59, 130, 246, 0.2)'
        : 'rgba(250, 204, 21, 0.4)';
    html += `<mark style="background:${background};color:#0f172a;padding:0 1px;border-radius:3px;">${escapePreservingWhitespace(rawLine.slice(segment.start, segment.endExclusive))}</mark>`;
    cursor = segment.endExclusive;
  });
  if (cursor < rawLine.length) {
    html += escapePreservingWhitespace(rawLine.slice(cursor));
  }
  return html || '&nbsp;';
};

const CodeViewer: React.FC<CodeViewerProps> = ({
  code,
  language = 'java',
  fileName,
  highlightLines = [],
  highlightRanges = [],
  startLine = 1,
  focusLine,
  focusRange,
  summary,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rawLines = useMemo(() => code.split('\n'), [code]);
  const hasPreciseRanges = highlightRanges.length > 0;
  const highlightedLines = useMemo(() => {
    if (!code) return [];

    return rawLines.map((line, index) => {
      const absoluteLine = startLine + index;
      const hasRange = lineRanges(highlightRanges, absoluteLine, line.length).length > 0;
      if (hasRange) {
        return renderHighlightedLine(
          line,
          highlightRanges,
          absoluteLine,
          focusRange?.start_line === absoluteLine
        );
      }
      if (!line) return '&nbsp;';

      try {
        if (language && hljs.getLanguage(language)) {
          return hljs.highlight(line, { language, ignoreIllegals: true }).value;
        }
        return hljs.highlightAuto(line).value;
      } catch {
        return escapeHtml(line);
      }
    });
  }, [code, focusRange?.start_line, highlightRanges, language, rawLines, startLine]);

  useEffect(() => {
    const targetLine = focusRange?.start_line ?? focusLine;
    if (!targetLine || !scrollRef.current) {
      return;
    }
    const target = scrollRef.current.querySelector<HTMLElement>(`[data-line="${targetLine}"]`);
    target?.scrollIntoView({ block: 'center' });
  }, [focusLine, focusRange?.start_line, code, fileName]);

  return (
    <div className="code-browser-viewer-panel" style={{ height: '100%', background: '#0f172a', borderRadius: 8, border: '1px solid #334155' }}>
      {/* File Toolbar - Reusing CodeBrowser styles */}
      {fileName && (
        <div className="code-browser-file-toolbar" style={{ borderBottomColor: '#334155', background: '#1e293b', borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
          <div className="code-browser-file-path" style={{ color: '#e2e8f0', fontSize: '13px' }}>
            <FileTextOutlined style={{ marginRight: 8, color: '#94a3b8' }} />
            {fileName}
          </div>
          {summary && (
            <div className="code-browser-toolbar-actions">
              <span className="code-browser-info-tag" style={{ color: '#94a3b8', fontSize: 12 }}>
                {summary}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Code Area */}
      <div className="code-browser-code-shell" style={{ padding: 0 }}>
        <div ref={scrollRef} className="code-browser-code-scroll" style={{ borderRadius: fileName ? '0 0 8px 8px' : 8, border: 'none' }}>
          <div className="code-browser-code-grid">
            {highlightedLines.map((lineHtml, index) => {
              const lineNum = startLine + index;
              const usesLineHighlight = !hasPreciseRanges;
              const isHighlighted = usesLineHighlight && highlightLines.includes(lineNum);
              const isFocused = usesLineHighlight && (focusRange?.start_line === lineNum || focusLine === lineNum);
              
              return (
                <div 
                  className="code-browser-code-row" 
                  key={index}
                  data-line={lineNum}
                  style={isFocused ? { background: 'rgba(250, 204, 21, 0.22)' } : isHighlighted ? { background: 'rgba(59, 130, 246, 0.15)' } : undefined}
                >
                  <span 
                    className="code-browser-line-number"
                  style={isFocused ? { color: '#fde68a', fontWeight: 'bold', borderRightColor: '#f59e0b' } : isHighlighted ? { color: '#e2e8f0', fontWeight: 'bold', borderRightColor: '#3b82f6' } : undefined}
                  >
                    {lineNum}
                  </span>
                  <pre
                    className="code-browser-code-line"
                    dangerouslySetInnerHTML={{ __html: lineHtml }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CodeViewer;
