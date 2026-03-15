from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.models import Finding, FindingPath, FindingPathEdge, FindingPathStep, Job
from app.services.path_graph_service import (
    build_linear_path_edges,
    build_path_edge_payload,
    build_path_node_payload,
    build_path_step_payload,
)
from app.services.source_location_service import normalize_graph_location
from app.services.snapshot_storage_service import read_snapshot_file_context


_QUERY_SHORTEST = """
MATCH (src)
WHERE src.file = $source_file AND toInteger(src.line) = $source_line
MATCH (sink)
WHERE sink.file = $sink_file AND toInteger(sink.line) = $sink_line
MATCH p = shortestPath((src)-[*..30]->(sink))
RETURN p
LIMIT 1
""".strip()


_QUERY_SEMANTIC_SHORTEST = """
MATCH (src)
WHERE src.file = $source_file AND toInteger(src.line) = $source_line
MATCH (sink)
WHERE sink.file = $sink_file AND toInteger(sink.line) = $sink_line
MATCH p = shortestPath((src)-[:REF|ARG|PARAM_PASS|SRC_FLOW*..20]->(sink))
WHERE NONE(n IN nodes(p)[1..-1] WHERE n:Method)
RETURN p
LIMIT 1
""".strip()


_QUERY_SEMANTIC_BY_ID_SHORTEST = """
MATCH (src)
WHERE src.id = $source_node_ref
MATCH (sink)
WHERE sink.id = $sink_node_ref
MATCH p = shortestPath((src)-[:REF|ARG|PARAM_PASS|SRC_FLOW*..20]->(sink))
WHERE NONE(n IN nodes(p)[1..-1] WHERE n:Method)
RETURN p
LIMIT 1
""".strip()


_QUERY_SEMANTIC_BY_ID_ALL = """
MATCH (src)
WHERE src.id = $source_node_ref
MATCH (sink)
WHERE sink.id = $sink_node_ref
MATCH p = (src)-[:REF|ARG|PARAM_PASS|SRC_FLOW*..20]->(sink)
WHERE NONE(n IN nodes(p)[1..-1] WHERE n:Method)
RETURN p
ORDER BY length(p) ASC
LIMIT $limit
""".strip()


_QUERY_SEMANTIC_ALL = """
MATCH (src)
WHERE src.file = $source_file AND toInteger(src.line) = $source_line
MATCH (sink)
WHERE sink.file = $sink_file AND toInteger(sink.line) = $sink_line
MATCH p = (src)-[:REF|ARG|PARAM_PASS|SRC_FLOW*..20]->(sink)
WHERE NONE(n IN nodes(p)[1..-1] WHERE n:Method)
RETURN p
ORDER BY length(p) ASC
LIMIT $limit
""".strip()


_RUNTIME_SEMANTIC_SIGNAL_EDGE_TYPES = frozenset({"REF", "PARAM_PASS", "SRC_FLOW"})


_QUERY_ALL = """
MATCH (src)
WHERE src.file = $source_file AND toInteger(src.line) = $source_line
MATCH (sink)
WHERE sink.file = $sink_file AND toInteger(sink.line) = $sink_line
MATCH p = (src)-[*..30]->(sink)
RETURN p
ORDER BY length(p) ASC
LIMIT $limit
""".strip()


def query_finding_paths(
    *, db: Session, finding: Finding, mode: str, limit: int
) -> list[dict[str, object]]:
    normalized_mode = _normalize_mode(mode)
    safe_limit = min(max(1, int(limit)), 20)

    persisted_paths = _query_persisted_finding_paths(
        db=db,
        version_id=finding.version_id,
        finding_id=finding.id,
        mode=normalized_mode,
        limit=safe_limit,
    )
    if persisted_paths:
        return persisted_paths

    if not bool(getattr(finding, "has_path", False)):
        raise AppError(
            code="PATH_NOT_AVAILABLE",
            status_code=409,
            message="当前漏洞未记录可查询的证据链",
        )

    source_file = (finding.source_file or "").strip()
    sink_file = (finding.sink_file or "").strip()
    source_line = _to_int(finding.source_line)
    sink_line = _to_int(finding.sink_line)
    if not source_file or not sink_file or source_line is None or sink_line is None:
        raise AppError(
            code="PATH_NOT_AVAILABLE",
            status_code=409,
            message="当前漏洞缺少 source/sink 定位信息，无法查询证据链",
        )

    settings = get_settings()
    neo4j_target = resolve_finding_neo4j_target(db=db, finding=finding)
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception as exc:
        raise AppError(
            code="PATH_QUERY_FAILED",
            status_code=501,
            message="未安装 neo4j 驱动，无法查询证据链",
        ) from exc

    uri = str(neo4j_target["uri"] or "").strip()
    if not uri:
        raise AppError(
            code="PATH_QUERY_FAILED",
            status_code=501,
            message="Neo4j 未配置，无法查询证据链",
        )

    query = _QUERY_SHORTEST if normalized_mode == "shortest" else _QUERY_ALL
    params: dict[str, object] = {
        "source_file": source_file,
        "source_line": source_line,
        "sink_file": sink_file,
        "sink_line": sink_line,
        "limit": safe_limit,
    }

    retry = max(1, int(settings.scan_external_neo4j_connect_retry))
    wait_seconds = max(1, int(settings.scan_external_neo4j_connect_wait_seconds))
    driver = GraphDatabase.driver(
        uri,
        auth=(settings.scan_external_neo4j_user, settings.scan_external_neo4j_password),
        connection_timeout=5,
    )
    try:
        _verify_connectivity(
            driver=driver,
            retry=retry,
            wait_seconds=wait_seconds,
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )
        with driver.session(database=str(neo4j_target["database"])) as session:
            rows = list(session.run(query, params))
        results = _serialize_runtime_rows(version_id=finding.version_id, rows=rows)

        if not results:
            raise AppError(
                code="PATH_NOT_FOUND",
                status_code=404,
                message="未查询到证据链路径",
            )
        return results
    except AppError:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        code = (
            "PATH_QUERY_TIMEOUT"
            if "timeout" in msg or "timed out" in msg
            else "PATH_QUERY_FAILED"
        )
        raise AppError(
            code=code,
            status_code=422,
            message="证据链查询失败",
            detail={"error": str(exc)},
        ) from exc
    finally:
        driver.close()


def _query_persisted_finding_paths(
    *, db: Session, version_id, finding_id, mode: str, limit: int
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(FindingPath)
        .where(FindingPath.finding_id == finding_id)
        .order_by(FindingPath.path_length.asc(), FindingPath.path_order.asc())
        .limit(limit if mode == "all" else 1)
    ).all()
    if not rows:
        return []

    results: list[dict[str, object]] = []
    for path_index, row in enumerate(rows):
        step_rows = db.scalars(
            select(FindingPathStep)
            .where(FindingPathStep.finding_path_id == row.id)
            .order_by(FindingPathStep.step_order.asc())
        ).all()
        nodes = [
            _serialize_persisted_path_node(version_id=version_id, step=step)
            for step in step_rows
        ]
        steps = [build_path_step_payload(node) for node in nodes]
        node_ref_by_id = {
            int(node.get("node_id") or 0): str(node.get("node_ref") or "")
            for node in nodes
            if str(node.get("node_ref") or "")
        }
        edge_rows = db.scalars(
            select(FindingPathEdge)
            .where(FindingPathEdge.finding_path_id == row.id)
            .order_by(FindingPathEdge.edge_order.asc())
        ).all()
        edges = [
            _serialize_persisted_path_edge(edge=edge, node_ref_by_id=node_ref_by_id)
            for edge in edge_rows
        ]
        if not edges:
            edges = build_linear_path_edges(nodes)
        results.append(
            {
                "path_id": path_index,
                "path_length": max(0, int(row.path_length or len(edges) or 0)),
                "steps": steps,
                "nodes": nodes,
                "edges": edges,
            }
        )
    return results


def _query_runtime_semantic_paths(
    *,
    db: Session,
    finding: Finding,
    mode: str,
    limit: int,
    source_node_ref: str | None = None,
    sink_node_ref: str | None = None,
) -> list[dict[str, object]]:
    neo4j_target = _resolve_finding_runtime_neo4j_target(db=db, finding=finding)
    if neo4j_target is None:
        return []

    uri = str(neo4j_target.get("uri") or "").strip()
    database = str(neo4j_target.get("database") or "").strip()
    if not uri or not database:
        return []

    settings = get_settings()
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception:
        return []

    driver = GraphDatabase.driver(
        uri,
        auth=(settings.scan_external_neo4j_user, settings.scan_external_neo4j_password),
        connection_timeout=5,
    )
    params, query = _build_runtime_semantic_query(
        finding=finding,
        mode=mode,
        limit=limit,
        source_node_ref=source_node_ref,
        sink_node_ref=sink_node_ref,
    )
    if not params or not query:
        return []
    try:
        _verify_connectivity(
            driver=driver,
            retry=max(1, int(settings.scan_external_neo4j_connect_retry)),
            wait_seconds=max(1, int(settings.scan_external_neo4j_connect_wait_seconds)),
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )
        with driver.session(database=database) as session:
            rows = list(session.run(query, params))
        return _filter_runtime_semantic_paths(
            _serialize_runtime_rows(version_id=finding.version_id, rows=rows)
        )
    except Exception:
        return []
    finally:
        driver.close()


def query_runtime_semantic_paths_by_node_refs(
    *,
    uri: str,
    database: str,
    version_id,
    source_node_ref: str,
    sink_node_ref: str,
    mode: str = "shortest",
    limit: int = 1,
) -> list[dict[str, object]]:
    normalized_uri = str(uri or "").strip()
    normalized_database = str(database or "").strip() or "neo4j"
    normalized_source = str(source_node_ref or "").strip()
    normalized_sink = str(sink_node_ref or "").strip()
    if not normalized_uri or not normalized_source or not normalized_sink:
        return []

    settings = get_settings()
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception:
        return []

    query = (
        _QUERY_SEMANTIC_BY_ID_SHORTEST
        if mode == "shortest"
        else _QUERY_SEMANTIC_BY_ID_ALL
    )
    params: dict[str, object] = {
        "source_node_ref": normalized_source,
        "sink_node_ref": normalized_sink,
        "limit": min(max(1, int(limit)), 20),
    }
    driver = GraphDatabase.driver(
        normalized_uri,
        auth=(settings.scan_external_neo4j_user, settings.scan_external_neo4j_password),
        connection_timeout=5,
    )
    try:
        _verify_connectivity(
            driver=driver,
            retry=max(1, int(settings.scan_external_neo4j_connect_retry)),
            wait_seconds=max(1, int(settings.scan_external_neo4j_connect_wait_seconds)),
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )
        with driver.session(database=normalized_database) as session:
            rows = list(session.run(query, params))
        return _filter_runtime_semantic_paths(
            _serialize_runtime_rows(version_id=version_id, rows=rows)
        )
    except Exception:
        return []
    finally:
        driver.close()


def _build_runtime_semantic_query(
    *,
    finding: Finding,
    mode: str,
    limit: int,
    source_node_ref: str | None,
    sink_node_ref: str | None,
) -> tuple[dict[str, object] | None, str | None]:
    normalized_source = str(source_node_ref or "").strip()
    normalized_sink = str(sink_node_ref or "").strip()
    if normalized_source and normalized_sink:
        return {
            "source_node_ref": normalized_source,
            "sink_node_ref": normalized_sink,
            "limit": limit,
        }, (
            _QUERY_SEMANTIC_BY_ID_SHORTEST
            if mode == "shortest"
            else _QUERY_SEMANTIC_BY_ID_ALL
        )

    source_file = (finding.source_file or "").strip()
    sink_file = (finding.sink_file or "").strip()
    source_line = _to_int(finding.source_line)
    sink_line = _to_int(finding.sink_line)
    if not source_file or not sink_file or source_line is None or sink_line is None:
        return None, None
    return {
        "source_file": source_file,
        "source_line": source_line,
        "sink_file": sink_file,
        "sink_line": sink_line,
        "limit": limit,
    }, (_QUERY_SEMANTIC_SHORTEST if mode == "shortest" else _QUERY_SEMANTIC_ALL)


def _extract_runtime_seed_node_refs(
    paths: list[dict[str, object]],
) -> tuple[str, str] | None:
    for path in paths:
        nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
        if not nodes:
            continue
        first = nodes[0] if isinstance(nodes[0], dict) else None
        last = nodes[-1] if isinstance(nodes[-1], dict) else None
        if first is None or last is None:
            continue
        source_ref = _extract_runtime_node_ref(first)
        sink_ref = _extract_runtime_node_ref(last)
        if source_ref and sink_ref:
            return source_ref, sink_ref
    return None


def _filter_runtime_semantic_paths(
    paths: list[dict[str, object]],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for path in paths:
        if _path_has_runtime_semantic_signal(path):
            filtered.append(path)
    return filtered


def _path_has_runtime_semantic_signal(path: dict[str, object]) -> bool:
    edges = path.get("edges") if isinstance(path.get("edges"), list) else []
    edge_types = {
        str(edge.get("edge_type") or "")
        for edge in edges
        if isinstance(edge, dict) and str(edge.get("edge_type") or "")
    }
    return bool(edge_types & _RUNTIME_SEMANTIC_SIGNAL_EDGE_TYPES)


def _extract_runtime_node_ref(node: dict[str, object]) -> str | None:
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    candidates = [
        raw_props.get("id"),
        node.get("node_ref"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return None


def _resolve_finding_runtime_neo4j_target(
    *, db: Session, finding: Finding
) -> dict[str, str] | None:
    job = db.get(Job, finding.job_id)
    if job is None or not isinstance(job.result_summary, dict):
        return None
    runtime = job.result_summary.get("neo4j_runtime")
    if not isinstance(runtime, dict):
        return None

    uri = str(runtime.get("uri") or "").strip()
    database = str(runtime.get("database") or "neo4j").strip() or "neo4j"
    if not uri:
        return None
    return {"uri": uri, "database": database}


def _serialize_runtime_rows(
    *, version_id, rows: list[object]
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for path_id, row in enumerate(rows):
        path = row.get("p") if hasattr(row, "get") else None
        if path is None:
            continue
        nodes = _normalize_runtime_path_nodes(
            version_id=version_id,
            nodes=_path_nodes(path),
        )
        if not nodes:
            continue
        steps = [build_path_step_payload(node) for node in nodes]
        edges = _path_edges(path=path, nodes=nodes)
        if not edges:
            edges = build_linear_path_edges(nodes)
        results.append(
            {
                "path_id": path_id,
                "path_length": max(0, len(edges) or (len(steps) - 1)),
                "steps": steps,
                "nodes": nodes,
                "edges": edges,
            }
        )
    return results


def _serialize_persisted_path_node(
    *, version_id, step: FindingPathStep
) -> dict[str, object]:
    raw_props = dict(step.raw_props_json or {})
    normalized_input_line = step.line_no
    raw_file = str(raw_props.get("file") or "").strip()
    raw_decl_kind = str(raw_props.get("declKind") or "").strip()
    if (
        step.node_kind == "Var"
        and raw_file
        and "/tmp/jimple2cpg-" in raw_file
        and raw_decl_kind in {"Identifier", "Local", "FieldIdentifier", "Expr"}
    ):
        normalized_input_line = None
    normalized_file, normalized_line = normalize_graph_location(
        version_id=version_id,
        file_path=step.file_path,
        line=normalized_input_line,
        func_name=step.func_name,
        code_snippet=step.code_snippet,
        node_ref=step.node_ref,
        labels=[str(item) for item in step.labels_json or [] if isinstance(item, str)],
    )
    return {
        "node_id": int(step.step_order),
        "labels": [
            str(item)
            for item in step.labels_json or []
            if isinstance(item, str) and item.strip()
        ],
        "file": normalized_file,
        "line": normalized_line,
        "column": step.column_no,
        "func_name": step.func_name,
        "display_name": step.display_name,
        "symbol_name": step.symbol_name,
        "owner_method": step.owner_method,
        "type_name": step.type_name,
        "node_kind": step.node_kind,
        "code_snippet": step.code_snippet,
        "node_ref": step.node_ref,
        "raw_props": raw_props,
    }


def _serialize_persisted_path_edge(
    *, edge: FindingPathEdge, node_ref_by_id: dict[int, str]
) -> dict[str, object]:
    return build_path_edge_payload(
        index=int(edge.edge_order),
        edge_type=edge.edge_type,
        from_node_id=edge.from_step_order,
        to_node_id=edge.to_step_order,
        from_node_ref=node_ref_by_id.get(int(edge.from_step_order or -1)),
        to_node_ref=node_ref_by_id.get(int(edge.to_step_order or -1)),
        props=dict(edge.props_json or {}),
        label=edge.label,
        is_hidden=edge.is_hidden,
    )


def load_finding_path_context(
    *,
    db: Session,
    finding: Finding,
    step_id: int,
    before: int = 3,
    after: int = 3,
) -> dict[str, object]:
    paths = query_finding_paths(db=db, finding=finding, mode="shortest", limit=1)
    if not paths:
        raise AppError(
            code="PATH_NOT_FOUND", status_code=404, message="未查询到证据链路径"
        )

    steps = paths[0].get("steps") or []
    if step_id < 0 or step_id >= len(steps):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="step_id 超出路径范围",
            detail={"step_count": len(steps)},
        )

    step = steps[step_id]
    file_path = str(step.get("file") or "").strip()
    line = _to_int(step.get("line"))
    if not file_path or line is None:
        raise AppError(
            code="PATH_CONTEXT_NOT_AVAILABLE",
            status_code=422,
            message="该路径节点缺少源码定位信息",
        )

    try:
        lines, start_line, end_line = read_snapshot_file_context(
            version_id=finding.version_id,
            path=file_path,
            line=line,
            before=before,
            after=after,
        )
    except AppError as exc:
        if exc.code in {"SNAPSHOT_NOT_FOUND", "PATH_NOT_FOUND"}:
            raise AppError(
                code="SOURCE_SNAPSHOT_MISSING",
                status_code=404,
                message="源码快照不存在，无法读取上下文",
            ) from exc
        raise

    return {
        "step_id": step_id,
        "file": file_path,
        "line": line,
        "start_line": start_line,
        "end_line": end_line,
        "lines": lines,
    }


def resolve_finding_neo4j_target(*, db: Session, finding: Finding) -> dict[str, str]:
    settings = get_settings()
    target = {
        "uri": str(settings.scan_external_neo4j_uri or "").strip(),
        "database": str(settings.scan_external_neo4j_database or "neo4j").strip()
        or "neo4j",
    }
    job = db.get(Job, finding.job_id)
    if job is None or not isinstance(job.result_summary, dict):
        return target
    runtime = job.result_summary.get("neo4j_runtime")
    if not isinstance(runtime, dict):
        return target

    uri = str(runtime.get("uri") or "").strip()
    database = str(runtime.get("database") or "").strip()
    if uri:
        target["uri"] = uri
    if database:
        target["database"] = database
    return target


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "shortest").strip().lower()
    if normalized not in {"shortest", "all"}:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="mode 参数不合法",
            detail={"allowed_modes": ["shortest", "all"]},
        )
    return normalized


def _path_nodes(path: Any) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    nodes = getattr(path, "nodes", None)
    if nodes is None:
        return out

    for idx, node in enumerate(nodes):
        props = dict(node.items()) if hasattr(node, "items") else {}
        labels = sorted(
            str(item) for item in getattr(node, "labels", []) if str(item).strip()
        )
        node_ref = _to_str(props.get("id")) or _to_str(
            getattr(node, "element_id", None)
        )
        out.append(
            build_path_node_payload(
                index=idx,
                labels=labels,
                props=props,
                node_ref=node_ref,
            )
        )
    return out


def _normalize_runtime_path_nodes(
    *, version_id, nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    normalized_nodes: list[dict[str, object]] = []
    for node in nodes:
        normalized_file, normalized_line = normalize_graph_location(
            version_id=version_id,
            file_path=str(node.get("file") or "").strip() or None,
            line=node.get("line"),
            func_name=str(node.get("func_name") or "").strip() or None,
            code_snippet=str(node.get("code_snippet") or "").strip() or None,
            node_ref=str(node.get("node_ref") or "").strip() or None,
            labels=[
                str(item)
                for item in node.get("labels") or []
                if isinstance(item, str) and item.strip()
            ],
        )
        normalized_nodes.append(
            {
                **node,
                "file": normalized_file,
                "line": normalized_line,
            }
        )
    return normalized_nodes


def _path_edges(
    *, path: Any, nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    relationships = list(getattr(path, "relationships", []) or [])
    edges: list[dict[str, object]] = []
    for index, relationship in enumerate(relationships):
        from_node = nodes[index] if index < len(nodes) else None
        to_node = nodes[index + 1] if index + 1 < len(nodes) else None
        props = dict(relationship.items()) if hasattr(relationship, "items") else {}
        edges.append(
            build_path_edge_payload(
                index=index,
                edge_type=_to_str(getattr(relationship, "type", None)),
                from_node_id=_to_int(from_node.get("node_id")) if from_node else None,
                to_node_id=_to_int(to_node.get("node_id")) if to_node else None,
                from_node_ref=_to_str(from_node.get("node_ref")) if from_node else None,
                to_node_ref=_to_str(to_node.get("node_ref")) if to_node else None,
                props=props,
                edge_ref=_to_str(getattr(relationship, "element_id", None))
                or _to_str(props.get("id")),
            )
        )
    return edges


def _normalize_runtime_path_step(
    *, version_id, step: dict[str, object]
) -> dict[str, object]:
    normalized_file, normalized_line = normalize_graph_location(
        version_id=version_id,
        file_path=str(step.get("file") or "").strip() or None,
        line=step.get("line"),
        func_name=str(step.get("func_name") or "").strip() or None,
        code_snippet=str(step.get("code_snippet") or "").strip() or None,
        node_ref=str(step.get("node_ref") or "").strip() or None,
        labels=[
            str(item)
            for item in step.get("labels") or []
            if isinstance(item, str) and item.strip()
        ],
    )
    return {
        **step,
        "file": normalized_file,
        "line": normalized_line,
    }


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _verify_connectivity(
    *, driver, retry: int, wait_seconds: int, retry_errors: tuple[type[Exception], ...]
) -> None:
    for attempt in range(1, retry + 1):
        try:
            driver.verify_connectivity()
            return
        except retry_errors as exc:
            if attempt == retry:
                raise AppError(
                    code="PATH_QUERY_FAILED",
                    status_code=422,
                    message="Neo4j 连接失败，无法查询证据链",
                    detail={"error": str(exc)},
                ) from exc
            time.sleep(wait_seconds)
