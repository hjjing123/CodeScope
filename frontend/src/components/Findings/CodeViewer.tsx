import React, { useMemo } from 'react';
import hljs from 'highlight.js/lib/common';
import { FileTextOutlined } from '@ant-design/icons';
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
  startLine?: number;
}

const CodeViewer: React.FC<CodeViewerProps> = ({
  code,
  language = 'java',
  fileName,
  highlightLines = [],
  startLine = 1,
}) => {
  const highlightedLines = useMemo(() => {
    if (!code) return [];

    return code.split('\n').map((line) => {
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
  }, [code, language]);

  return (
    <div className="code-browser-viewer-panel" style={{ height: '100%', background: '#0f172a', borderRadius: 8, border: '1px solid #334155' }}>
      {/* File Toolbar - Reusing CodeBrowser styles */}
      {fileName && (
        <div className="code-browser-file-toolbar" style={{ borderBottomColor: '#334155', background: '#1e293b', borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
          <div className="code-browser-file-path" style={{ color: '#e2e8f0', fontSize: '13px' }}>
            <FileTextOutlined style={{ marginRight: 8, color: '#94a3b8' }} />
            {fileName}
          </div>
        </div>
      )}

      {/* Code Area */}
      <div className="code-browser-code-shell" style={{ padding: 0 }}>
        <div className="code-browser-code-scroll" style={{ borderRadius: fileName ? '0 0 8px 8px' : 8, border: 'none' }}>
          <div className="code-browser-code-grid">
            {highlightedLines.map((lineHtml, index) => {
              const lineNum = startLine + index;
              const isHighlighted = highlightLines.includes(lineNum);
              
              return (
                <div 
                  className="code-browser-code-row" 
                  key={index}
                  style={isHighlighted ? { background: 'rgba(59, 130, 246, 0.15)' } : undefined}
                >
                  <span 
                    className="code-browser-line-number"
                    style={isHighlighted ? { color: '#e2e8f0', fontWeight: 'bold', borderRightColor: '#3b82f6' } : undefined}
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
