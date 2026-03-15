from __future__ import annotations

import hashlib
import uuid
from typing import Any

from app.models import Job
from app.services.java_trace_parser_service import repair_java_path
from app.services.path_graph_service import (
    collect_path_labels,
    extract_path_node_ref,
    normalize_path_graph,
    path_edge_types,
    path_has_semantic_signal,
    select_path_anchor_pair,
    to_int,
    to_text,
)
from app.services.source_location_service import normalize_graph_location


LOW_VALUE_CALL_NAMES = frozenset(
    {
        "equals",
        "equalsignorecase",
        "contains",
        "startswith",
        "endswith",
        "isempty",
        "isblank",
        "matches",
        "compareto",
        "compare",
        "hashcode",
        "tostring",
        "length",
        "size",
        "get",
        "put",
        "set",
        "add",
        "remove",
        "iterator",
        "next",
        "hasnext",
        "info",
        "debug",
        "warn",
        "error",
        "trace",
        "println",
        "print",
        "format",
        "valueof",
    }
)


def normalize_external_finding_candidate(
    *, version_id: uuid.UUID, raw_finding: dict[str, object]
) -> dict[str, object]:
    normalized = dict(raw_finding)
    normalized_paths: list[dict[str, object]] = []
    raw_paths = (
        raw_finding.get("paths") if isinstance(raw_finding.get("paths"), list) else []
    )
    for path_index, path_item in enumerate(raw_paths):
        if not isinstance(path_item, dict):
            continue
        normalized_path = normalize_path_graph(
            version_id=version_id,
            path_item=path_item,
            path_index=path_index,
        )
        if normalized_path is not None:
            normalized_paths.append(normalized_path)

    normalized_source_file, normalized_source_line = normalize_graph_location(
        version_id=version_id,
        file_path=to_text(raw_finding.get("source_file")),
        line=raw_finding.get("source_line"),
    )
    normalized_sink_file, normalized_sink_line = normalize_graph_location(
        version_id=version_id,
        file_path=to_text(raw_finding.get("sink_file")),
        line=raw_finding.get("sink_line"),
    )
    normalized_file_path, normalized_line_start = normalize_graph_location(
        version_id=version_id,
        file_path=to_text(raw_finding.get("file_path")),
        line=raw_finding.get("line_start"),
    )

    source_node, sink_node = _select_primary_anchors(normalized_paths)
    if source_node is not None:
        normalized_source_file = normalized_source_file or to_text(
            source_node.get("file")
        )
        normalized_source_line = normalized_source_line or to_int(
            source_node.get("line")
        )
    if sink_node is not None:
        normalized_sink_file = normalized_sink_file or to_text(sink_node.get("file"))
        normalized_sink_line = normalized_sink_line or to_int(sink_node.get("line"))

    normalized_file_path = (
        normalized_file_path or normalized_sink_file or normalized_source_file
    )
    normalized_line_start = (
        normalized_line_start or normalized_sink_line or normalized_source_line
    )
    normalized.update(
        {
            "file_path": normalized_file_path,
            "line_start": normalized_line_start,
            "line_end": normalized_line_start,
            "source_file": normalized_source_file,
            "source_line": normalized_source_line,
            "sink_file": normalized_sink_file,
            "sink_line": normalized_sink_line,
            "paths": normalized_paths,
            "has_path": bool(normalized_paths),
            "path_length": (
                to_int(normalized_paths[0].get("path_length"))
                if normalized_paths
                else None
            ),
        }
    )
    return normalized


def process_external_finding_candidate(
    *,
    job: Job,
    raw_finding: dict[str, object],
    seen_fingerprints: set[str] | None = None,
) -> dict[str, object] | None:
    normalized = normalize_external_finding_candidate(
        version_id=job.version_id,
        raw_finding=raw_finding,
    )
    repaired = repair_external_finding_candidate(job=job, finding_payload=normalized)
    evidence = (
        repaired.get("evidence") if isinstance(repaired.get("evidence"), dict) else {}
    )
    canonical_fingerprint = to_text(evidence.get("canonical_fingerprint"))
    if seen_fingerprints is not None and canonical_fingerprint:
        if canonical_fingerprint in seen_fingerprints:
            return None
        seen_fingerprints.add(canonical_fingerprint)
    return repaired


def repair_external_finding_candidate(
    *, job: Job, finding_payload: dict[str, object]
) -> dict[str, object]:
    paths = (
        finding_payload.get("paths")
        if isinstance(finding_payload.get("paths"), list)
        else []
    )
    if not paths:
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=None,
            sink_node=None,
            repair_status="node_only",
        )

    primary_path = paths[0] if isinstance(paths[0], dict) else None
    if primary_path is None:
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=None,
            sink_node=None,
            repair_status="empty_path",
        )

    source_node, sink_node = select_path_anchor_pair(primary_path)
    if source_node is None or sink_node is None:
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=source_node,
            sink_node=sink_node,
            repair_status="missing_anchor",
        )

    final_paths = paths
    repair_status = "normalized"
    primary_score = _path_quality_score(
        primary_path,
        source_node=source_node,
        sink_node=sink_node,
    )
    needs_java_promotion = (
        not path_has_semantic_signal(paths)
    ) or _needs_java_promotion(
        primary_path,
        source_node=source_node,
        sink_node=sink_node,
    )
    if needs_java_promotion:
        repaired_path = repair_java_path(
            version_id=job.version_id,
            candidate_path=primary_path,
            source_node=source_node,
            sink_node=sink_node,
        )
        if repaired_path is not None:
            repaired_source, repaired_sink = select_path_anchor_pair(repaired_path)
            repaired_score = _path_quality_score(
                repaired_path,
                source_node=repaired_source,
                sink_node=repaired_sink,
            )
            if (not path_has_semantic_signal(paths)) or repaired_score > primary_score:
                final_paths = [repaired_path]
                source_node, sink_node = repaired_source, repaired_sink
                repair_status = "java_repaired"
        if not path_has_semantic_signal(paths) and repair_status != "java_repaired":
            return _finalize_without_path(
                finding_payload=finding_payload,
                source_node=source_node,
                sink_node=sink_node,
                repair_status="downgraded_no_path",
            )

    primary_path = (
        final_paths[0] if final_paths and isinstance(final_paths[0], dict) else None
    )
    if primary_path is None:
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=source_node,
            sink_node=sink_node,
            repair_status="downgraded_no_path",
        )
    source_node, sink_node = select_path_anchor_pair(primary_path)
    if source_node is None or sink_node is None:
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=source_node,
            sink_node=sink_node,
            repair_status="missing_anchor",
        )
    if not _path_is_actionable(
        primary_path, source_node=source_node, sink_node=sink_node
    ):
        return _finalize_without_path(
            finding_payload=finding_payload,
            source_node=source_node,
            sink_node=sink_node,
            repair_status="downgraded_no_path",
        )

    return _finalize_with_path(
        finding_payload=finding_payload,
        paths=final_paths,
        source_node=source_node,
        sink_node=sink_node,
        repair_status=repair_status,
    )


def _select_primary_anchors(
    paths: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    for path in paths:
        if not isinstance(path, dict):
            continue
        source_node, sink_node = select_path_anchor_pair(path)
        if source_node is not None or sink_node is not None:
            return source_node, sink_node
    return None, None


def _path_is_actionable(
    path: dict[str, object],
    *,
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
) -> bool:
    return _path_quality_score(path, source_node=source_node, sink_node=sink_node) >= 15


def _needs_java_promotion(
    path: dict[str, object],
    *,
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
) -> bool:
    del source_node
    if not isinstance(sink_node, dict):
        return False
    sink_kind = (to_text(sink_node.get("node_kind")) or "").lower()
    if sink_kind in {"var", "method"}:
        return True
    if _is_low_value_call_sink(sink_node):
        return True
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    if len(nodes) >= 2:
        previous = nodes[-2] if isinstance(nodes[-2], dict) else None
        if _same_effective_node(previous, sink_node):
            return True
    return False


def _path_quality_score(
    path: dict[str, object],
    *,
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
) -> int:
    edges = path.get("edges") if isinstance(path.get("edges"), list) else []
    nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    edge_types = {
        str(edge_type) for edge_type in path_edge_types(path) if str(edge_type).strip()
    }
    sink_labels = {label.lower() for label in _node_labels(sink_node)}
    unique_files = {
        to_text(node.get("file"))
        for node in nodes
        if isinstance(node, dict) and to_text(node.get("file"))
    }
    score = 0
    if path_has_semantic_signal(path):
        score += 30
    if "PARAM_PASS" in edge_types:
        score += 15
    if "SRC_FLOW" in edge_types:
        score += 10
    if "REF" in edge_types:
        score += 6
    if "ARG" in edge_types:
        score += 4
    score += min(len(edges) * 2, 20)
    score += min(len(unique_files) * 8, 24)

    sink_kind = (
        to_text(sink_node.get("node_kind")) if isinstance(sink_node, dict) else ""
    ) or ""
    if sink_kind.lower() == "call":
        score += 8
    elif sink_kind.lower() == "var":
        score += 4
    if any("unsafe" in label for label in sink_labels):
        score += 28
    if any("mybatis" in label for label in sink_labels):
        score += 10

    if _is_low_value_call_sink(sink_node):
        score -= 30
    if edge_types and edge_types <= {"ARG"}:
        score -= 10
    if len(nodes) >= 2:
        previous = nodes[-2] if isinstance(nodes[-2], dict) else None
        if _same_effective_node(previous, sink_node):
            score -= 8
    if isinstance(source_node, dict) and isinstance(sink_node, dict):
        if to_text(source_node.get("file")) != to_text(sink_node.get("file")):
            score += 8
    return score


def _is_low_value_call_sink(node: dict[str, object] | None) -> bool:
    if not isinstance(node, dict):
        return False
    sink_kind = (to_text(node.get("node_kind")) or "").lower()
    if sink_kind != "call":
        return False
    call_name = _node_symbol_name(node).lower()
    return bool(call_name and call_name in LOW_VALUE_CALL_NAMES)


def _same_effective_node(
    left: dict[str, object] | None, right: dict[str, object] | None
) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return (
        _node_symbol_name(left) == _node_symbol_name(right)
        and to_text(left.get("file")) == to_text(right.get("file"))
        and to_int(left.get("line")) == to_int(right.get("line"))
        and (to_text(left.get("node_kind")) or "")
        == (to_text(right.get("node_kind")) or "")
    )


def _node_symbol_name(node: dict[str, object] | None) -> str:
    if not isinstance(node, dict):
        return ""
    for candidate in (
        node.get("symbol_name"),
        node.get("display_name"),
        node.get("func_name"),
    ):
        text = to_text(candidate)
        if text:
            return text
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    return to_text(raw_props.get("name")) or ""


def _node_labels(node: dict[str, object] | None) -> set[str]:
    if not isinstance(node, dict):
        return set()
    return {
        str(label).strip()
        for label in node.get("labels") or []
        if isinstance(label, str) and label.strip()
    }


def _sink_operation_name(node: dict[str, object] | None) -> str:
    if not isinstance(node, dict):
        return ""
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    node_kind = (to_text(node.get("node_kind")) or "").lower()
    if node_kind == "call":
        candidates = (
            node.get("symbol_name"),
            node.get("display_name"),
            raw_props.get("name"),
            raw_props.get("method"),
            node.get("owner_method"),
        )
    else:
        candidates = (
            raw_props.get("method"),
            node.get("owner_method"),
            node.get("symbol_name"),
            node.get("display_name"),
            raw_props.get("name"),
        )
    for candidate in candidates:
        text = to_text(candidate)
        if text:
            return text.lower()
    return ""


def _source_business_key(
    source_node: dict[str, object] | None,
    *,
    source_file: str | None,
    source_line: int | None,
) -> str:
    normalized_file = (
        source_file or to_text(source_node.get("file"))
        if isinstance(source_node, dict)
        else source_file
    ) or "-"
    normalized_line = (
        source_line
        if source_line is not None
        else to_int(source_node.get("line"))
        if isinstance(source_node, dict)
        else None
    )
    return f"{normalized_file.lower()}:{normalized_line if normalized_line is not None else -1}"


def _build_coarse_dedupe_key(
    *,
    rule_key: str,
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
    source_file: str | None,
    source_line: int | None,
) -> str | None:
    if not isinstance(sink_node, dict):
        return None
    sink_operation = _sink_operation_name(sink_node)
    if not sink_operation:
        return None
    source_key = _source_business_key(
        source_node,
        source_file=source_file,
        source_line=source_line,
    )
    return f"{rule_key.lower()}|{source_key}|op|{sink_operation}"


def _dedupe_score(
    path: dict[str, object],
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
) -> int:
    return _path_quality_score(path, source_node=source_node, sink_node=sink_node)


def _finalize_with_path(
    *,
    finding_payload: dict[str, object],
    paths: list[dict[str, object]],
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
    repair_status: str,
) -> dict[str, object]:
    updated = dict(finding_payload)
    primary_path = paths[0] if paths and isinstance(paths[0], dict) else {}
    steps = (
        primary_path.get("steps") if isinstance(primary_path.get("steps"), list) else []
    )
    source_file = (
        to_text(source_node.get("file")) if isinstance(source_node, dict) else None
    )
    source_line = (
        to_int(source_node.get("line")) if isinstance(source_node, dict) else None
    )
    sink_file = to_text(sink_node.get("file")) if isinstance(sink_node, dict) else None
    sink_line = to_int(sink_node.get("line")) if isinstance(sink_node, dict) else None
    file_path = sink_file or source_file or to_text(updated.get("file_path"))
    line_start = sink_line or source_line or to_int(updated.get("line_start"))
    evidence = _normalize_evidence_payload(
        updated.get("evidence") or updated.get("evidence_json")
    )
    evidence.update(
        {
            "match_kind": "path",
            "path_nodes": len(steps),
            "path_edges": len(primary_path.get("edges") or []),
            "edge_types": list(dict.fromkeys(path_edge_types(paths))),
            "labels": list(dict.fromkeys(collect_path_labels(paths))),
            "repair_status": repair_status,
            "business_entry_key": _source_business_key(
                source_node,
                source_file=source_file,
                source_line=source_line,
            ),
            "sink_operation": _sink_operation_name(sink_node),
            "dedupe_score": _dedupe_score(
                primary_path,
                source_node=source_node,
                sink_node=sink_node,
            ),
            "coarse_dedupe_key": _build_coarse_dedupe_key(
                rule_key=to_text(updated.get("rule_key")) or "rule",
                source_node=source_node,
                sink_node=sink_node,
                source_file=source_file,
                source_line=source_line,
            ),
            "canonical_fingerprint": _canonical_fingerprint(
                rule_key=to_text(updated.get("rule_key")) or "rule",
                source_node=source_node,
                sink_node=sink_node,
                source_file=source_file,
                source_line=source_line,
                sink_file=sink_file,
                sink_line=sink_line,
            ),
        }
    )
    updated.update(
        {
            "paths": paths,
            "has_path": True,
            "path_length": to_int(primary_path.get("path_length"))
            or len(primary_path.get("edges") or []),
            "source_file": source_file,
            "source_line": source_line,
            "sink_file": sink_file,
            "sink_line": sink_line,
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_start,
            "evidence": evidence,
            "evidence_json": evidence,
        }
    )
    return updated


def _finalize_without_path(
    *,
    finding_payload: dict[str, object],
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
    repair_status: str,
) -> dict[str, object]:
    updated = dict(finding_payload)
    source_file = (
        to_text(source_node.get("file"))
        if isinstance(source_node, dict)
        else to_text(updated.get("source_file"))
    )
    source_line = (
        to_int(source_node.get("line"))
        if isinstance(source_node, dict)
        else to_int(updated.get("source_line"))
    )
    sink_file = (
        to_text(sink_node.get("file"))
        if isinstance(sink_node, dict)
        else to_text(updated.get("sink_file"))
    )
    sink_line = (
        to_int(sink_node.get("line"))
        if isinstance(sink_node, dict)
        else to_int(updated.get("sink_line"))
    )
    file_path = sink_file or source_file or to_text(updated.get("file_path"))
    line_start = sink_line or source_line or to_int(updated.get("line_start"))
    evidence = _normalize_evidence_payload(
        updated.get("evidence") or updated.get("evidence_json")
    )
    evidence.update(
        {
            "repair_status": repair_status,
            "business_entry_key": _source_business_key(
                source_node,
                source_file=source_file,
                source_line=source_line,
            ),
            "sink_operation": _sink_operation_name(sink_node),
            "dedupe_score": 0,
            "coarse_dedupe_key": None,
            "canonical_fingerprint": _canonical_fingerprint(
                rule_key=to_text(updated.get("rule_key")) or "rule",
                source_node=source_node,
                sink_node=sink_node,
                source_file=source_file,
                source_line=source_line,
                sink_file=sink_file,
                sink_line=sink_line,
            ),
            "candidate_edge_types": list(
                dict.fromkeys(path_edge_types(updated.get("paths") or []))
            ),
        }
    )
    updated.update(
        {
            "paths": [],
            "has_path": False,
            "path_length": None,
            "source_file": source_file,
            "source_line": source_line,
            "sink_file": sink_file or file_path,
            "sink_line": sink_line or line_start,
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_start,
            "evidence": evidence,
            "evidence_json": evidence,
        }
    )
    return updated


def _canonical_fingerprint(
    *,
    rule_key: str,
    source_node: dict[str, object] | None,
    sink_node: dict[str, object] | None,
    source_file: str | None,
    source_line: int | None,
    sink_file: str | None,
    sink_line: int | None,
) -> str:
    source_ref = _fingerprint_location(source_node, source_file, source_line)
    sink_ref = _fingerprint_location(sink_node, sink_file, sink_line)
    payload = f"{rule_key}|{source_ref}|{sink_ref}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _fingerprint_location(
    node: dict[str, object] | None,
    file_path: str | None,
    line: int | None,
) -> str:
    if isinstance(node, dict):
        node_ref = extract_path_node_ref(node)
        if node_ref:
            return node_ref
    return f"{file_path or '-'}:{line if line is not None else -1}"


def _normalize_evidence_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return {
            "items": [
                item
                for item in value
                if isinstance(item, (dict, str, int, float, bool))
            ]
        }
    return {}
