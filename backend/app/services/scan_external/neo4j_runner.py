from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.errors import AppError

from .path_result_postprocess import (
    load_path_postprocess_config,
    postprocess_result_records,
)


@dataclass(slots=True)
class CypherExecutionSummary:
    statement_count: int
    total_rows: int
    row_counts: list[int]


def execute_cypher_file(
    *,
    cypher_file: Path,
    uri: str,
    user: str,
    password: str,
    database: str,
    connect_retry: int,
    connect_wait_seconds: int,
) -> CypherExecutionSummary:
    return execute_cypher_file_stream(
        cypher_file=cypher_file,
        uri=uri,
        user=user,
        password=password,
        database=database,
        connect_retry=connect_retry,
        connect_wait_seconds=connect_wait_seconds,
        on_record=None,
    )


def execute_cypher_file_stream(
    *,
    cypher_file: Path,
    uri: str,
    user: str,
    password: str,
    database: str,
    connect_retry: int,
    connect_wait_seconds: int,
    on_record: Callable[[dict[str, Any]], None] | None,
) -> CypherExecutionSummary:
    if not cypher_file.exists() or not cypher_file.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Cypher 文件不存在",
            detail={"cypher_file": str(cypher_file)},
        )

    cypher_text = cypher_file.read_text(encoding="utf-8", errors="replace")
    statements = split_cypher_statements(cypher_text)
    if not statements:
        return CypherExecutionSummary(statement_count=0, total_rows=0, row_counts=[])

    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="缺少 neo4j Python 驱动，请安装依赖 neo4j",
        ) from exc

    auth = (
        (user, password)
        if str(user or "").strip() or str(password or "").strip()
        else None
    )
    driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=5)
    try:
        _verify_connectivity(
            driver=driver,
            retry=max(1, int(connect_retry)),
            wait_seconds=max(1, int(connect_wait_seconds)),
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )

        path_post_cfg = load_path_postprocess_config()
        row_counts: list[int] = []
        with driver.session(database=database) as session:
            for statement in statements:
                result = _run_with_retry(
                    session=session,
                    statement=statement,
                    retry=max(1, int(connect_retry)),
                    wait_seconds=max(1, int(connect_wait_seconds)),
                    retry_errors=(ServiceUnavailable, DatabaseUnavailable),
                )
                keys = list(result.keys())
                if not keys:
                    result.consume()
                    row_counts.append(0)
                    continue
                raw_records = list(result)
                records, _stats = postprocess_result_records(
                    raw_records,
                    keys,
                    path_post_cfg,
                )
                row_count = 0
                for record in records:
                    row_count += 1
                    if on_record is not None:
                        on_record(_serialize_record(record))
                row_counts.append(row_count)

        return CypherExecutionSummary(
            statement_count=len(statements),
            total_rows=sum(row_counts),
            row_counts=row_counts,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="SCAN_EXTERNAL_RULES_FAILED",
            status_code=422,
            message="执行 Cypher 失败",
            detail={"cypher_file": str(cypher_file), "error": str(exc)},
        ) from exc
    finally:
        driver.close()


def _serialize_record(record: Any) -> dict[str, Any]:
    keys = list(record.keys()) if hasattr(record, "keys") else []
    payload: dict[str, Any] = {}
    for key in keys:
        payload[str(key)] = _serialize_graph_value(record.get(key))
    return payload


def _serialize_graph_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_serialize_graph_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_graph_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_graph_value(item) for key, item in value.items()}
    if _looks_like_path(value):
        nodes = [_serialize_graph_node(node) for node in getattr(value, "nodes", [])]
        relationships = list(getattr(value, "relationships", []) or [])
        edges: list[dict[str, Any]] = []
        for index, relationship in enumerate(relationships):
            source_ref = nodes[index]["node_ref"] if index < len(nodes) else None
            target_ref = (
                nodes[index + 1]["node_ref"] if index + 1 < len(nodes) else None
            )
            edges.append(
                _serialize_path_relationship(
                    relationship,
                    edge_order=index,
                    from_node_ref=source_ref,
                    to_node_ref=target_ref,
                )
            )
        return {
            "kind": "path",
            "length": max(0, len(relationships)),
            "nodes": nodes,
            "edges": edges,
        }
    if _looks_like_node(value):
        return _serialize_graph_node(value)
    if _looks_like_relationship(value):
        return {
            "kind": "relationship",
            "type": str(getattr(value, "type", "") or ""),
            "props": _serialize_graph_items(value),
        }
    return str(value)


def _serialize_path_relationship(
    relationship: Any,
    *,
    edge_order: int,
    from_node_ref: str | None,
    to_node_ref: str | None,
) -> dict[str, Any]:
    props = _serialize_graph_items(relationship)
    edge_ref = str(
        getattr(relationship, "element_id", "")
        or props.get("id")
        or f"edge-{edge_order}"
    )
    return {
        "kind": "relationship",
        "edge_ref": edge_ref,
        "edge_order": edge_order,
        "type": str(getattr(relationship, "type", "") or ""),
        "from_node_ref": str(from_node_ref or ""),
        "to_node_ref": str(to_node_ref or ""),
        "props": props,
    }


def _serialize_graph_node(node: Any) -> dict[str, Any]:
    props = _serialize_graph_items(node)
    node_ref = str(
        props.get("id")
        or getattr(node, "element_id", "")
        or props.get("name")
        or props.get("fullName")
        or ""
    )
    return {
        "kind": "node",
        "labels": sorted(
            str(item) for item in getattr(node, "labels", []) if str(item)
        ),
        "node_ref": node_ref or "node",
        "props": props,
    }


def _serialize_graph_items(value: Any) -> dict[str, Any]:
    if not hasattr(value, "items"):
        return {}
    try:
        items = value.items()
    except Exception:
        return {}
    return {str(key): _serialize_graph_value(item) for key, item in items}


def _looks_like_path(value: Any) -> bool:
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _looks_like_node(value: Any) -> bool:
    return (
        hasattr(value, "labels")
        and hasattr(value, "items")
        and not _looks_like_path(value)
    )


def _looks_like_relationship(value: Any) -> bool:
    return (
        hasattr(value, "items")
        and hasattr(value, "type")
        and not _looks_like_node(value)
    )


def drop_database_if_exists(
    *,
    uri: str,
    user: str,
    password: str,
    database: str,
    connect_retry: int,
    connect_wait_seconds: int,
) -> None:
    target_database = database.strip()
    if not target_database:
        return

    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="缺少 neo4j Python 驱动，请安装依赖 neo4j",
        ) from exc

    auth = (
        (user, password)
        if str(user or "").strip() or str(password or "").strip()
        else None
    )
    driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=5)
    try:
        _verify_connectivity(
            driver=driver,
            retry=max(1, int(connect_retry)),
            wait_seconds=max(1, int(connect_wait_seconds)),
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )

        escaped = target_database.replace("`", "``")
        statement = f"DROP DATABASE `{escaped}` IF EXISTS"
        with driver.session(database="system") as session:
            result = _run_with_retry(
                session=session,
                statement=statement,
                retry=max(1, int(connect_retry)),
                wait_seconds=max(1, int(connect_wait_seconds)),
                retry_errors=(ServiceUnavailable, DatabaseUnavailable),
            )
            result.consume()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="删除 Neo4j 临时数据库失败",
            detail={"database": target_database, "error": str(exc)},
        ) from exc
    finally:
        driver.close()


def verify_neo4j_connectivity(
    *,
    uri: str,
    user: str,
    password: str,
    connect_retry: int,
    connect_wait_seconds: int,
) -> None:
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="缺少 neo4j Python 驱动，请安装依赖 neo4j",
        ) from exc

    auth = (
        (user, password)
        if str(user or "").strip() or str(password or "").strip()
        else None
    )
    driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=5)
    try:
        _verify_connectivity(
            driver=driver,
            retry=max(1, int(connect_retry)),
            wait_seconds=max(1, int(connect_wait_seconds)),
            retry_errors=(ServiceUnavailable, DatabaseUnavailable),
        )
    finally:
        driver.close()


def strip_cypher_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if not in_single and not in_double and not in_backtick:
            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

        if ch == "'" and not in_double and not in_backtick:
            if in_single and nxt == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue

        if ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def split_cypher_statements(text: str) -> list[str]:
    text = strip_cypher_comments(text)
    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    i = 0

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if ch == "'" and not in_double and not in_backtick:
            if in_single and nxt == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double and not in_backtick:
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


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
                    code="SCAN_EXTERNAL_NOT_CONFIGURED",
                    status_code=501,
                    message="Neo4j 连接失败，请检查连接配置",
                    detail={"error": str(exc)},
                ) from exc
            time.sleep(wait_seconds)


def _run_with_retry(
    *,
    session,
    statement: str,
    retry: int,
    wait_seconds: int,
    retry_errors: tuple[type[Exception], ...],
):
    for attempt in range(1, retry + 1):
        try:
            return session.run(statement)
        except retry_errors:
            if attempt == retry:
                raise
            time.sleep(wait_seconds)
