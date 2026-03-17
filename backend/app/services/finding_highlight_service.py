from __future__ import annotations

import uuid
from typing import Any

from app.services.java_trace_parser_service import (
    _find_method,
    _find_method_node,
    _load_parsed_java_file,
    _read_file_text,
)
from app.services.path_graph_service import to_int, to_text


def resolve_path_step_highlight(
    *, version_id: uuid.UUID, path: dict[str, object], step_id: int
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    steps = path.get("steps") if isinstance(path.get("steps"), list) else []
    if step_id < 0 or step_id >= len(steps):
        return [], None
    step = steps[step_id] if isinstance(steps[step_id], dict) else None
    if not isinstance(step, dict):
        return [], None
    node = _find_step_node(path=path, step=step)
    file_path = to_text(step.get("file")) or (
        to_text(node.get("file")) if isinstance(node, dict) else None
    )
    line = to_int(step.get("line")) or (
        to_int(node.get("line")) if isinstance(node, dict) else None
    )
    if not file_path or line is None:
        return [], None

    highlight_ranges: list[dict[str, object]] = []
    if file_path.lower().endswith(".java"):
        highlight_ranges = _resolve_java_step_ranges(
            version_id=version_id,
            path=path,
            step=step,
            node=node,
            file_path=file_path,
            line=line,
        )
    if not highlight_ranges:
        fallback = _line_fallback_range(
            version_id=version_id,
            file_path=file_path,
            line=line,
            step=step,
            node=node,
        )
        if fallback is not None:
            highlight_ranges = [fallback]
    focus_range = highlight_ranges[0] if highlight_ranges else None
    return highlight_ranges, focus_range


def resolve_finding_focus_highlight(
    *,
    version_id: uuid.UUID,
    rule_key: str,
    file_path: str,
    line: int,
    evidence: dict[str, object] | None,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    normalized_file = to_text(file_path)
    normalized_line = to_int(line)
    if not normalized_file or normalized_line is None:
        return [], None
    safe_evidence = evidence if isinstance(evidence, dict) else {}
    source_bytes = _normalized_source_bytes(
        version_id=version_id,
        file_path=normalized_file,
    )
    if source_bytes is None:
        return [], None

    labels = (
        safe_evidence.get("labels")
        if isinstance(safe_evidence.get("labels"), list)
        else []
    )
    node_ref = to_text(safe_evidence.get("node_ref"))
    label_set = {str(label).strip() for label in labels if str(label).strip()}

    highlight_ranges: list[dict[str, object]] = []
    if "PomDependency" in label_set or normalized_file.lower().endswith("pom.xml"):
        highlight_ranges = _resolve_pom_dependency_ranges(
            source_bytes=source_bytes,
            line=normalized_line,
            node_ref=node_ref,
        )
    elif "PropertiesKeyValue" in label_set or normalized_file.lower().endswith(
        ".properties"
    ):
        highlight_ranges = _resolve_properties_key_value_ranges(
            source_bytes=source_bytes,
            line=normalized_line,
            node_ref=node_ref,
            rule_key=rule_key,
        )

    if not highlight_ranges:
        fallback = _line_fallback_range_from_bytes(
            source_bytes=source_bytes,
            line=normalized_line,
            symbol=_node_ref_focus_symbol(node_ref),
        )
        if fallback is not None:
            highlight_ranges = [fallback]

    focus_range = highlight_ranges[0] if highlight_ranges else None
    return highlight_ranges, focus_range


def _find_step_node(
    *, path: dict[str, object], step: dict[str, object]
) -> dict[str, object] | None:
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    step_id = to_int(step.get("step_id"))
    node_ref = to_text(step.get("node_ref"))
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if step_id is not None and to_int(node.get("node_id")) == step_id:
            return node
        if node_ref and to_text(node.get("node_ref")) == node_ref:
            return node
    return None


def _resolve_java_step_ranges(
    *,
    version_id: uuid.UUID,
    path: dict[str, object],
    step: dict[str, object],
    node: dict[str, object] | None,
    file_path: str,
    line: int,
) -> list[dict[str, object]]:
    parsed = _load_parsed_java_file(version_id=version_id, file_path=file_path)
    if parsed is None:
        return []
    root_node, _methods = parsed
    source_bytes = _normalized_source_bytes(version_id=version_id, file_path=file_path)
    if source_bytes is None:
        return []
    method_fact = _find_method(version_id=version_id, file_path=file_path, line=line)
    method_node = (
        _find_method_node(root_node=root_node, method=method_fact)
        if method_fact is not None
        else None
    )
    raw_props = (
        node.get("raw_props")
        if isinstance(node, dict) and isinstance(node.get("raw_props"), dict)
        else {}
    )
    symbol = _primary_symbol(step=step, node=node)
    node_kind = (
        to_text(step.get("node_kind")) or to_text(node.get("node_kind"))
        if isinstance(node, dict)
        else ""
    ) or ""
    lowered_kind = node_kind.lower()

    if lowered_kind == "var":
        ranges = _resolve_java_var_ranges(
            source_bytes=source_bytes,
            root_node=root_node,
            method_node=method_node,
            raw_props=raw_props,
            symbol=symbol,
            line=line,
        )
        if ranges:
            return ranges

    if lowered_kind == "call":
        ranges = _resolve_java_call_ranges(
            path=path,
            source_bytes=source_bytes,
            root_node=root_node,
            method_node=method_node,
            raw_props=raw_props,
            symbol=symbol,
            line=line,
            incoming_edge=_find_incoming_edge(path=path, step=step),
        )
        if ranges:
            return ranges

    if symbol:
        token_range = _line_symbol_fallback(
            source_bytes=source_bytes,
            file_path=file_path,
            line=line,
            symbol=symbol,
        )
        if token_range is not None:
            return [token_range]
    return []


def _resolve_java_var_ranges(
    *,
    source_bytes: bytes,
    root_node: Any,
    method_node: Any | None,
    raw_props: dict[str, object],
    symbol: str | None,
    line: int,
) -> list[dict[str, object]]:
    if not symbol:
        return []
    decl_kind = (to_text(raw_props.get("declKind")) or "").lower()
    param_index = to_int(raw_props.get("paramIndex"))
    search_root = method_node or root_node

    if decl_kind == "param" or param_index is not None:
        param_range = _resolve_parameter_range(
            source_bytes=source_bytes,
            method_node=method_node,
            symbol=symbol,
            param_index=param_index,
            target_line=line,
        )
        if param_range is not None:
            return [param_range]

    identifier_range = _resolve_identifier_range(
        source_bytes=source_bytes,
        root_node=search_root,
        symbol=symbol,
        target_line=line,
        prefer_declaration=decl_kind in {"local", "field", "param"},
    )
    if identifier_range is not None:
        return [identifier_range]
    return []


def _resolve_java_call_ranges(
    *,
    path: dict[str, object],
    source_bytes: bytes,
    root_node: Any,
    method_node: Any | None,
    raw_props: dict[str, object],
    symbol: str | None,
    line: int,
    incoming_edge: dict[str, object] | None,
) -> list[dict[str, object]]:
    search_root = method_node or root_node
    call_node = _find_call_node(
        root_node=search_root,
        symbol=symbol,
        target_line=line,
    )
    if call_node is None:
        return []

    arg_index = None
    source_symbol = None
    if isinstance(incoming_edge, dict):
        arg_index = to_int((incoming_edge.get("props_json") or {}).get("argIndex"))
        source_symbol = _incoming_edge_source_symbol(path=path, edge=incoming_edge)

    if arg_index is not None:
        argument_range = _resolve_call_argument_range(
            source_bytes=source_bytes,
            call_node=call_node,
            arg_index=arg_index,
            source_symbol=source_symbol,
        )
        if argument_range:
            return argument_range

    name_node = call_node.child_by_field_name("name")
    if name_node is None:
        name_node = call_node.child_by_field_name("type")
    if name_node is not None:
        return [
            _range_from_node(
                source_bytes=source_bytes,
                node=name_node,
                kind="call",
                confidence="high",
            )
        ]
    return [
        _range_from_node(
            source_bytes=source_bytes, node=call_node, kind="call", confidence="medium"
        )
    ]


def _resolve_parameter_range(
    *,
    source_bytes: bytes,
    method_node: Any | None,
    symbol: str,
    param_index: int | None,
    target_line: int,
) -> dict[str, object] | None:
    if method_node is None:
        return None
    parameters = method_node.child_by_field_name("parameters")
    if parameters is None:
        return None
    named_params = list(parameters.named_children)
    candidate_indexes: list[int] = []
    if param_index is not None:
        for candidate in (param_index - 1, param_index):
            if candidate < 0 or candidate >= len(named_params):
                continue
            if candidate not in candidate_indexes:
                candidate_indexes.append(candidate)
    for candidate in candidate_indexes:
        name_node = _parameter_name_node(named_params[candidate])
        if name_node is None:
            continue
        node_text = _node_text(name_node)
        if node_text != symbol:
            continue
        return _range_from_node(
            source_bytes=source_bytes,
            node=name_node,
            kind="param",
            confidence="high",
        )
    for param in named_params:
        name_node = _parameter_name_node(param)
        if name_node is None:
            continue
        node_text = _node_text(name_node)
        if node_text == symbol and name_node.start_point[0] + 1 == target_line:
            return _range_from_node(
                source_bytes=source_bytes,
                node=name_node,
                kind="param",
                confidence="high",
            )
    return None


def _parameter_name_node(param_node: Any) -> Any | None:
    name_node = param_node.child_by_field_name("name")
    if name_node is not None:
        return name_node
    for child in param_node.named_children:
        if child.type in {"identifier", "variable_declarator_id"}:
            return child
    return None


def _resolve_identifier_range(
    *,
    source_bytes: bytes,
    root_node: Any,
    symbol: str,
    target_line: int,
    prefer_declaration: bool,
) -> dict[str, object] | None:
    best_node = None
    best_score: tuple[int, int, int] | None = None
    for node in _iter_named_nodes(root_node):
        if node.type not in {"identifier", "field_identifier"}:
            continue
        if _node_text(node) != symbol:
            continue
        start_line = node.start_point[0] + 1
        if abs(start_line - target_line) > 3:
            continue
        parent_type = node.parent.type if node.parent is not None else ""
        score = (
            3
            if start_line == target_line
            else max(0, 2 - abs(start_line - target_line)),
            2
            if prefer_declaration
            and parent_type in {"formal_parameter", "variable_declarator"}
            else 0,
            -node.start_point[1],
        )
        if best_score is None or score > best_score:
            best_score = score
            best_node = node
    if best_node is None:
        return None
    return _range_from_node(
        source_bytes=source_bytes, node=best_node, kind="identifier", confidence="high"
    )


def _find_call_node(
    *, root_node: Any, symbol: str | None, target_line: int
) -> Any | None:
    candidates: list[tuple[tuple[int, int], Any]] = []
    normalized_symbol = (symbol or "").strip()
    for node in _iter_named_nodes(root_node):
        if node.type not in {"method_invocation", "object_creation_expression"}:
            continue
        node_line_start = node.start_point[0] + 1
        node_line_end = node.end_point[0] + 1
        if not (node_line_start <= target_line <= node_line_end):
            continue
        name_node = node.child_by_field_name("name") or node.child_by_field_name("type")
        name_text = _node_text(name_node) if name_node is not None else None
        if normalized_symbol and name_text and name_text != normalized_symbol:
            continue
        distance = abs(node_line_start - target_line)
        candidates.append(((distance, node.start_point[1]), node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _resolve_call_argument_range(
    *, source_bytes: bytes, call_node: Any, arg_index: int, source_symbol: str | None
) -> list[dict[str, object]]:
    if arg_index == -1:
        receiver_node = call_node.child_by_field_name("object")
        if receiver_node is None:
            return []
        return _split_node_range(
            source_bytes=source_bytes,
            node=receiver_node,
            kind="receiver",
            confidence="high",
        )
    arguments = call_node.child_by_field_name("arguments")
    if arguments is None:
        return []
    named_arguments = list(arguments.named_children)
    candidate_indexes: list[int] = []
    for candidate in (arg_index - 1, arg_index):
        if candidate < 0 or candidate >= len(named_arguments):
            continue
        if candidate not in candidate_indexes:
            candidate_indexes.append(candidate)

    normalized_source_symbol = (source_symbol or "").strip()
    for candidate in candidate_indexes:
        arg_node = named_arguments[candidate]
        if normalized_source_symbol:
            arg_text = _node_text(arg_node) or ""
            if normalized_source_symbol not in arg_text:
                continue
        return _split_node_range(
            source_bytes=source_bytes,
            node=arg_node,
            kind="argument",
            confidence="high",
        )

    if normalized_source_symbol:
        for arg_node in named_arguments:
            arg_text = _node_text(arg_node) or ""
            if normalized_source_symbol in arg_text:
                return _split_node_range(
                    source_bytes=source_bytes,
                    node=arg_node,
                    kind="argument",
                    confidence="medium",
                )
    return []


def _find_incoming_edge(
    *, path: dict[str, object], step: dict[str, object]
) -> dict[str, object] | None:
    edges = path.get("edges") if isinstance(path.get("edges"), list) else []
    step_id = to_int(step.get("step_id"))
    node_ref = to_text(step.get("node_ref"))
    best_edge = None
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        to_step_id = to_int(edge.get("to_step_id")) or to_int(edge.get("to_node_id"))
        to_node_ref = to_text(edge.get("to_node_ref"))
        if step_id is not None and to_step_id == step_id:
            best_edge = edge
        elif node_ref and to_node_ref == node_ref:
            best_edge = edge
        if best_edge is not None:
            props = (
                best_edge.get("props_json")
                if isinstance(best_edge.get("props_json"), dict)
                else {}
            )
            if "argIndex" in props:
                return best_edge
    return best_edge


def _incoming_edge_source_symbol(
    *, path: dict[str, object], edge: dict[str, object]
) -> str | None:
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    from_step_id = to_int(edge.get("from_step_id")) or to_int(edge.get("from_node_id"))
    from_node_ref = to_text(edge.get("from_node_ref"))
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if from_step_id is not None and to_int(node.get("node_id")) == from_step_id:
            return _primary_symbol(step=node, node=node)
        if from_node_ref and to_text(node.get("node_ref")) == from_node_ref:
            return _primary_symbol(step=node, node=node)
    return None


def _split_node_range(
    *, source_bytes: bytes, node: Any, kind: str, confidence: str
) -> list[dict[str, object]]:
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    start_col = node.start_point[1] + 1
    end_col_exclusive = node.end_point[1]
    node_text = source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )
    ranges: list[dict[str, object]] = []
    for line_no in range(start_line, end_line + 1):
        line_text = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
        if line_no == start_line:
            seg_start = max(1, start_col)
        else:
            seg_start = 1
        if line_no == end_line:
            seg_end = max(seg_start, end_col_exclusive)
        else:
            seg_end = max(seg_start, len(line_text))
        ranges.append(
            {
                "start_line": line_no,
                "start_column": seg_start,
                "end_line": line_no,
                "end_column": seg_end,
                "text": node_text.strip() or None,
                "kind": kind,
                "confidence": confidence,
            }
        )
    return ranges


def _range_from_node(
    *, source_bytes: bytes, node: Any, kind: str, confidence: str
) -> dict[str, object]:
    return _split_node_range(
        source_bytes=source_bytes,
        node=node,
        kind=kind,
        confidence=confidence,
    )[0]


def _line_fallback_range(
    *,
    version_id: uuid.UUID,
    file_path: str,
    line: int,
    step: dict[str, object],
    node: dict[str, object] | None,
) -> dict[str, object] | None:
    source_bytes = _normalized_source_bytes(version_id=version_id, file_path=file_path)
    if source_bytes is None:
        return None
    symbol = _primary_symbol(step=step, node=node)
    if symbol:
        token_range = _line_symbol_fallback(
            source_bytes=source_bytes,
            file_path=file_path,
            line=line,
            symbol=symbol,
        )
        if token_range is not None:
            return token_range
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    if line <= 0 or line > len(lines):
        return None
    line_text = lines[line - 1]
    return {
        "start_line": line,
        "start_column": 1,
        "end_line": line,
        "end_column": max(1, len(line_text)),
        "text": line_text.strip() or None,
        "kind": "line",
        "confidence": "low",
    }


def _line_fallback_range_from_bytes(
    *, source_bytes: bytes, line: int, symbol: str | None
) -> dict[str, object] | None:
    if symbol:
        token_range = _line_symbol_fallback(
            source_bytes=source_bytes,
            file_path="",
            line=line,
            symbol=symbol,
        )
        if token_range is not None:
            return token_range
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    if line <= 0 or line > len(lines):
        return None
    line_text = lines[line - 1]
    return {
        "start_line": line,
        "start_column": 1,
        "end_line": line,
        "end_column": max(1, len(line_text)),
        "text": line_text.strip() or None,
        "kind": "line",
        "confidence": "low",
    }


def _line_symbol_fallback(
    *, source_bytes: bytes, file_path: str, line: int, symbol: str
) -> dict[str, object] | None:
    del file_path
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    if line <= 0 or line > len(lines):
        return None
    line_text = lines[line - 1]
    index = line_text.find(symbol)
    if index < 0:
        return None
    return {
        "start_line": line,
        "start_column": index + 1,
        "end_line": line,
        "end_column": index + len(symbol),
        "text": symbol,
        "kind": "token",
        "confidence": "medium",
    }


def _primary_symbol(
    *, step: dict[str, object], node: dict[str, object] | None
) -> str | None:
    if isinstance(node, dict):
        raw_props = (
            node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
        )
        for candidate in (
            raw_props.get("name"),
            node.get("symbol_name"),
            node.get("display_name"),
            raw_props.get("selector"),
            raw_props.get("method"),
        ):
            text = to_text(candidate)
            if text:
                return text
    for candidate in (
        step.get("symbol_name"),
        step.get("display_name"),
        step.get("func_name"),
    ):
        text = to_text(candidate)
        if text:
            return text
    return None


def _node_ref_focus_symbol(node_ref: str | None) -> str | None:
    if not node_ref:
        return None
    parts = [part for part in str(node_ref).split("|") if part]
    if not parts:
        return None
    tail = parts[-1]
    return tail.strip() or None


def _resolve_pom_dependency_ranges(
    *, source_bytes: bytes, line: int, node_ref: str | None
) -> list[dict[str, object]]:
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    if line <= 0 or line > len(lines):
        return []
    dependency_start = None
    for index in range(line - 1, max(-1, line - 15), -1):
        if "<dependency>" in lines[index]:
            dependency_start = index
            break
    if dependency_start is None:
        dependency_start = line - 1
    dependency_end = None
    for index in range(dependency_start, min(len(lines), dependency_start + 20)):
        if "</dependency>" in lines[index]:
            dependency_end = index
            break
    if dependency_end is None:
        dependency_end = min(len(lines) - 1, dependency_start + 10)

    coordinates = _parse_pom_coordinates(node_ref)
    artifact = coordinates.get("artifact")
    version = coordinates.get("version")
    ranges: list[dict[str, object]] = []
    artifact_line = _find_xml_value_range(
        lines=lines,
        start_index=dependency_start,
        end_index=dependency_end,
        tag="artifactId",
        expected_value=artifact,
        kind="component",
    )
    if artifact_line is not None:
        ranges.append(artifact_line)
    version_line = _find_xml_value_range(
        lines=lines,
        start_index=dependency_start,
        end_index=dependency_end,
        tag="version",
        expected_value=version,
        kind="version",
    )
    if version_line is not None:
        ranges.append(version_line)
    return ranges


def _parse_pom_coordinates(node_ref: str | None) -> dict[str, str | None]:
    tail = _node_ref_focus_symbol(node_ref)
    if not tail:
        return {"group": None, "artifact": None, "version": None}
    segments = tail.split(":")
    if len(segments) >= 3:
        return {
            "group": ":".join(segments[:-2]) or None,
            "artifact": segments[-2] or None,
            "version": segments[-1] or None,
        }
    return {"group": None, "artifact": tail or None, "version": None}


def _find_xml_value_range(
    *,
    lines: list[str],
    start_index: int,
    end_index: int,
    tag: str,
    expected_value: str | None,
    kind: str,
) -> dict[str, object] | None:
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    for index in range(start_index, end_index + 1):
        line = lines[index]
        open_index = line.find(open_tag)
        close_index = line.find(close_tag)
        if open_index < 0 or close_index < 0 or close_index <= open_index:
            continue
        value_start = open_index + len(open_tag)
        value = line[value_start:close_index].strip()
        if expected_value and value != expected_value:
            continue
        raw_value_start = line.find(value, value_start, close_index)
        if raw_value_start < 0:
            raw_value_start = value_start
        return {
            "start_line": index + 1,
            "start_column": raw_value_start + 1,
            "end_line": index + 1,
            "end_column": raw_value_start + len(value),
            "text": value or None,
            "kind": kind,
            "confidence": "high" if expected_value else "medium",
        }
    return None


def _resolve_properties_key_value_ranges(
    *, source_bytes: bytes, line: int, node_ref: str | None, rule_key: str
) -> list[dict[str, object]]:
    lines = source_bytes.decode("utf-8", errors="replace").splitlines()
    if line <= 0 or line > len(lines):
        return []
    line_text = lines[line - 1]
    key = _node_ref_focus_symbol(node_ref)
    if not key:
        return []
    equals_index = line_text.find("=")
    if equals_index < 0:
        return []
    key_index = line_text.find(key)
    value = line_text[equals_index + 1 :].strip()
    ranges: list[dict[str, object]] = []
    if key_index >= 0:
        ranges.append(
            {
                "start_line": line,
                "start_column": key_index + 1,
                "end_line": line,
                "end_column": key_index + len(key),
                "text": key,
                "kind": "config-key",
                "confidence": "high",
            }
        )
    if value:
        raw_value_index = line_text.find(value, equals_index + 1)
        if raw_value_index >= 0:
            kind = "secret-value" if "secret" in rule_key else "config-value"
            ranges.append(
                {
                    "start_line": line,
                    "start_column": raw_value_index + 1,
                    "end_line": line,
                    "end_column": raw_value_index + len(value),
                    "text": value,
                    "kind": kind,
                    "confidence": "high",
                }
            )
    return ranges


def _normalized_source_bytes(*, version_id: uuid.UUID, file_path: str) -> bytes | None:
    payload = _read_file_text(version_id=version_id, file_path=file_path)
    if payload is None:
        return None
    text = payload.decode("utf-8", errors="replace")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.encode("utf-8")


def _node_text(node: Any) -> str | None:
    if node is None:
        return None
    try:
        return node.text.decode("utf-8", errors="replace")
    except Exception:
        return None


def _iter_named_nodes(node: Any):
    yield node
    for child in getattr(node, "named_children", []) or []:
        yield from _iter_named_nodes(child)
