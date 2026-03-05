from __future__ import annotations

import re
from typing import Any

from app.core.errors import AppError
from app.services.scan_external.neo4j_runner import split_cypher_statements


MAX_RULE_TIMEOUT_MS = 300_000
MAX_RULE_QUERY_LENGTH = 200_000
ALLOWED_STATEMENT_PREFIXES = {
    "MATCH",
    "OPTIONAL",
    "WITH",
    "UNWIND",
    "RETURN",
    "CALL",
}
FORBIDDEN_WRITE_CLAUSE_RE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|DROP|REMOVE|SET)\b", re.IGNORECASE)


def validate_rule_content_for_publish(*, rule_key: str, content: Any) -> dict[str, object]:
    if not isinstance(content, dict):
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="规则内容必须为对象",
            detail={"rule_key": rule_key, "field": "content"},
        )

    query_raw = content.get("query")
    if not isinstance(query_raw, str) or not query_raw.strip():
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="规则内容缺少有效 query",
            detail={"rule_key": rule_key, "field": "query"},
        )
    query = query_raw.strip()
    if len(query) > MAX_RULE_QUERY_LENGTH:
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="规则 query 长度超过上限",
            detail={
                "rule_key": rule_key,
                "field": "query",
                "max_length": MAX_RULE_QUERY_LENGTH,
            },
        )

    timeout_ms = _parse_timeout_ms(rule_key=rule_key, value=content.get("timeout_ms"))

    statements = split_cypher_statements(query)
    if not statements:
        raise AppError(
            code="RULE_SYNTAX_ERROR",
            status_code=422,
            message="规则 query 解析失败，未识别到可执行语句",
            detail={"rule_key": rule_key},
        )

    for index, statement in enumerate(statements, start=1):
        prefix = _statement_prefix(statement)
        if prefix not in ALLOWED_STATEMENT_PREFIXES:
            raise AppError(
                code="RULE_SYNTAX_ERROR",
                status_code=422,
                message="规则 query 包含不支持的语句前缀",
                detail={"rule_key": rule_key, "statement_index": index, "prefix": prefix},
            )
        if FORBIDDEN_WRITE_CLAUSE_RE.search(statement):
            raise AppError(
                code="RULE_VALIDATION_FAILED",
                status_code=422,
                message="规则 query 不允许包含写操作子句",
                detail={"rule_key": rule_key, "statement_index": index},
            )

    normalized = dict(content)
    normalized["query"] = query
    normalized["timeout_ms"] = timeout_ms
    return normalized


def _parse_timeout_ms(*, rule_key: str, value: Any) -> int:
    if value is None:
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="规则内容缺少 timeout_ms",
            detail={"rule_key": rule_key, "field": "timeout_ms"},
        )
    if isinstance(value, bool):
        parsed = None
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        parsed = int(text) if text.isdigit() else None
    else:
        parsed = None

    if parsed is None or parsed <= 0:
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="timeout_ms 必须为正整数",
            detail={"rule_key": rule_key, "field": "timeout_ms"},
        )
    if parsed > MAX_RULE_TIMEOUT_MS:
        raise AppError(
            code="RULE_VALIDATION_FAILED",
            status_code=422,
            message="timeout_ms 超过上限",
            detail={
                "rule_key": rule_key,
                "field": "timeout_ms",
                "max_timeout_ms": MAX_RULE_TIMEOUT_MS,
            },
        )
    return parsed


def _statement_prefix(statement: str) -> str:
    token = statement.strip().split(maxsplit=1)
    if not token:
        return ""
    return token[0].upper()
