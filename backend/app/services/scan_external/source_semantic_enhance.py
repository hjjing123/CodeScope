from __future__ import annotations

import json
import time
from typing import Any, Callable

from neo4j import GraphDatabase, NotificationMinimumSeverity
from neo4j.exceptions import DatabaseUnavailable, ServiceUnavailable

from app.core.errors import AppError

from .contracts import ExternalScanContext


STATEMENTS = [
    "CREATE INDEX call_ownerMethod IF NOT EXISTS FOR (c:Call) ON (c.ownerMethod)",
    "CREATE INDEX call_ownerMethodFullName IF NOT EXISTS FOR (c:Call) ON (c.ownerMethodFullName)",
    "CREATE INDEX var_method IF NOT EXISTS FOR (v:Var) ON (v.method)",
    "CREATE INDEX var_file IF NOT EXISTS FOR (v:Var) ON (v.file)",
    "CREATE INDEX method_paramTypes IF NOT EXISTS FOR (m:Method) ON (m.paramTypes)",
    "DROP INDEX srcflow_kind IF EXISTS",
    "CALL () { MATCH ()-[r:SRC_FLOW]->() DELETE r } IN TRANSACTIONS OF 10000 ROWS",
    """
CALL () {
  MATCH (iface:Method)
  WHERE iface.fullName CONTAINS '.service.'
  MATCH (impl:Method)
  WHERE impl.fullName CONTAINS '.service.impl.'
    AND impl.name = iface.name
    AND impl.paramTypes IS NOT NULL AND iface.paramTypes IS NOT NULL
    AND size(impl.paramTypes) = size(iface.paramTypes)
    AND impl.paramTypes[1..] = iface.paramTypes[1..]
  WITH iface, impl,
       split(split(iface.fullName, ':')[0], '.') AS ifaceSeg,
       split(split(impl.fullName, ':')[0], '.') AS implSeg
  WHERE size(ifaceSeg) >= 2 AND size(implSeg) >= 2
    AND implSeg[size(implSeg)-2] = ifaceSeg[size(ifaceSeg)-2] + 'Impl'
  MATCH (ip:Var)-[:ARG]->(iface)
  MATCH (mp:Var)-[:ARG]->(impl)
  WHERE ip.paramIndex IS NOT NULL AND mp.paramIndex IS NOT NULL
    AND toInteger(ip.paramIndex) = toInteger(mp.paramIndex)
    AND toInteger(ip.paramIndex) > 0
  MERGE (ip)-[:SRC_FLOW {kind:'impl_param_bridge'}]->(mp)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var)
  WHERE src.name IS NOT NULL AND src.name <> '' AND src.name <> 'this'
    AND NOT src.name STARTS WITH '$'
    AND src.file IS NOT NULL AND src.file <> ''
    AND src.method IS NOT NULL AND src.method <> ''
  MATCH (dst:Var:AssignLeft)
  WHERE dst.id <> src.id
    AND dst.file = src.file
    AND dst.method = src.method
    AND dst.assignRight IS NOT NULL AND dst.assignRight <> ''
    AND dst.assignRight CONTAINS src.name
  MERGE (src)-[:SRC_FLOW {kind:'assign_contains'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var:AssignLeft)
  WHERE src.name IS NOT NULL AND src.name STARTS WITH '$stack'
    AND src.file IS NOT NULL AND src.file <> ''
    AND src.method IS NOT NULL AND src.method <> ''
  MATCH (dst:Var:AssignLeft)
  WHERE dst.id <> src.id
    AND dst.file = src.file
    AND dst.method = src.method
    AND dst.assignRight IS NOT NULL AND dst.assignRight <> ''
    AND dst.assignRight CONTAINS src.name
  MERGE (src)-[:SRC_FLOW {kind:'temp_assign'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (c:Call)
  WHERE c.AllocationClassName IS NOT NULL AND c.AllocationClassName <> ''
    AND c.file IS NOT NULL AND c.file <> ''
    AND c.ownerMethod IS NOT NULL AND c.ownerMethod <> ''
  MATCH (dst:Var:AssignLeft)
  WHERE dst.file = c.file
    AND dst.method = c.ownerMethod
    AND dst.assignRight IS NOT NULL AND dst.assignRight <> ''
    AND toLower(dst.assignRight) STARTS WITH 'new '
    AND toLower(dst.assignRight) CONTAINS toLower(c.AllocationClassName)
  MERGE (c)-[:SRC_FLOW {kind:'ctor_assign'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (c:Call)
  WHERE c.selector IS NOT NULL AND c.selector <> ''
    AND c.file IS NOT NULL AND c.file <> ''
    AND c.ownerMethod IS NOT NULL AND c.ownerMethod <> ''
  MATCH (dst:Var:AssignLeft)
  WHERE dst.file = c.file
    AND dst.method = c.ownerMethod
    AND dst.assignRight IS NOT NULL AND dst.assignRight <> ''
    AND dst.assignRight CONTAINS c.selector + '('
  MERGE (c)-[:SRC_FLOW {kind:'call_assign'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (v:Var)
  WHERE v.name IS NOT NULL AND v.name <> '' AND v.name <> 'this'
    AND v.file IS NOT NULL AND v.file <> ''
    AND v.method IS NOT NULL AND v.method <> ''
    AND (v:Reference OR v:Argument OR v:CallArg OR v.declKind IN ['Param','Local','FieldIdentifier'])
  MATCH (c:Call)
  WHERE c.file = v.file
    AND c.ownerMethod = v.method
    AND c.receivers IS NOT NULL
    AND any(r IN c.receivers WHERE r = v.name OR r ENDS WITH '.' + v.name)
  MERGE (v)-[:SRC_FLOW {kind:'receiver'}]->(c)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var:Argument)-[:REF|ARG|SRC_FLOW]->(arg:Var:CallArg)-[ra:ARG]->(call:Call)-[:CALLS]->(:Method)<-[rp:ARG]-(param:Var)
  WHERE src.name IS NOT NULL AND src.name <> '' AND src.name <> 'this'
    AND ra.argIndex IS NOT NULL
    AND param.paramIndex IS NOT NULL
    AND toInteger(param.paramIndex) = toInteger(ra.argIndex)
    AND (param.name IS NULL OR param.name <> 'this')
  MERGE (src)-[:SRC_FLOW {kind:'interproc_param'}]->(param)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var:Argument)-[:REF|ARG|PARAM_PASS|SRC_FLOW]->(mid:Var)-[:REF|ARG|PARAM_PASS|SRC_FLOW]->(dst:Var)
  WHERE src.id <> dst.id
    AND src.file IS NOT NULL AND dst.file IS NOT NULL AND src.file = dst.file
    AND src.method IS NOT NULL AND dst.method IS NOT NULL AND src.method = dst.method
    AND src.name IS NOT NULL AND src.name <> '' AND src.name <> 'this'
  MERGE (src)-[:SRC_FLOW {kind:'compose2var'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var:Argument)-[:REF|ARG|PARAM_PASS|SRC_FLOW]->(mid)-[:REF|ARG|PARAM_PASS|SRC_FLOW]->(dst:Call)
  WHERE src.name IS NOT NULL AND src.name <> '' AND src.name <> 'this'
  MERGE (src)-[:SRC_FLOW {kind:'compose2call'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
    """
CALL () {
  MATCH (src:Var:Argument)-[sf:SRC_FLOW]->(param:Var)-[:ARG]->(dst:Call)
  WHERE src.name IS NOT NULL AND src.name <> '' AND src.name <> 'this'
    AND sf.kind = 'interproc_param'
  MERGE (src)-[:SRC_FLOW {kind:'interproc_call'}]->(dst)
} IN TRANSACTIONS OF 10000 ROWS
""".strip(),
]


def _serialize_summary_counters(summary: Any) -> dict[str, object]:
    counters = getattr(summary, "counters", None)
    if counters is None:
        return {}

    names = [
        "contains_updates",
        "contains_system_updates",
        "nodes_created",
        "nodes_deleted",
        "relationships_created",
        "relationships_deleted",
        "properties_set",
        "labels_added",
        "labels_removed",
        "indexes_added",
        "indexes_removed",
        "constraints_added",
        "constraints_removed",
        "system_updates",
    ]
    payload: dict[str, object] = {}
    for name in names:
        value = getattr(counters, name, None)
        if value not in (None, 0, False):
            payload[name] = value
    if not payload:
        payload["contains_updates"] = bool(getattr(counters, "contains_updates", False))
    return payload


def run_source_semantic_enhance(
    *,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
) -> tuple[str, str]:
    uri = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_URI") or "").strip()
        or str(settings.scan_external_neo4j_uri or "").strip()
    )
    user = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_USER") or "").strip()
        or str(settings.scan_external_neo4j_user or "").strip()
    )
    password = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_PASSWORD") or "").strip()
        or str(settings.scan_external_neo4j_password or "").strip()
    )
    database = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_DATABASE") or "").strip()
        or str(settings.scan_external_neo4j_database or "").strip()
        or "neo4j"
    )
    if not uri:
        raise AppError(
            code="SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED",
            status_code=422,
            message="source semantic 增强缺少 Neo4j 连接地址",
        )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    script_results: list[dict[str, object]] = []
    total_statements = len(STATEMENTS)
    started_all = time.monotonic()
    append_log(
        "QUERY",
        f"[source_semantic] 开始执行源码语义增强: uri={uri}, db={database}, statements={total_statements}",
    )
    try:
        driver.verify_connectivity()
        with driver.session(
            database=database,
            notifications_min_severity=NotificationMinimumSeverity.OFF,
        ) as session:
            for index, cypher in enumerate(STATEMENTS, start=1):
                append_log(
                    "QUERY",
                    f"[source_semantic] 开始执行 {index}/{total_statements}",
                )
                started = time.monotonic()
                result = session.run(cypher)
                summary = result.consume()
                duration_ms = int((time.monotonic() - started) * 1000)
                script_results.append(
                    {
                        "statement_index": index,
                        "duration_ms": duration_ms,
                        "counters": _serialize_summary_counters(summary),
                    }
                )
                append_log(
                    "QUERY",
                    f"[source_semantic] 执行完成 {index}/{total_statements}: duration_ms={duration_ms}",
                )
    except (ServiceUnavailable, DatabaseUnavailable) as exc:
        raise AppError(
            code="SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED",
            status_code=422,
            message="source semantic 增强连接 Neo4j 失败",
            detail={"error": str(exc), "uri": uri, "database": database},
        ) from exc
    except Exception as exc:
        raise AppError(
            code="SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED",
            status_code=422,
            message="source semantic 增强执行失败",
            detail={"error": str(exc), "uri": uri, "database": database},
        ) from exc
    finally:
        driver.close()

    total_duration_ms = int((time.monotonic() - started_all) * 1000)
    payload = {
        "statement_count": total_statements,
        "duration_ms": total_duration_ms,
        "statements": script_results,
    }
    append_log(
        "QUERY",
        f"[source_semantic] 执行完成: statements={total_statements}, duration_ms={total_duration_ms}",
    )
    return json.dumps(payload, ensure_ascii=False), ""
