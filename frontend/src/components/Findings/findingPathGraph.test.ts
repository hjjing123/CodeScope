import { describe, expect, it } from 'vitest';

import type { FindingPath } from '../../types/finding';
import { buildFindingPathGraph, pickPreferredPathStep } from './findingPathGraph';

const samplePath: FindingPath = {
  path_id: 0,
  path_length: 4,
  steps: [
    { step_id: 0, labels: ['Method'], func_name: 'processbuilderVul', node_ref: 'method-1' },
    {
      step_id: 1,
      labels: ['Var', 'Param'],
      file: 'src/Main.java',
      line: 22,
      func_name: 'processbuilderVul',
      display_name: 'filepath',
      symbol_name: 'filepath',
      owner_method: 'processbuilderVul',
      node_kind: 'Var',
      code_snippet: 'String filepath',
      node_ref: 'var-1',
    },
    {
      step_id: 2,
      labels: ['Var', 'Decl'],
      file: 'src/Main.java',
      line: 24,
      func_name: 'processbuilderVul',
      display_name: 'cmdList',
      symbol_name: 'cmdList',
      owner_method: 'processbuilderVul',
      node_kind: 'Var',
      code_snippet: 'String[] cmdList = {"sh", "-c", "ls -l " + filepath};',
      node_ref: 'var-2',
    },
    {
      step_id: 3,
      labels: ['Call'],
      file: 'src/Main.java',
      line: 26,
      func_name: 'start',
      display_name: 'start',
      node_kind: 'Call',
      code_snippet: 'new ProcessBuilder(cmdList)',
      node_ref: 'call-1',
    },
  ],
  nodes: [
    {
      node_id: 0,
      labels: ['Method'],
      file: 'src/Main.java',
      line: 21,
      func_name: 'processbuilderVul',
      display_name: 'processbuilderVul',
      owner_method: 'processbuilderVul',
      node_kind: 'Method',
      node_ref: 'method-1',
      raw_props: {},
    },
    {
      node_id: 1,
      labels: ['Var', 'Param'],
      file: 'src/Main.java',
      line: 22,
      func_name: 'processbuilderVul',
      display_name: 'filepath',
      symbol_name: 'filepath',
      owner_method: 'processbuilderVul',
      node_kind: 'Var',
      code_snippet: 'String filepath',
      node_ref: 'var-1',
      raw_props: { declKind: 'Param' },
    },
    {
      node_id: 2,
      labels: ['Var', 'Decl'],
      file: 'src/Main.java',
      line: 24,
      func_name: 'processbuilderVul',
      display_name: 'cmdList',
      symbol_name: 'cmdList',
      owner_method: 'processbuilderVul',
      node_kind: 'Var',
      code_snippet: 'String[] cmdList = {"sh", "-c", "ls -l " + filepath};',
      node_ref: 'var-2',
      raw_props: { declKind: 'Local', assignRight: '"ls -l " + filepath' },
    },
    {
      node_id: 3,
      labels: ['Call'],
      file: 'src/Main.java',
      line: 26,
      func_name: 'start',
      display_name: 'start',
      owner_method: 'processbuilderVul',
      node_kind: 'Call',
      code_snippet: 'new ProcessBuilder(cmdList)',
      node_ref: 'call-1',
      raw_props: {},
    },
  ],
  edges: [
    {
      edge_id: 0,
      edge_type: 'ARG',
      from_node_id: 1,
      to_node_id: 2,
      from_step_id: 1,
      to_step_id: 2,
      label: '参数传递',
      is_hidden: false,
      props_json: { argIndex: 2 },
    },
    {
      edge_id: 1,
      edge_type: 'ARG',
      from_node_id: 2,
      to_node_id: 3,
      from_step_id: 2,
      to_step_id: 3,
      label: '参数传递',
      is_hidden: false,
      props_json: { argIndex: 0 },
    },
  ],
};

describe('findingPathGraph', () => {
  it('compacts raw nodes into a propagation-oriented graph', () => {
    const graph = buildFindingPathGraph(samplePath);

    expect(graph.rawNodeCount).toBe(4);
    expect(graph.isStructuralOnly).toBe(false);
    expect(graph.nodes.map((node) => node.title)).toEqual(['filepath', 'cmdList', 'start']);
    expect(graph.edges[0]?.label).toBe('赋值/拼接');
    expect(graph.edges[1]?.label).toBe('参数传递 #0');
  });

  it('picks the first meaningful step for source preview', () => {
    const step = pickPreferredPathStep(samplePath);

    expect(step?.step_id).toBe(1);
    expect(step?.display_name).toBe('filepath');
  });

  it('keeps a structural chain visible when semantic propagation is unavailable', () => {
    const structuralPath: FindingPath = {
      path_id: 1,
      path_length: 2,
      steps: [
        {
          step_id: 0,
          labels: ['Var', 'Param', 'SpringControllerArg'],
          file: 'src/XStreamVul.java',
          line: 43,
          display_name: 'args',
          symbol_name: 'args',
          node_kind: 'Var',
          node_ref: 'var-args',
        },
        {
          step_id: 1,
          labels: ['Method', 'SpringController'],
          file: 'src/XStreamVul.java',
          line: 43,
          display_name: 'main',
          symbol_name: 'main',
          node_kind: 'Method',
          node_ref: 'method-main',
        },
        {
          step_id: 2,
          labels: ['Call'],
          file: 'src/XStreamVul.java',
          line: 34,
          display_name: 'fromXML',
          node_kind: 'Call',
          node_ref: 'call-fromxml',
        },
      ],
      nodes: [
        {
          node_id: 0,
          labels: ['Var', 'Param', 'SpringControllerArg'],
          file: 'src/XStreamVul.java',
          line: 43,
          display_name: 'args',
          symbol_name: 'args',
          node_kind: 'Var',
          node_ref: 'var-args',
          raw_props: { declKind: 'Param' },
        },
        {
          node_id: 1,
          labels: ['Method', 'SpringController'],
          file: 'src/XStreamVul.java',
          line: 43,
          display_name: 'main',
          symbol_name: 'main',
          node_kind: 'Method',
          node_ref: 'method-main',
          raw_props: {},
        },
        {
          node_id: 2,
          labels: ['Call'],
          file: 'src/XStreamVul.java',
          line: 34,
          display_name: 'fromXML',
          node_kind: 'Call',
          node_ref: 'call-fromxml',
          raw_props: {},
        },
      ],
      edges: [
        {
          edge_id: 0,
          edge_type: 'ARG',
          from_node_id: 0,
          to_node_id: 1,
          from_step_id: 0,
          to_step_id: 1,
          label: '参数传递',
          is_hidden: false,
          props_json: {},
        },
        {
          edge_id: 1,
          edge_type: 'HAS_CALL',
          from_node_id: 1,
          to_node_id: 2,
          from_step_id: 1,
          to_step_id: 2,
          label: '调用包含',
          is_hidden: false,
          props_json: {},
        },
      ],
    };

    const graph = buildFindingPathGraph(structuralPath);

    expect(graph.isStructuralOnly).toBe(true);
    expect(graph.nodes.map((node) => node.title)).toEqual(['args', 'main', 'fromXML']);
    expect(graph.edges.map((edge) => edge.label)).toEqual(['参数传递', '调用包含']);
  });

  it('shows interprocedural parameter binding as semantic propagation', () => {
    const interproceduralPath: FindingPath = {
      path_id: 2,
      path_length: 3,
      steps: [
        {
          step_id: 0,
          labels: ['Var', 'Param', 'SpringControllerArg'],
          file: 'src/XStreamVul.java',
          line: 20,
          display_name: 'xml',
          symbol_name: 'xml',
          node_kind: 'Var',
          node_ref: 'var-xml',
        },
        {
          step_id: 1,
          labels: ['Var', 'Param'],
          file: 'src/Helper.java',
          line: 10,
          display_name: 'content',
          symbol_name: 'content',
          node_kind: 'Var',
          node_ref: 'var-content',
        },
        {
          step_id: 2,
          labels: ['Call'],
          file: 'src/Helper.java',
          line: 12,
          display_name: 'fromXML',
          node_kind: 'Call',
          node_ref: 'call-fromxml',
        },
      ],
      nodes: [
        {
          node_id: 0,
          labels: ['Var', 'Param', 'SpringControllerArg'],
          file: 'src/XStreamVul.java',
          line: 20,
          display_name: 'xml',
          symbol_name: 'xml',
          node_kind: 'Var',
          node_ref: 'var-xml',
          raw_props: { declKind: 'Param', paramIndex: 0 },
        },
        {
          node_id: 1,
          labels: ['Var', 'Param'],
          file: 'src/Helper.java',
          line: 10,
          display_name: 'content',
          symbol_name: 'content',
          node_kind: 'Var',
          node_ref: 'var-content',
          raw_props: { declKind: 'Param', paramIndex: 0 },
        },
        {
          node_id: 2,
          labels: ['Call'],
          file: 'src/Helper.java',
          line: 12,
          display_name: 'fromXML',
          node_kind: 'Call',
          node_ref: 'call-fromxml',
          raw_props: {},
        },
      ],
      edges: [
        {
          edge_id: 0,
          edge_type: 'PARAM_PASS',
          from_node_id: 0,
          to_node_id: 1,
          from_step_id: 0,
          to_step_id: 1,
          label: '跨函数参数传递',
          is_hidden: false,
          props_json: { argIndex: 0 },
        },
        {
          edge_id: 1,
          edge_type: 'ARG',
          from_node_id: 1,
          to_node_id: 2,
          from_step_id: 1,
          to_step_id: 2,
          label: '参数传递',
          is_hidden: false,
          props_json: { argIndex: 0 },
        },
      ],
    };

    const graph = buildFindingPathGraph(interproceduralPath);

    expect(graph.isStructuralOnly).toBe(false);
    expect(graph.nodes.map((node) => node.title)).toEqual(['xml', 'content', 'fromXML']);
    expect(graph.edges[0]?.label).toBe('跨函数参数传递 #0');
    expect(graph.edges[1]?.label).toBe('参数传递 #0');
  });

  it('hides synthetic locals and stack temporaries from graph nodes', () => {
    const path: FindingPath = {
      path_id: 3,
      path_length: 4,
      steps: [
        { step_id: 0, labels: ['Var', 'Param'], file: 'src/SSTI.java', line: 217, display_name: 'username', symbol_name: 'username', node_kind: 'Var', node_ref: 'username' },
        { step_id: 1, labels: ['Var', 'Reference'], file: 'src/SSTI.java', line: 226, display_name: 'templateString', symbol_name: 'templateString', node_kind: 'Var', node_ref: 'templateString' },
        { step_id: 2, labels: ['Var', 'Decl'], file: 'src/SSTI.java', line: 219, display_name: 'Local', node_kind: 'Var', node_ref: 'local' },
        { step_id: 3, labels: ['Var', 'Reference'], file: 'src/SSTI.java', line: 219, display_name: '$stack21', symbol_name: '$stack21', node_kind: 'Var', node_ref: '$stack21' },
        { step_id: 4, labels: ['Call'], file: 'src/SSTI.java', line: 219, display_name: 'new FileReader', node_kind: 'Call', node_ref: 'sink' },
      ],
      nodes: [
        { node_id: 0, labels: ['Var', 'Param'], file: 'src/SSTI.java', line: 217, display_name: 'username', symbol_name: 'username', node_kind: 'Var', node_ref: 'username', raw_props: { name: 'username', declKind: 'Param' } },
        { node_id: 1, labels: ['Var', 'Reference'], file: 'src/SSTI.java', line: 226, display_name: 'templateString', symbol_name: 'templateString', node_kind: 'Var', node_ref: 'templateString', raw_props: { name: 'templateString', declKind: 'Identifier', assignRight: 'templateString.replace("<USERNAME>", username)' } },
        { node_id: 2, labels: ['Var', 'Decl'], file: 'src/SSTI.java', line: 219, display_name: 'Local', node_kind: 'Var', node_ref: 'local', raw_props: { declKind: 'Local', name: '' } },
        { node_id: 3, labels: ['Var', 'Reference'], file: 'src/SSTI.java', line: 219, display_name: '$stack21', symbol_name: '$stack21', node_kind: 'Var', node_ref: '$stack21', raw_props: { name: '$stack21', declKind: 'Identifier' } },
        { node_id: 4, labels: ['Call'], file: 'src/SSTI.java', line: 219, display_name: 'new FileReader', node_kind: 'Call', node_ref: 'sink', raw_props: {} },
      ],
      edges: [
        { edge_id: 0, edge_type: 'REF', from_node_id: 0, to_node_id: 1, from_step_id: 0, to_step_id: 1, label: '引用传播', is_hidden: false, props_json: {} },
        { edge_id: 1, edge_type: 'REF', from_node_id: 1, to_node_id: 2, from_step_id: 1, to_step_id: 2, label: '引用传播', is_hidden: false, props_json: {} },
        { edge_id: 2, edge_type: 'REF', from_node_id: 2, to_node_id: 3, from_step_id: 2, to_step_id: 3, label: '引用传播', is_hidden: false, props_json: {} },
        { edge_id: 3, edge_type: 'ARG', from_node_id: 3, to_node_id: 4, from_step_id: 3, to_step_id: 4, label: '参数传递', is_hidden: false, props_json: { argIndex: 1 } },
      ],
    };

    const graph = buildFindingPathGraph(path);

    expect(graph.isStructuralOnly).toBe(false);
    expect(graph.nodes.map((node) => node.title)).toEqual(['username', 'templateString', 'new FileReader']);
    expect(graph.edges.map((edge) => edge.label)).toEqual(['赋值/拼接', '引用传播']);
  });
});
