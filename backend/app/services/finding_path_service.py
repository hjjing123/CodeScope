from __future__ import annotations

import time
from typing import Any

from app.config import get_settings
from app.core.errors import AppError
from app.models import Finding
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


def query_finding_paths(*, finding: Finding, mode: str, limit: int) -> list[dict[str, object]]:
    normalized_mode = _normalize_mode(mode)
    safe_limit = min(max(1, int(limit)), 20)

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
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception as exc:
        raise AppError(
            code="PATH_QUERY_FAILED",
            status_code=501,
            message="未安装 neo4j 驱动，无法查询证据链",
        ) from exc

    uri = (settings.scan_external_neo4j_uri or "").strip()
    if not uri:
        raise AppError(code="PATH_QUERY_FAILED", status_code=501, message="Neo4j 未配置，无法查询证据链")

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
        with driver.session(database=settings.scan_external_neo4j_database) as session:
            rows = list(session.run(query, params))

        results: list[dict[str, object]] = []
        for path_id, row in enumerate(rows):
            path = row.get("p")
            if path is None:
                continue
            steps = _path_steps(path)
            results.append(
                {
                    "path_id": path_id,
                    "path_length": max(0, len(steps) - 1),
                    "steps": steps,
                }
            )

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
        code = "PATH_QUERY_TIMEOUT" if "timeout" in msg or "timed out" in msg else "PATH_QUERY_FAILED"
        raise AppError(
            code=code,
            status_code=422,
            message="证据链查询失败",
            detail={"error": str(exc)},
        ) from exc
    finally:
        driver.close()


def load_finding_path_context(
    *,
    finding: Finding,
    step_id: int,
    before: int = 3,
    after: int = 3,
) -> dict[str, object]:
    paths = query_finding_paths(finding=finding, mode="shortest", limit=1)
    if not paths:
        raise AppError(code="PATH_NOT_FOUND", status_code=404, message="未查询到证据链路径")

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


def _path_steps(path: Any) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    nodes = getattr(path, "nodes", None)
    if nodes is None:
        return out

    for idx, node in enumerate(nodes):
        props = dict(node.items()) if hasattr(node, "items") else {}
        labels = sorted(str(item) for item in getattr(node, "labels", []) if str(item).strip())
        file_path = _to_str(props.get("file"))
        line = _to_int(props.get("line"))
        func_name = _to_str(props.get("method")) or _to_str(props.get("name"))
        code = _to_str(props.get("code"))
        if code is not None and len(code) > 240:
            code = f"{code[:240]}..."

        node_ref = _to_str(props.get("id")) or f"step-{idx}"
        out.append(
            {
                "step_id": idx,
                "labels": labels,
                "file": file_path,
                "line": line,
                "func_name": func_name,
                "code_snippet": code,
                "node_ref": node_ref,
            }
        )
    return out


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


def _verify_connectivity(*, driver, retry: int, wait_seconds: int, retry_errors: tuple[type[Exception], ...]) -> None:
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
