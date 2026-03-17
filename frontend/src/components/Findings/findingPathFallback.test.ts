import { describe, expect, it } from 'vitest';

import type { Finding } from '../../types/finding';
import { buildFallbackFindingPaths } from './findingPathFallback';

const buildFinding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'finding-1',
  project_id: 'project-1',
  version_id: 'version-1',
  job_id: 'job-1',
  rule_key: 'demo_rule',
  severity: 'HIGH',
  status: 'new',
  has_path: false,
  evidence_json: {},
  created_at: '2026-03-14T00:00:00Z',
  ...overrides,
});

describe('findingPathFallback', () => {
  it('builds a single-step fallback path from the matched location', () => {
    const finding = buildFinding({
      file_path: 'pom.xml',
      line_start: 85,
      sink_file: 'pom.xml',
      sink_line: 85,
      evidence_json: {
        labels: ['PomDependency'],
        node_ref: 'dependency-1',
        code_context: {
          focus: {
            file_path: 'pom.xml',
            start_line: 83,
            snippet: '<dependency>...</dependency>',
          },
        },
      },
    });

    const [path] = buildFallbackFindingPaths(finding);

    expect(path.steps).toHaveLength(1);
    expect(path.steps[0]).toMatchObject({
      file: 'pom.xml',
      line: 85,
      display_name: 'Sink',
      node_ref: 'dependency-1',
    });
    expect(path.nodes?.[0]?.raw_props).toMatchObject({ fallback: true });
  });

  it('builds a source-to-sink fallback when both endpoints are available', () => {
    const finding = buildFinding({
      file_path: 'src/App.java',
      source_file: 'src/App.java',
      source_line: 12,
      sink_file: 'src/App.java',
      sink_line: 28,
      evidence_json: {
        labels: ['Var', 'Reference'],
      },
    });

    const [path] = buildFallbackFindingPaths(finding);

    expect(path.path_length).toBe(1);
    expect(path.steps.map((step) => `${step.display_name}:${step.line}`)).toEqual([
      'Source:12',
      'Sink:28',
    ]);
    expect(path.edges?.[0]).toMatchObject({
      edge_type: 'STEP_NEXT',
      label: '定位关联',
    });
  });

  it('merges identical source and sink locations into one node', () => {
    const finding = buildFinding({
      file_path: 'src/App.java',
      source_file: 'src/App.java',
      source_line: 18,
      sink_file: 'src/App.java',
      sink_line: 18,
    });

    const [path] = buildFallbackFindingPaths(finding);

    expect(path.steps).toHaveLength(1);
    expect(path.steps[0]).toMatchObject({
      file: 'src/App.java',
      line: 18,
      display_name: 'Source / Sink',
    });
  });

  it('uses match label for node-only findings without propagation', () => {
    const finding = buildFinding({
      has_path: false,
      file_path: 'pom.xml',
      line_start: 85,
      sink_file: 'pom.xml',
      sink_line: 85,
      evidence_json: {
        match_kind: 'node',
        labels: ['PomDependency'],
        node_ref: 'dependency-1',
      },
    });

    const [path] = buildFallbackFindingPaths(finding);

    expect(path.steps).toHaveLength(1);
    expect(path.steps[0]).toMatchObject({
      display_name: 'Match',
      file: 'pom.xml',
      line: 85,
    });
  });
});
