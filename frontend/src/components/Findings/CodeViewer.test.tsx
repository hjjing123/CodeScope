import { render } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import CodeViewer from './CodeViewer';

describe('CodeViewer', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('renders precise highlight ranges inside a line', () => {
    const { container } = render(
      <CodeViewer
        code={'<dependency>\n<artifactId>xstream</artifactId>\n<version>1.4.10</version>'}
        language="java"
        startLine={85}
        focusLine={85}
        highlightRanges={[
          {
            start_line: 86,
            start_column: 13,
            end_line: 86,
            end_column: 19,
            text: 'xstream',
            kind: 'component',
            confidence: 'high',
          },
          {
            start_line: 87,
            start_column: 10,
            end_line: 87,
            end_column: 15,
            text: '1.4.10',
            kind: 'version',
            confidence: 'high',
          },
        ]}
        focusRange={{
          start_line: 86,
          start_column: 13,
          end_line: 86,
          end_column: 19,
          text: 'xstream',
          kind: 'component',
          confidence: 'high',
        }}
      />
    );

    const marks = container.querySelectorAll('mark');
    const dependencyRow = container.querySelector('[data-line="85"]');
    const artifactRow = container.querySelector('[data-line="86"]');
    expect(marks[0]?.textContent).toBe('xstream');
    expect(marks[1]?.textContent).toBe('1.4.10');
    expect(dependencyRow?.getAttribute('style') || '').not.toContain('background');
    expect(artifactRow?.getAttribute('style') || '').not.toContain('background');
  });
});
