from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.path_graph_service import (
    build_path_edge_payload,
    to_text,
    trim_code_snippet,
)

try:
    from tree_sitter import Language, Node, Parser
    import tree_sitter_java as _tree_sitter_java
except Exception:  # pragma: no cover - optional dependency fail-open
    Language = None
    Node = Any
    Parser = None
    _tree_sitter_java = None


@dataclass(slots=True)
class JavaMethodFact:
    file_path: str
    method_name: str
    param_names: list[str]
    decl_line: int
    start_line: int
    end_line: int
    body: Any | None


@dataclass(slots=True)
class JavaCallFact:
    line: int
    name: str
    arg_names: list[set[str]]
    receiver_names: set[str]
    code: str | None
    kind: str


@dataclass(slots=True)
class JavaAssignFact:
    line: int
    target: str
    input_names: set[str]
    code: str | None


@dataclass(slots=True)
class JavaTracePath:
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]


def repair_java_path(
    *,
    version_id: uuid.UUID,
    candidate_path: dict[str, object],
    source_node: dict[str, object],
    sink_node: dict[str, object],
) -> dict[str, object] | None:
    parser = _build_parser()
    if parser is None:
        return None

    source_file = to_text(source_node.get("file"))
    sink_file = to_text(sink_node.get("file")) or source_file
    source_line = _safe_line(source_node.get("line"))
    sink_line = _safe_line(sink_node.get("line"))
    if not source_file or source_line is None or not sink_file or sink_line is None:
        return None

    source_method = _find_method(
        version_id=version_id, file_path=source_file, line=source_line
    )
    if source_method is None:
        return None

    sink_method = _find_method(
        version_id=version_id, file_path=sink_file, line=sink_line
    )
    source_symbol = _infer_source_symbol(source_node=source_node, method=source_method)
    if not source_symbol:
        return None

    sink_name = (
        to_text(sink_node.get("display_name"))
        or to_text(sink_node.get("symbol_name"))
        or to_text(sink_node.get("func_name"))
    )
    traced = _trace_method_path(
        version_id=version_id,
        method=source_method,
        source_symbol=source_symbol,
        source_line=source_line,
        sink_file=sink_file,
        sink_line=sink_line,
        sink_name=sink_name,
        sink_method=sink_method,
        depth=0,
    )
    if traced is None:
        return None

    return {
        "path_id": to_int(candidate_path.get("path_id")) or 0,
        "path_length": max(0, len(traced.edges)),
        "nodes": traced.nodes,
        "steps": [
            {
                "step_id": int(node.get("node_id") or 0),
                "labels": [
                    str(item)
                    for item in node.get("labels") or []
                    if isinstance(item, str) and item.strip()
                ],
                "file": node.get("file"),
                "line": node.get("line"),
                "column": node.get("column"),
                "func_name": node.get("func_name"),
                "display_name": node.get("display_name"),
                "symbol_name": node.get("symbol_name"),
                "owner_method": node.get("owner_method"),
                "type_name": node.get("type_name"),
                "node_kind": node.get("node_kind"),
                "code_snippet": node.get("code_snippet"),
                "node_ref": node.get("node_ref"),
            }
            for node in traced.nodes
        ],
        "edges": traced.edges,
    }


def _trace_method_path(
    *,
    version_id: uuid.UUID,
    method: JavaMethodFact,
    source_symbol: str,
    source_line: int,
    sink_file: str,
    sink_line: int,
    sink_name: str | None,
    sink_method: JavaMethodFact | None,
    depth: int,
) -> JavaTracePath | None:
    if depth > 2:
        return None

    root_node = _read_file_root(version_id=version_id, file_path=method.file_path)
    if root_node is None:
        return None
    method_node = _find_method_node(root_node=root_node, method=method)
    if method_node is None:
        return None

    body = method_node.child_by_field_name("body")
    if body is None:
        return None

    source_node = _build_var_node(
        file_path=method.file_path,
        line=max(source_line, method.decl_line),
        symbol=source_symbol,
        method_name=method.method_name,
        labels=["Var", "Param" if source_symbol in method.param_names else "Reference"],
        code=_read_line(
            version_id=version_id,
            file_path=method.file_path,
            line=max(source_line, method.decl_line),
        ),
    )
    chains: dict[str, JavaTracePath] = {
        source_symbol: JavaTracePath(nodes=[source_node], edges=[])
    }
    last_tainted_call: JavaTracePath | None = None

    for fact in _collect_method_facts(
        version_id=version_id, file_path=method.file_path, body=body
    ):
        if fact.line < source_line:
            continue
        if isinstance(fact, JavaAssignFact):
            predecessor = _pick_predecessor(chains=chains, inputs=fact.input_names)
            if predecessor is None:
                continue
            base = chains[predecessor]
            target_node = _build_var_node(
                file_path=method.file_path,
                line=fact.line,
                symbol=fact.target,
                method_name=method.method_name,
                labels=["Var", "Identifier"],
                code=fact.code,
            )
            chains[fact.target] = _append_node_to_path(
                base_path=base,
                node=target_node,
                edge_type="SRC_FLOW",
                props={"kind": "assign"},
            )
            continue

        if not isinstance(fact, JavaCallFact):
            continue
        tainted_predecessor, arg_index = _pick_tainted_call_arg(
            chains=chains, call=fact
        )
        if tainted_predecessor is None or arg_index is None:
            continue
        base = chains[tainted_predecessor]
        call_node = _build_call_node(
            file_path=method.file_path,
            line=fact.line,
            call_name=fact.name,
            method_name=method.method_name,
            code=fact.code,
        )
        tainted_call_path = _append_node_to_path(
            base_path=base,
            node=call_node,
            edge_type="ARG",
            props={"argIndex": arg_index, "kind": fact.kind},
        )
        last_tainted_call = tainted_call_path
        if _call_matches_sink(
            call=fact,
            method=method,
            sink_file=sink_file,
            sink_line=sink_line,
            sink_name=sink_name,
        ):
            return tainted_call_path
        if sink_method is None or sink_method.file_path == method.file_path:
            continue
        if not _call_can_bridge(call=fact, sink_method=sink_method):
            continue
        if arg_index >= len(sink_method.param_names):
            continue
        callee_param = sink_method.param_names[arg_index]
        callee_path = _trace_method_path(
            version_id=version_id,
            method=sink_method,
            source_symbol=callee_param,
            source_line=sink_method.decl_line,
            sink_file=sink_file,
            sink_line=sink_line,
            sink_name=sink_name,
            sink_method=sink_method,
            depth=depth + 1,
        )
        if callee_path is None or not callee_path.nodes:
            continue
        return _join_call_and_callee(
            caller_path=tainted_call_path,
            callee_path=callee_path,
            arg_index=arg_index,
        )

    if sink_method is None or sink_method.file_path != method.file_path:
        return last_tainted_call
    return last_tainted_call if last_tainted_call and sink_line >= source_line else None


def _join_call_and_callee(
    *, caller_path: JavaTracePath, callee_path: JavaTracePath, arg_index: int
) -> JavaTracePath:
    caller_nodes = [dict(node) for node in caller_path.nodes]
    caller_edges = [dict(edge) for edge in caller_path.edges]
    node_offset = len(caller_nodes)
    callee_nodes = []
    for index, node in enumerate(callee_path.nodes):
        copied = dict(node)
        copied["node_id"] = node_offset + index
        callee_nodes.append(copied)
    callee_edges = []
    for edge in callee_path.edges:
        copied = dict(edge)
        if to_int(copied.get("from_node_id")) is not None:
            copied["from_node_id"] = node_offset + int(copied["from_node_id"])
            copied["from_step_id"] = copied["from_node_id"]
        if to_int(copied.get("to_node_id")) is not None:
            copied["to_node_id"] = node_offset + int(copied["to_node_id"])
            copied["to_step_id"] = copied["to_node_id"]
        copied["edge_id"] = len(caller_edges) + len(callee_edges)
        copied["edge_order"] = copied["edge_id"]
        callee_edges.append(copied)
    bridge_edge = build_path_edge_payload(
        index=len(caller_edges),
        edge_type="PARAM_PASS",
        from_node_id=to_int(caller_nodes[-1].get("node_id")),
        to_node_id=to_int(callee_nodes[0].get("node_id")) if callee_nodes else None,
        from_node_ref=to_text(caller_nodes[-1].get("node_ref")),
        to_node_ref=to_text(callee_nodes[0].get("node_ref")) if callee_nodes else None,
        props={"argIndex": arg_index, "kind": "java_param_bridge"},
    )
    return JavaTracePath(
        nodes=caller_nodes + callee_nodes,
        edges=caller_edges + [bridge_edge] + callee_edges,
    )


def _append_node_to_path(
    *,
    base_path: JavaTracePath,
    node: dict[str, object],
    edge_type: str,
    props: dict[str, object],
) -> JavaTracePath:
    nodes = [dict(item) for item in base_path.nodes]
    edges = [dict(item) for item in base_path.edges]
    copied_node = dict(node)
    copied_node["node_id"] = len(nodes)
    previous = nodes[-1]
    nodes.append(copied_node)
    edges.append(
        build_path_edge_payload(
            index=len(edges),
            edge_type=edge_type,
            from_node_id=to_int(previous.get("node_id")),
            to_node_id=to_int(copied_node.get("node_id")),
            from_node_ref=to_text(previous.get("node_ref")),
            to_node_ref=to_text(copied_node.get("node_ref")),
            props=props,
        )
    )
    return JavaTracePath(nodes=nodes, edges=edges)


def _call_matches_sink(
    *,
    call: JavaCallFact,
    method: JavaMethodFact,
    sink_file: str,
    sink_line: int,
    sink_name: str | None,
) -> bool:
    if method.file_path != sink_file:
        return False
    if call.line == sink_line:
        return True
    normalized_sink_name = str(sink_name or "").strip()
    if (
        normalized_sink_name
        and call.name == normalized_sink_name
        and abs(call.line - sink_line) <= 1
    ):
        return True
    return False


def _call_can_bridge(*, call: JavaCallFact, sink_method: JavaMethodFact) -> bool:
    if call.name != sink_method.method_name:
        return False
    return len(call.arg_names) == len(sink_method.param_names)


def _pick_predecessor(
    *, chains: dict[str, JavaTracePath], inputs: set[str]
) -> str | None:
    for name in sorted(inputs):
        if name in chains:
            return name
    return None


def _pick_tainted_call_arg(
    *, chains: dict[str, JavaTracePath], call: JavaCallFact
) -> tuple[str | None, int | None]:
    for index, names in enumerate(call.arg_names):
        predecessor = _pick_predecessor(chains=chains, inputs=names)
        if predecessor is not None:
            return predecessor, index
    predecessor = _pick_predecessor(chains=chains, inputs=call.receiver_names)
    if predecessor is not None:
        return predecessor, -1
    return None, None


def _collect_method_facts(
    *, version_id: uuid.UUID, file_path: str, body: Node
) -> list[JavaAssignFact | JavaCallFact]:
    facts: list[JavaAssignFact | JavaCallFact] = []
    for node in _iter_named_nodes(body):
        if node.type == "local_variable_declaration":
            facts.extend(
                _build_local_var_facts(
                    version_id=version_id, file_path=file_path, node=node
                )
            )
            continue
        if node.type == "assignment_expression":
            fact = _build_assignment_fact(
                version_id=version_id, file_path=file_path, node=node
            )
            if fact is not None:
                facts.append(fact)
            continue
        if node.type == "method_invocation":
            fact = _build_call_fact(
                version_id=version_id, file_path=file_path, node=node, kind="call"
            )
            if fact is not None:
                facts.append(fact)
            continue
        if node.type == "object_creation_expression":
            fact = _build_call_fact(
                version_id=version_id, file_path=file_path, node=node, kind="new"
            )
            if fact is not None:
                facts.append(fact)
    facts.sort(key=lambda item: item.line)
    return facts


def _build_local_var_facts(
    *, version_id: uuid.UUID, file_path: str, node: Node
) -> list[JavaAssignFact]:
    facts: list[JavaAssignFact] = []
    for child in node.named_children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        value_node = child.child_by_field_name("value")
        target = _node_text(version_id=version_id, file_path=file_path, node=name_node)
        if not target or value_node is None:
            continue
        facts.append(
            JavaAssignFact(
                line=child.start_point[0] + 1,
                target=target,
                input_names=_extract_identifiers(
                    version_id=version_id, file_path=file_path, node=value_node
                ),
                code=_node_text(version_id=version_id, file_path=file_path, node=child),
            )
        )
    return facts


def _build_assignment_fact(
    *, version_id: uuid.UUID, file_path: str, node: Node
) -> JavaAssignFact | None:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    target = _extract_assignment_target(
        version_id=version_id, file_path=file_path, node=left
    )
    if not target or right is None:
        return None
    return JavaAssignFact(
        line=node.start_point[0] + 1,
        target=target,
        input_names=_extract_identifiers(
            version_id=version_id, file_path=file_path, node=right
        ),
        code=_node_text(version_id=version_id, file_path=file_path, node=node),
    )


def _build_call_fact(
    *, version_id: uuid.UUID, file_path: str, node: Node, kind: str
) -> JavaCallFact | None:
    if kind == "call":
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        receiver_node = node.child_by_field_name("object")
    else:
        name_node = node.child_by_field_name("type")
        args_node = node.child_by_field_name("arguments")
        receiver_node = None
    name = _node_text(version_id=version_id, file_path=file_path, node=name_node)
    if not name:
        return None
    arg_names = []
    if args_node is not None:
        for child in args_node.named_children:
            arg_names.append(
                _extract_identifiers(
                    version_id=version_id, file_path=file_path, node=child
                )
            )
    receiver_names = (
        _extract_identifiers(
            version_id=version_id, file_path=file_path, node=receiver_node
        )
        if receiver_node is not None
        else set()
    )
    return JavaCallFact(
        line=node.start_point[0] + 1,
        name=name,
        arg_names=arg_names,
        receiver_names=receiver_names,
        code=_node_text(version_id=version_id, file_path=file_path, node=node),
        kind=kind,
    )


def _extract_assignment_target(
    *, version_id: uuid.UUID, file_path: str, node: Node | None
) -> str | None:
    if node is None:
        return None
    if node.type == "identifier":
        return _node_text(version_id=version_id, file_path=file_path, node=node)
    if node.type == "field_access":
        field = node.child_by_field_name("field")
        return _node_text(version_id=version_id, file_path=file_path, node=field)
    names = _extract_identifiers(version_id=version_id, file_path=file_path, node=node)
    return next(iter(sorted(names)), None)


def _extract_identifiers(
    *, version_id: uuid.UUID, file_path: str, node: Node | None
) -> set[str]:
    if node is None:
        return set()
    names: set[str] = set()
    if node.type == "identifier":
        text = _node_text(version_id=version_id, file_path=file_path, node=node)
        if text:
            names.add(text)
        return names
    skip_name_field = node.type in {"method_invocation", "object_creation_expression"}
    skipped_child = node.child_by_field_name("name") if skip_name_field else None
    for child in node.named_children:
        if skipped_child is not None and child == skipped_child:
            continue
        names.update(
            _extract_identifiers(version_id=version_id, file_path=file_path, node=child)
        )
    return names


def _build_var_node(
    *,
    file_path: str,
    line: int,
    symbol: str,
    method_name: str,
    labels: list[str],
    code: str | None,
) -> dict[str, object]:
    return {
        "node_id": 0,
        "labels": labels,
        "file": file_path,
        "line": line,
        "column": None,
        "func_name": method_name,
        "display_name": symbol,
        "symbol_name": symbol,
        "owner_method": method_name,
        "type_name": None,
        "node_kind": "Var",
        "code_snippet": trim_code_snippet(code),
        "node_ref": f"java:{file_path}:{line}:var:{symbol}",
        "raw_props": {"name": symbol, "file": file_path, "line": line, "kind": "Var"},
    }


def _build_call_node(
    *, file_path: str, line: int, call_name: str, method_name: str, code: str | None
) -> dict[str, object]:
    return {
        "node_id": 0,
        "labels": ["Call"],
        "file": file_path,
        "line": line,
        "column": None,
        "func_name": method_name,
        "display_name": call_name,
        "symbol_name": call_name,
        "owner_method": method_name,
        "type_name": None,
        "node_kind": "Call",
        "code_snippet": trim_code_snippet(code),
        "node_ref": f"java:{file_path}:{line}:call:{call_name}",
        "raw_props": {
            "name": call_name,
            "file": file_path,
            "line": line,
            "kind": "Call",
        },
    }


def _infer_source_symbol(
    *, source_node: dict[str, object], method: JavaMethodFact
) -> str | None:
    for candidate in (
        source_node.get("symbol_name"),
        source_node.get("display_name"),
        source_node.get("node_ref"),
    ):
        text = to_text(candidate)
        if not text:
            continue
        if text in method.param_names:
            return text
        if "|" not in text and ":" not in text:
            return text
    raw_props = (
        source_node.get("raw_props")
        if isinstance(source_node.get("raw_props"), dict)
        else {}
    )
    text = to_text(raw_props.get("name"))
    if text:
        return text
    return None


def _find_method(
    *, version_id: uuid.UUID, file_path: str, line: int
) -> JavaMethodFact | None:
    parsed = _load_parsed_java_file(version_id=version_id, file_path=file_path)
    if parsed is None:
        return None
    for method in parsed[1]:
        if method.decl_line <= line <= method.end_line:
            return method
    return None


def _find_method_node(*, root_node: Node, method: JavaMethodFact) -> Node | None:
    for node in _iter_named_nodes(root_node):
        if node.type not in {"method_declaration", "constructor_declaration"}:
            continue
        name = _method_name_from_node(node)
        if name != method.method_name:
            continue
        if node.start_point[0] + 1 != method.decl_line:
            continue
        return node
    return None


def _read_file_root(*, version_id: uuid.UUID, file_path: str) -> Node | None:
    parsed = _load_parsed_java_file(version_id=version_id, file_path=file_path)
    if parsed is None:
        return None
    return parsed[0]


def _load_parsed_java_file(
    *, version_id: uuid.UUID, file_path: str
) -> tuple[Node, list[JavaMethodFact]] | None:
    return _load_parsed_java_file_cached(str(version_id), file_path)


@lru_cache(maxsize=256)
def _load_parsed_java_file_cached(
    version_id_text: str, file_path: str
) -> tuple[Node, list[JavaMethodFact]] | None:
    parser = _build_parser()
    if parser is None:
        return None
    absolute_file = (
        _snapshot_source_root(version_id=uuid.UUID(version_id_text)) / file_path
    )
    if not absolute_file.exists() or not absolute_file.is_file():
        return None
    try:
        source = absolute_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    methods = _extract_methods(
        version_id=uuid.UUID(version_id_text), file_path=file_path, root=root
    )
    return root, methods


def _extract_methods(
    *, version_id: uuid.UUID, file_path: str, root: Node
) -> list[JavaMethodFact]:
    methods: list[JavaMethodFact] = []
    for node in _iter_named_nodes(root):
        if node.type not in {"method_declaration", "constructor_declaration"}:
            continue
        method_name = _method_name_from_node(node)
        if not method_name:
            continue
        params = _parameter_names(version_id=version_id, file_path=file_path, node=node)
        body = node.child_by_field_name("body")
        start_line = (
            (body.start_point[0] + 1) if body is not None else (node.start_point[0] + 1)
        )
        end_line = (
            (body.end_point[0] + 1) if body is not None else (node.end_point[0] + 1)
        )
        methods.append(
            JavaMethodFact(
                file_path=file_path,
                method_name=method_name,
                param_names=params,
                decl_line=node.start_point[0] + 1,
                start_line=start_line,
                end_line=end_line,
                body=body,
            )
        )
    return methods


def _parameter_names(*, version_id: uuid.UUID, file_path: str, node: Node) -> list[str]:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return []
    names: list[str] = []
    for child in parameters.named_children:
        name_node = child.child_by_field_name("name")
        name = _node_text(version_id=version_id, file_path=file_path, node=name_node)
        if name:
            names.append(name)
    return names


def _method_name_from_node(node: Node) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    text = to_text(name_node.text.decode("utf-8", errors="replace"))
    return text


def _node_text(
    *, version_id: uuid.UUID, file_path: str, node: Node | None
) -> str | None:
    if node is None:
        return None
    source = _read_file_text(version_id=version_id, file_path=file_path)
    if source is None:
        return None
    return trim_code_snippet(
        source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    )


@lru_cache(maxsize=256)
def _read_file_text(version_id: uuid.UUID, file_path: str) -> bytes | None:
    absolute_file = _snapshot_source_root(version_id=version_id) / file_path
    if not absolute_file.exists() or not absolute_file.is_file():
        return None
    try:
        return absolute_file.read_bytes()
    except OSError:
        return None


def _read_line(*, version_id: uuid.UUID, file_path: str, line: int) -> str | None:
    payload = _read_file_text(version_id=version_id, file_path=file_path)
    if payload is None:
        return None
    try:
        lines = payload.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return None
    if line <= 0 or line > len(lines):
        return None
    return trim_code_snippet(lines[line - 1])


def _iter_named_nodes(node: Node):
    yield node
    for child in node.named_children:
        yield from _iter_named_nodes(child)


@lru_cache(maxsize=1)
def _build_parser() -> Parser | None:
    if Parser is None or Language is None or _tree_sitter_java is None:
        return None
    language = Language(_tree_sitter_java.language())
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        parser.language = language
        return parser


def _snapshot_source_root(*, version_id: uuid.UUID) -> Path:
    normalized = Path(os.path.normpath(str(get_settings().snapshot_storage_root)))
    if not normalized.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        normalized = backend_root / normalized
    return normalized / str(version_id) / "source"


def _safe_line(value: object) -> int | None:
    return to_int(value)


def to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
