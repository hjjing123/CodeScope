from __future__ import annotations

from typing import Any


EDGE_TYPE_LABELS: dict[str, str] = {
    "ARG": "参数传递",
    "REF": "引用传播",
    "CALLS": "跨方法调用",
    "PARAM_PASS": "跨函数参数传递",
    "AST": "语法展开",
    "HAS_CALL": "调用包含",
    "IN_FILE": "文件归属",
    "STEP_NEXT": "步骤连接",
}

HIDDEN_EDGE_TYPES = {"HAS_CALL", "IN_FILE"}


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
