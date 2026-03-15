from __future__ import annotations

from typing import Any

from app.services.source_location_service import normalize_graph_location


EDGE_TYPE_LABELS: dict[str, str] = {
    "ARG": "参数传递",
    "REF": "引用传播",
    "CALLS": "跨方法调用",
    "PARAM_PASS": "跨函数参数传递",
    "AST": "语法展开",
    "HAS_CALL": "调用包含",
    "IN_FILE": "文件归属",
    "SRC_FLOW": "源码补链",
    "STEP_NEXT": "步骤连接",
}

HIDDEN_EDGE_TYPES = {"HAS_CALL", "IN_FILE"}
SEMANTIC_EDGE_TYPES = frozenset({"REF", "PARAM_PASS", "SRC_FLOW"})
WEAK_EDGE_TYPES = frozenset({"ARG", "CALLS", "STEP_NEXT"})
STRUCTURAL_EDGE_TYPES = frozenset({"AST", "HAS_CALL", "IN_FILE"})


def _short_display_text(value: str | None, *, max_length: int = 80) -> str | None:
    text = to_text(value)
    if text is None:
        return None
    single_line = " ".join(text.split())
    if len(single_line) <= max_length:
        return single_line
    return f"{single_line[:max_length]}..."


def to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def trim_code_snippet(value: object, *, max_length: int = 240) -> str | None:
    text = to_text(value)
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def edge_display_label(edge_type: str | None) -> str:
    normalized = to_text(edge_type) or "EDGE"
    return EDGE_TYPE_LABELS.get(normalized, normalized)


def edge_is_hidden(edge_type: str | None) -> bool:
    normalized = (to_text(edge_type) or "").upper()
    return normalized in HIDDEN_EDGE_TYPES


def build_path_node_payload(
    *,
    index: int,
    labels: list[str],
    props: dict[str, Any] | None,
    node_ref: str | None,
) -> dict[str, object]:
    safe_props = dict(props or {})
    symbol_name = to_text(safe_props.get("name"))
    owner_method = to_text(safe_props.get("method"))
    full_name = to_text(safe_props.get("fullName"))
    display_hint = _short_display_text(safe_props.get("displayName"))
    code_hint = _short_display_text(safe_props.get("code"))
    normalized_node_ref = (
        to_text(node_ref)
        or to_text(safe_props.get("id"))
        or full_name
        or symbol_name
        or f"node-{index}"
    )
    display_name = (
        display_hint
        or symbol_name
        or owner_method
        or full_name
        or code_hint
        or normalized_node_ref
    )
    return {
        "node_id": index,
        "labels": [str(item) for item in labels if str(item).strip()],
        "file": to_text(safe_props.get("file")),
        "line": to_int(safe_props.get("line")),
        "column": to_int(safe_props.get("col")),
        "func_name": owner_method or symbol_name,
        "display_name": display_name,
        "symbol_name": symbol_name,
        "owner_method": owner_method,
        "type_name": to_text(safe_props.get("type"))
        or to_text(safe_props.get("receiverType")),
        "node_kind": to_text(safe_props.get("kind")),
        "code_snippet": trim_code_snippet(safe_props.get("code")),
        "node_ref": normalized_node_ref,
        "raw_props": safe_props,
    }


def build_path_step_payload(node: dict[str, object]) -> dict[str, object]:
    step_id = to_int(node.get("node_id")) or 0
    return {
        "step_id": step_id,
        "labels": [
            str(item)
            for item in node.get("labels") or []
            if isinstance(item, str) and item.strip()
        ],
        "file": to_text(node.get("file")),
        "line": to_int(node.get("line")),
        "column": to_int(node.get("column")),
        "func_name": to_text(node.get("func_name")),
        "display_name": to_text(node.get("display_name")),
        "symbol_name": to_text(node.get("symbol_name")),
        "owner_method": to_text(node.get("owner_method")),
        "type_name": to_text(node.get("type_name")),
        "node_kind": to_text(node.get("node_kind")),
        "code_snippet": trim_code_snippet(node.get("code_snippet")),
        "node_ref": to_text(node.get("node_ref")) or f"step-{step_id}",
    }


def build_path_edge_payload(
    *,
    index: int,
    edge_type: str | None,
    from_node_id: int | None,
    to_node_id: int | None,
    from_node_ref: str | None,
    to_node_ref: str | None,
    props: dict[str, Any] | None,
    edge_ref: str | None = None,
    label: str | None = None,
    is_hidden: bool | None = None,
) -> dict[str, object]:
    normalized_edge_type = to_text(edge_type) or "EDGE"
    hidden = (
        edge_is_hidden(normalized_edge_type) if is_hidden is None else bool(is_hidden)
    )
    normalized_edge_ref = to_text(edge_ref) or f"edge-{index}"
    return {
        "edge_id": index,
        "edge_order": index,
        "edge_type": normalized_edge_type,
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "from_step_id": from_node_id,
        "to_step_id": to_node_id,
        "from_node_ref": to_text(from_node_ref),
        "to_node_ref": to_text(to_node_ref),
        "label": to_text(label) or edge_display_label(normalized_edge_type),
        "is_hidden": hidden,
        "props_json": dict(props or {}),
        "edge_ref": normalized_edge_ref,
    }


def build_linear_path_edges(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    for index in range(max(0, len(nodes) - 1)):
        current = nodes[index]
        nxt = nodes[index + 1]
        edges.append(
            build_path_edge_payload(
                index=index,
                edge_type="STEP_NEXT",
                from_node_id=to_int(current.get("node_id")),
                to_node_id=to_int(nxt.get("node_id")),
                from_node_ref=to_text(current.get("node_ref")),
                to_node_ref=to_text(nxt.get("node_ref")),
                props={},
                label="步骤连接",
                is_hidden=False,
            )
        )
    return edges


def normalize_path_step(
    *, version_id, item: dict[str, object], index: int
) -> dict[str, object]:
    normalized_file, normalized_line = normalize_graph_location(
        version_id=version_id,
        file_path=to_text(item.get("file")),
        line=item.get("line"),
        func_name=to_text(item.get("func_name")),
        code_snippet=to_text(item.get("code_snippet")),
        node_ref=to_text(item.get("node_ref")),
        labels=[
            str(label)
            for label in item.get("labels") or []
            if isinstance(label, str) and label.strip()
        ],
    )
    return {
        **item,
        "step_id": index,
        "column": to_int(item.get("column")),
        "display_name": to_text(item.get("display_name")),
        "symbol_name": to_text(item.get("symbol_name")),
        "owner_method": to_text(item.get("owner_method")),
        "type_name": to_text(item.get("type_name")),
        "node_kind": to_text(item.get("node_kind")),
        "file": normalized_file,
        "line": normalized_line,
    }


def normalize_path_steps(*, version_id, steps: object) -> list[dict[str, object]]:
    if not isinstance(steps, list):
        return []
    normalized_steps: list[dict[str, object]] = []
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            continue
        normalized_steps.append(
            normalize_path_step(version_id=version_id, item=item, index=index)
        )
    return normalized_steps


def normalize_path_node(
    *, version_id, item: dict[str, object], index: int
) -> dict[str, object]:
    normalized_file, normalized_line = normalize_graph_location(
        version_id=version_id,
        file_path=to_text(item.get("file")),
        line=item.get("line"),
        func_name=to_text(item.get("func_name")),
        code_snippet=to_text(item.get("code_snippet")),
        node_ref=to_text(item.get("node_ref")),
        labels=[
            str(label)
            for label in item.get("labels") or []
            if isinstance(label, str) and label.strip()
        ],
    )
    raw_props = item.get("raw_props") if isinstance(item.get("raw_props"), dict) else {}
    return {
        **item,
        "node_id": index,
        "file": normalized_file,
        "line": normalized_line,
        "column": to_int(item.get("column")),
        "display_name": to_text(item.get("display_name")),
        "symbol_name": to_text(item.get("symbol_name")),
        "owner_method": to_text(item.get("owner_method")),
        "type_name": to_text(item.get("type_name")),
        "node_kind": to_text(item.get("node_kind")),
        "node_ref": to_text(item.get("node_ref")) or f"node-{index}",
        "raw_props": raw_props,
    }


def normalize_path_nodes(*, version_id, nodes: object) -> list[dict[str, object]]:
    if not isinstance(nodes, list):
        return []
    normalized_nodes: list[dict[str, object]] = []
    for index, item in enumerate(nodes):
        if not isinstance(item, dict):
            continue
        normalized_nodes.append(
            normalize_path_node(version_id=version_id, item=item, index=index)
        )
    return normalized_nodes


def derive_path_nodes_from_steps(
    steps: list[dict[str, object]],
) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        nodes.append(
            {
                "node_id": index,
                "labels": [
                    str(item)
                    for item in step.get("labels") or []
                    if isinstance(item, str) and item.strip()
                ],
                "file": to_text(step.get("file")),
                "line": to_int(step.get("line")),
                "column": to_int(step.get("column")),
                "func_name": to_text(step.get("func_name")),
                "display_name": to_text(step.get("display_name")),
                "symbol_name": to_text(step.get("symbol_name")),
                "owner_method": to_text(step.get("owner_method")),
                "type_name": to_text(step.get("type_name")),
                "node_kind": to_text(step.get("node_kind")),
                "code_snippet": to_text(step.get("code_snippet")),
                "node_ref": to_text(step.get("node_ref")) or f"node-{index}",
                "raw_props": {},
            }
        )
    return nodes


def normalize_path_edges(
    *, edges: object, nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    if not isinstance(edges, list):
        return []
    node_index_by_ref = {
        str(node.get("node_ref") or ""): int(node.get("node_id") or 0)
        for node in nodes
        if str(node.get("node_ref") or "")
    }
    normalized_edges: list[dict[str, object]] = []
    for index, item in enumerate(edges):
        if not isinstance(item, dict):
            continue
        props = (
            item.get("props_json")
            if isinstance(item.get("props_json"), dict)
            else item.get("props")
            if isinstance(item.get("props"), dict)
            else {}
        )
        from_node_ref = to_text(item.get("from_node_ref"))
        to_node_ref = to_text(item.get("to_node_ref"))
        from_node_id = node_index_by_ref.get(from_node_ref or "")
        to_node_id = node_index_by_ref.get(to_node_ref or "")
        if from_node_id is None:
            from_node_id = to_int(item.get("from_node_id"))
            if from_node_id is None:
                from_node_id = to_int(item.get("from_step_id"))
        if to_node_id is None:
            to_node_id = to_int(item.get("to_node_id"))
            if to_node_id is None:
                to_node_id = to_int(item.get("to_step_id"))
        normalized_edges.append(
            build_path_edge_payload(
                index=index,
                edge_type=to_text(item.get("edge_type") or item.get("type")),
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                from_node_ref=from_node_ref,
                to_node_ref=to_node_ref,
                props=props,
                edge_ref=to_text(item.get("edge_ref")),
                label=to_text(item.get("label")),
                is_hidden=item.get("is_hidden")
                if item.get("is_hidden") is not None
                else None,
            )
        )
    return normalized_edges


def normalize_path_graph(
    *, version_id, path_item: dict[str, object], path_index: int
) -> dict[str, object] | None:
    nodes = normalize_path_nodes(version_id=version_id, nodes=path_item.get("nodes"))
    if nodes:
        steps = [build_path_step_payload(node) for node in nodes]
    else:
        steps = normalize_path_steps(
            version_id=version_id, steps=path_item.get("steps")
        )
        nodes = derive_path_nodes_from_steps(steps)
    if not steps:
        return None
    edges = normalize_path_edges(edges=path_item.get("edges"), nodes=nodes)
    if not edges:
        edges = build_linear_path_edges(nodes)
    path_length = to_int(path_item.get("path_length"))
    if path_length is None:
        path_length = len(edges) or max(0, len(steps) - 1)
    return {
        **path_item,
        "path_id": path_index,
        "path_length": max(0, path_length or 0),
        "steps": steps,
        "nodes": nodes,
        "edges": edges,
    }


def extract_path_node_ref(node: dict[str, object]) -> str | None:
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    for candidate in (raw_props.get("id"), node.get("node_ref")):
        text = to_text(candidate)
        if text:
            return text
    return None


def path_edge_types(paths: list[dict[str, object]] | dict[str, object]) -> list[str]:
    items = paths if isinstance(paths, list) else [paths]
    edge_types: list[str] = []
    for path in items:
        if not isinstance(path, dict):
            continue
        for edge in path.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            edge_type = to_text(edge.get("edge_type"))
            if edge_type:
                edge_types.append(edge_type)
    return edge_types


def path_has_semantic_signal(
    paths: list[dict[str, object]] | dict[str, object],
) -> bool:
    return bool(set(path_edge_types(paths)) & SEMANTIC_EDGE_TYPES)


def collect_path_labels(
    paths: list[dict[str, object]] | dict[str, object],
) -> list[str]:
    items = paths if isinstance(paths, list) else [paths]
    labels: list[str] = []
    for path in items:
        if not isinstance(path, dict):
            continue
        for step in path.get("steps") or []:
            if not isinstance(step, dict):
                continue
            for label in step.get("labels") or []:
                text = to_text(label)
                if text:
                    labels.append(text)
    return labels


def _node_labels(node: dict[str, object]) -> set[str]:
    return {
        str(item).strip()
        for item in node.get("labels") or []
        if isinstance(item, str) and item.strip()
    }


def _source_anchor_score(node: dict[str, object], *, index: int, total: int) -> int:
    labels = {label.lower() for label in _node_labels(node)}
    score = max(0, 50 - index * 3)
    if any("entry" in label for label in labels):
        score += 40
    if any(label.endswith("arg") or label.endswith("param") for label in labels):
        score += 25
    if "argument" in labels or "param" in labels:
        score += 20
    if to_text(node.get("node_kind")) == "Var":
        score += 15
    if "method" in labels:
        score -= 60
    if "call" in labels:
        score -= 10
    if index == 0:
        score += 10
    return score


def _sink_anchor_score(node: dict[str, object], *, index: int, total: int) -> int:
    labels = {label.lower() for label in _node_labels(node)}
    score = index * 3
    if any("sink" in label or "unsafe" in label for label in labels):
        score += 45
    if "call" in labels:
        score += 35
    if to_text(node.get("node_kind")) == "Call":
        score += 30
    if to_text(node.get("node_kind")) == "Var":
        score += 10
    if "method" in labels:
        score -= 60
    if index == total - 1:
        score += 10
    return score


def select_path_anchor_pair(
    path: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    if not nodes:
        return None, None
    total = len(nodes)
    best_source: tuple[int, int] | None = None
    best_sink: tuple[int, int] | None = None
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        source_score = _source_anchor_score(node, index=index, total=total)
        sink_score = _sink_anchor_score(node, index=index, total=total)
        if best_source is None or source_score > best_source[1]:
            best_source = (index, source_score)
        if best_sink is None or sink_score >= best_sink[1]:
            best_sink = (index, sink_score)
    if best_source is None or best_sink is None:
        return None, None
    source_index = best_source[0]
    sink_index = best_sink[0]
    if sink_index <= source_index:
        sink_index = total - 1
        if sink_index <= source_index:
            source_index = 0
            sink_index = total - 1
    source = nodes[source_index] if source_index < total else None
    sink = nodes[sink_index] if sink_index < total else None
    if not isinstance(source, dict) or not isinstance(sink, dict):
        return None, None
    return source, sink


def canonical_path_fingerprint(path: dict[str, object]) -> str:
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    edges = path.get("edges") if isinstance(path.get("edges"), list) else []
    source, sink = select_path_anchor_pair(path)
    source_ref = extract_path_node_ref(source) if isinstance(source, dict) else None
    sink_ref = extract_path_node_ref(sink) if isinstance(sink, dict) else None
    edge_types = ",".join(
        to_text(edge.get("edge_type")) or "EDGE"
        for edge in edges
        if isinstance(edge, dict)
    )
    return (
        f"src={source_ref or '-'}|sink={sink_ref or '-'}|"
        f"nodes={len(nodes)}|edges={edge_types}"
    )
