from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.errors import AppError


RULE_KEY_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
DEFAULT_RULE_TIMEOUT_MS = 5000


@dataclass(slots=True)
class RuleFileRecord:
    rule_key: str
    name: str
    vuln_type: str
    default_severity: str
    language_scope: str
    description: str | None
    enabled: bool
    active_version: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class RuleFileVersionRecord:
    id: uuid.UUID
    rule_key: str
    version: int
    status: str
    content: dict[str, object]
    created_by: uuid.UUID | None
    created_at: datetime


def normalize_rule_key(value: str) -> str:
    normalized = (value or "").strip()
    if normalized.lower().endswith(".cypher"):
        normalized = normalized[:-7]
    if not RULE_KEY_RE.fullmatch(normalized):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_key 仅支持字母数字以及 ._-，且长度不超过 128",
        )
    return normalized


def normalize_rule_selector(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="规则名不能为空"
        )
    return normalize_rule_key(normalized)


def list_rules(
    *,
    enabled: bool | None,
    vuln_type: str | None,
    search: str | None = None,
    page: int,
    page_size: int,
) -> tuple[list[RuleFileRecord], int]:
    rules_dir = _resolve_rules_dir()
    keys = _collect_rule_keys(rules_dir)
    records: list[RuleFileRecord] = []
    for key in keys:
        try:
            records.append(_build_rule_record(rules_dir, key))
        except AppError as exc:
            if exc.code == "NOT_FOUND":
                continue
            raise

    if enabled is not None:
        records = [item for item in records if item.enabled == enabled]
    if vuln_type is not None and vuln_type.strip():
        target = vuln_type.strip().upper()
        records = [item for item in records if item.vuln_type.upper() == target]
    if search is not None and search.strip():
        keyword = search.strip().lower()
        records = [
            item
            for item in records
            if (
                keyword in item.rule_key.lower()
                or keyword in item.name.lower()
                or keyword in item.vuln_type.lower()
                or keyword in (item.description or "").lower()
            )
        ]

    records.sort(key=lambda item: item.updated_at, reverse=True)
    total = len(records)
    start = max(0, (page - 1) * page_size)
    return records[start : start + page_size], total


def get_rule(rule_key: str) -> RuleFileRecord:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir()
    return _build_rule_record(rules_dir, key)


def get_rules_by_keys(rule_keys: set[str]) -> dict[str, RuleFileRecord]:
    rules_dir = _resolve_rules_dir()
    records: dict[str, RuleFileRecord] = {}
    for raw_key in rule_keys:
        key = normalize_rule_key(raw_key)
        try:
            records[key] = _build_rule_record(rules_dir, key)
        except AppError:
            continue
    return records


def list_rule_versions(rule_key: str) -> list[RuleFileVersionRecord]:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir()
    _ensure_rule_exists(rules_dir, key)

    versions: list[RuleFileVersionRecord] = []
    version_dir = _version_dir(rules_dir, key)
    if version_dir.exists() and version_dir.is_dir():
        for item in sorted(version_dir.glob("*.json"), key=lambda p: p.name.lower()):
            try:
                version = int(item.stem)
            except ValueError:
                continue
            payload = _read_json_dict(item)
            content = _ensure_content_dict(
                payload.get("content"), default_query_path=None
            )
            status = str(payload.get("status") or "PUBLISHED").upper()
            created_by = _parse_uuid(payload.get("created_by"))
            created_at = _parse_datetime(
                payload.get("created_at"), fallback=_mtime(item)
            )
            versions.append(
                RuleFileVersionRecord(
                    id=_version_uuid(key, version, status),
                    rule_key=key,
                    version=version,
                    status=status,
                    content=content,
                    created_by=created_by,
                    created_at=created_at,
                )
            )

    draft_path = _draft_path(rules_dir, key)
    if draft_path.exists() and draft_path.is_file():
        payload = _read_json_dict(draft_path)
        version = _parse_positive_int(
            payload.get("version"), default=_next_version(rules_dir, key)
        )
        content = _ensure_content_dict(payload.get("content"), default_query_path=None)
        created_by = _parse_uuid(payload.get("created_by"))
        created_at = _parse_datetime(
            payload.get("created_at"), fallback=_mtime(draft_path)
        )
        versions.append(
            RuleFileVersionRecord(
                id=_version_uuid(key, version, "DRAFT"),
                rule_key=key,
                version=version,
                status="DRAFT",
                content=content,
                created_by=created_by,
                created_at=created_at,
            )
        )

    rule_file = _rule_file_path(rules_dir, key)
    if rule_file.exists() and rule_file.is_file() and not versions:
        content = _build_content_from_rule_file(
            rule_file=rule_file, meta=_load_meta(rules_dir, key)
        )
        versions.append(
            RuleFileVersionRecord(
                id=_version_uuid(key, 1, "PUBLISHED"),
                rule_key=key,
                version=1,
                status="PUBLISHED",
                content=content,
                created_by=None,
                created_at=_mtime(rule_file),
            )
        )

    versions.sort(
        key=lambda item: (item.version, 1 if item.status == "DRAFT" else 0),
        reverse=True,
    )
    return versions


def create_rule(
    *,
    rule_key: str,
    name: str,
    vuln_type: str,
    default_severity: str,
    language_scope: str,
    description: str | None,
    content: dict[str, object],
    created_by: uuid.UUID | None,
) -> tuple[RuleFileRecord, RuleFileVersionRecord]:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir(create_missing=True)
    if _rule_exists(rules_dir, key):
        raise AppError(
            code="RULE_ALREADY_EXISTS", status_code=409, message="规则已存在"
        )

    now = _now()
    meta = {
        "rule_key": key,
        "name": name.strip() or key,
        "vuln_type": vuln_type.strip().upper() or _infer_vuln_type(key),
        "default_severity": default_severity.strip().upper() or _infer_severity(key),
        "language_scope": language_scope.strip() or "java",
        "description": description,
        "enabled": True,
        "active_version": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    _write_meta(rules_dir, key, meta)

    draft = {
        "version": 1,
        "status": "DRAFT",
        "content": _ensure_content_dict(content, default_query_path=None),
        "created_by": str(created_by) if created_by is not None else None,
        "created_at": now.isoformat(),
    }
    _write_json(_draft_path(rules_dir, key), draft)

    rule = _build_rule_record(rules_dir, key)
    draft_version = RuleFileVersionRecord(
        id=_version_uuid(key, 1, "DRAFT"),
        rule_key=key,
        version=1,
        status="DRAFT",
        content=_ensure_content_dict(draft.get("content"), default_query_path=None),
        created_by=created_by,
        created_at=now,
    )
    return rule, draft_version


def update_rule_draft(
    *,
    rule_key: str,
    updates: dict[str, object],
    operator_id: uuid.UUID | None,
) -> tuple[RuleFileRecord, RuleFileVersionRecord]:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir(create_missing=True)
    _ensure_rule_exists(rules_dir, key)

    now = _now()
    meta = _load_meta(rules_dir, key)
    if not meta:
        base = _build_rule_record(rules_dir, key)
        meta = {
            "rule_key": base.rule_key,
            "name": base.name,
            "vuln_type": base.vuln_type,
            "default_severity": base.default_severity,
            "language_scope": base.language_scope,
            "description": base.description,
            "enabled": base.enabled,
            "active_version": base.active_version,
            "created_at": base.created_at.isoformat(),
            "updated_at": base.updated_at.isoformat(),
        }

    draft_path = _draft_path(rules_dir, key)
    if draft_path.exists() and draft_path.is_file():
        draft = _read_json_dict(draft_path)
    else:
        base_content: dict[str, object] = {}
        active_version = _parse_positive_int(meta.get("active_version"), default=0)
        if active_version > 0:
            version_path = _version_path(rules_dir, key, active_version)
            if version_path.exists() and version_path.is_file():
                version_payload = _read_json_dict(version_path)
                base_content = _ensure_content_dict(
                    version_payload.get("content"), default_query_path=None
                )
        else:
            rule_file = _rule_file_path(rules_dir, key)
            if rule_file.exists() and rule_file.is_file():
                base_content = _build_content_from_rule_file(
                    rule_file=rule_file, meta=meta
                )

        draft = {
            "version": _next_version(rules_dir, key),
            "status": "DRAFT",
            "content": base_content,
            "created_by": str(operator_id) if operator_id is not None else None,
            "created_at": now.isoformat(),
        }

    if updates.get("name") is not None:
        meta["name"] = str(updates["name"]).strip() or key
    if updates.get("vuln_type") is not None:
        meta["vuln_type"] = str(
            updates["vuln_type"]
        ).strip().upper() or _infer_vuln_type(key)
    if updates.get("default_severity") is not None:
        meta["default_severity"] = str(
            updates["default_severity"]
        ).strip().upper() or _infer_severity(key)
    if updates.get("language_scope") is not None:
        meta["language_scope"] = str(updates["language_scope"]).strip() or "java"
    if "description" in updates:
        value = updates.get("description")
        meta["description"] = None if value is None else str(value)
    if updates.get("content") is not None:
        draft["content"] = _ensure_content_dict(
            updates.get("content"), default_query_path=None
        )
    draft["created_by"] = (
        str(operator_id) if operator_id is not None else draft.get("created_by")
    )
    meta["updated_at"] = now.isoformat()

    _write_meta(rules_dir, key, meta)
    _write_json(draft_path, draft)

    draft_version_number = _parse_positive_int(
        draft.get("version"), default=_next_version(rules_dir, key)
    )
    rule = _build_rule_record(rules_dir, key)
    draft_version = RuleFileVersionRecord(
        id=_version_uuid(key, draft_version_number, "DRAFT"),
        rule_key=key,
        version=draft_version_number,
        status="DRAFT",
        content=_ensure_content_dict(draft.get("content"), default_query_path=None),
        created_by=_parse_uuid(draft.get("created_by")),
        created_at=_parse_datetime(draft.get("created_at"), fallback=now),
    )
    return rule, draft_version


def publish_rule(
    *, rule_key: str, operator_id: uuid.UUID | None
) -> tuple[RuleFileRecord, RuleFileVersionRecord]:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir(create_missing=True)
    _ensure_rule_exists(rules_dir, key)

    draft_path = _draft_path(rules_dir, key)
    if not draft_path.exists() or not draft_path.is_file():
        raise AppError(
            code="RULE_DRAFT_NOT_FOUND", status_code=409, message="规则草稿不存在"
        )

    draft = _read_json_dict(draft_path)
    version = _parse_positive_int(
        draft.get("version"), default=_next_version(rules_dir, key)
    )
    content = _ensure_content_dict(draft.get("content"), default_query_path=None)
    normalized_content = _validate_rule_content(rule_key=key, content=content)

    now = _now()
    published = {
        "version": version,
        "status": "PUBLISHED",
        "content": normalized_content,
        "created_by": str(operator_id)
        if operator_id is not None
        else draft.get("created_by"),
        "created_at": draft.get("created_at") or now.isoformat(),
    }
    _write_json(_version_path(rules_dir, key, version), published)
    _write_text(
        _rule_file_path(rules_dir, key),
        str(normalized_content.get("query") or "").rstrip() + "\n",
    )

    meta = _load_meta(rules_dir, key)
    if not meta:
        inferred = _build_rule_record(rules_dir, key)
        meta = {
            "rule_key": key,
            "name": inferred.name,
            "vuln_type": inferred.vuln_type,
            "default_severity": inferred.default_severity,
            "language_scope": inferred.language_scope,
            "description": inferred.description,
            "enabled": inferred.enabled,
            "created_at": inferred.created_at.isoformat(),
        }
    meta["active_version"] = version
    meta["timeout_ms"] = int(
        normalized_content.get("timeout_ms") or DEFAULT_RULE_TIMEOUT_MS
    )
    meta["updated_at"] = now.isoformat()
    _write_meta(rules_dir, key, meta)
    draft_path.unlink(missing_ok=True)

    rule = _build_rule_record(rules_dir, key)
    published_version = RuleFileVersionRecord(
        id=_version_uuid(key, version, "PUBLISHED"),
        rule_key=key,
        version=version,
        status="PUBLISHED",
        content=normalized_content,
        created_by=_parse_uuid(published.get("created_by")),
        created_at=_parse_datetime(published.get("created_at"), fallback=now),
    )
    return rule, published_version


def rollback_rule(*, rule_key: str, version: int) -> RuleFileRecord:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir(create_missing=True)
    _ensure_rule_exists(rules_dir, key)

    version_path = _version_path(rules_dir, key, int(version))
    if not version_path.exists() or not version_path.is_file():
        raise AppError(
            code="RULE_VERSION_NOT_FOUND",
            status_code=404,
            message="目标发布版本不存在",
        )

    payload = _read_json_dict(version_path)
    content = _ensure_content_dict(payload.get("content"), default_query_path=None)
    normalized_content = _validate_rule_content(rule_key=key, content=content)
    _write_text(
        _rule_file_path(rules_dir, key),
        str(normalized_content.get("query") or "").rstrip() + "\n",
    )

    meta = _load_meta(rules_dir, key)
    now = _now()
    if not meta:
        meta = {
            "rule_key": key,
            "name": key,
            "vuln_type": _infer_vuln_type(key),
            "default_severity": _infer_severity(key),
            "language_scope": "java",
            "description": None,
            "enabled": True,
            "created_at": now.isoformat(),
        }
    meta["active_version"] = int(version)
    meta["timeout_ms"] = int(
        normalized_content.get("timeout_ms") or DEFAULT_RULE_TIMEOUT_MS
    )
    meta["updated_at"] = now.isoformat()
    _write_meta(rules_dir, key, meta)
    return _build_rule_record(rules_dir, key)


def toggle_rule(*, rule_key: str, enabled: bool) -> RuleFileRecord:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir(create_missing=True)
    _ensure_rule_exists(rules_dir, key)

    now = _now()
    meta = _load_meta(rules_dir, key)
    if not meta:
        current = _build_rule_record(rules_dir, key)
        meta = {
            "rule_key": current.rule_key,
            "name": current.name,
            "vuln_type": current.vuln_type,
            "default_severity": current.default_severity,
            "language_scope": current.language_scope,
            "description": current.description,
            "active_version": current.active_version,
            "created_at": current.created_at.isoformat(),
        }
    meta["enabled"] = bool(enabled)
    meta["updated_at"] = now.isoformat()
    _write_meta(rules_dir, key, meta)
    return _build_rule_record(rules_dir, key)


def resolve_rule_content(
    *, rule_key: str, rule_version: int | None
) -> tuple[str, int | None, dict[str, object]]:
    key = normalize_rule_key(rule_key)
    rules_dir = _resolve_rules_dir()
    _ensure_rule_exists(rules_dir, key)

    if rule_version is not None:
        target = int(rule_version)
        draft_path = _draft_path(rules_dir, key)
        if draft_path.exists() and draft_path.is_file():
            draft = _read_json_dict(draft_path)
            draft_version = _parse_positive_int(draft.get("version"), default=-1)
            if draft_version == target:
                content = _ensure_content_dict(
                    draft.get("content"), default_query_path=None
                )
                normalized = _validate_rule_content(rule_key=key, content=content)
                return key, target, normalized

        version_path = _version_path(rules_dir, key, target)
        if version_path.exists() and version_path.is_file():
            payload = _read_json_dict(version_path)
            content = _ensure_content_dict(
                payload.get("content"), default_query_path=None
            )
            normalized = _validate_rule_content(rule_key=key, content=content)
            return key, target, normalized

        raise AppError(
            code="RULE_VERSION_NOT_FOUND", status_code=404, message="指定规则版本不存在"
        )

    candidates = list_rule_versions(key)
    if not candidates:
        raise AppError(
            code="RULE_DRAFT_NOT_FOUND", status_code=404, message="规则草稿不存在"
        )

    picked = candidates[0]
    normalized = _validate_rule_content(rule_key=key, content=picked.content)
    return key, picked.version, normalized


def list_runtime_rule_files(*, rules_dir: Path | None = None) -> list[Path]:
    root = rules_dir if rules_dir is not None else _resolve_rules_dir()
    if not root.exists() or not root.is_dir():
        return []

    files = sorted(
        [item for item in root.glob("*.cypher") if item.is_file()],
        key=lambda item: item.name.lower(),
    )
    selected: list[Path] = []
    for file_path in files:
        try:
            key = normalize_rule_key(file_path.stem)
        except AppError:
            continue
        if is_rule_enabled(key, rules_dir=root):
            selected.append(file_path)
    return selected


def resolve_runtime_rule_files(
    *,
    requested_rule_names: list[str],
    rules_dir: Path | None = None,
) -> tuple[list[Path], list[str], list[str]]:
    root = rules_dir if rules_dir is not None else _resolve_rules_dir()
    selected: list[Path] = []
    missing: list[str] = []
    disabled: list[str] = []
    selected_markers: set[str] = set()

    for raw_name in requested_rule_names:
        original = (raw_name or "").strip()
        if not original:
            continue
        try:
            key = normalize_rule_selector(original)
        except AppError:
            missing.append(original)
            continue

        file_path = _rule_file_path(root, key)
        if not file_path.exists() or not file_path.is_file():
            missing.append(original)
            continue
        if not is_rule_enabled(key, rules_dir=root):
            disabled.append(original)
            continue

        marker = str(file_path.resolve()).lower()
        if marker in selected_markers:
            continue
        selected_markers.add(marker)
        selected.append(file_path)

    return selected, missing, disabled


def validate_runtime_rule_keys(
    *,
    requested_rule_names: list[str],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in requested_rule_names:
        key = normalize_rule_selector(item)
        marker = key.lower()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(key)

    if not normalized:
        return []

    _selected, missing, disabled = resolve_runtime_rule_files(
        requested_rule_names=normalized
    )
    if missing:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_keys 中存在不存在的规则",
            detail={"missing_rules": missing},
        )
    if disabled:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_keys 中包含已停用规则",
            detail={"disabled_rules": disabled},
        )
    return normalized


def validate_runtime_rule_selection(*, requested_rule_names: list[str]) -> list[str]:
    return validate_runtime_rule_keys(requested_rule_names=requested_rule_names)


def validate_runtime_single_rule(*, rule_name: str) -> str:
    key = normalize_rule_selector(rule_name)
    file_path = _rule_file_path(_resolve_rules_dir(), key)
    if not file_path.exists() or not file_path.is_file():
        raise AppError(code="NOT_FOUND", status_code=404, message="规则不存在")
    if not is_rule_enabled(key):
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="规则已停用")
    return key


def is_rule_enabled(rule_key: str, *, rules_dir: Path | None = None) -> bool:
    key = normalize_rule_key(rule_key)
    root = rules_dir if rules_dir is not None else _resolve_rules_dir()
    meta = _load_meta(root, key)
    value = meta.get("enabled")
    if isinstance(value, bool):
        return value
    return True


def _build_rule_record(rules_dir: Path, rule_key: str) -> RuleFileRecord:
    key = normalize_rule_key(rule_key)
    if not _rule_exists(rules_dir, key):
        raise AppError(code="NOT_FOUND", status_code=404, message="规则不存在")

    meta = _load_meta(rules_dir, key)
    rule_file = _rule_file_path(rules_dir, key)
    draft = _draft_path(rules_dir, key)
    version_dir = _version_dir(rules_dir, key)

    default_created = _now()
    if rule_file.exists() and rule_file.is_file():
        default_created = _mtime(rule_file)
    elif draft.exists() and draft.is_file():
        default_created = _mtime(draft)

    created_at = _parse_datetime(meta.get("created_at"), fallback=default_created)
    updated_candidates = [created_at]
    if rule_file.exists() and rule_file.is_file():
        updated_candidates.append(_mtime(rule_file))
    if draft.exists() and draft.is_file():
        updated_candidates.append(_mtime(draft))
    if version_dir.exists() and version_dir.is_dir():
        for item in version_dir.glob("*.json"):
            if item.is_file():
                updated_candidates.append(_mtime(item))
    updated_at = _parse_datetime(
        meta.get("updated_at"), fallback=max(updated_candidates)
    )

    active_version = _parse_positive_int(meta.get("active_version"), default=None)
    if active_version is None:
        active_version = _infer_active_version(rules_dir, key)

    return RuleFileRecord(
        rule_key=key,
        name=str(meta.get("name") or key),
        vuln_type=str(meta.get("vuln_type") or _infer_vuln_type(key)),
        default_severity=str(meta.get("default_severity") or _infer_severity(key)),
        language_scope=str(meta.get("language_scope") or "java"),
        description=(
            None if meta.get("description") is None else str(meta.get("description"))
        ),
        enabled=bool(meta.get("enabled", True)),
        active_version=active_version,
        created_at=created_at,
        updated_at=updated_at,
    )


def _infer_active_version(rules_dir: Path, rule_key: str) -> int | None:
    version_dir = _version_dir(rules_dir, rule_key)
    versions: list[int] = []
    if version_dir.exists() and version_dir.is_dir():
        for item in version_dir.glob("*.json"):
            if not item.is_file():
                continue
            try:
                versions.append(int(item.stem))
            except ValueError:
                continue
    if versions:
        return max(versions)
    file_path = _rule_file_path(rules_dir, rule_key)
    if file_path.exists() and file_path.is_file():
        return 1
    return None


def _collect_rule_keys(rules_dir: Path) -> list[str]:
    if not rules_dir.exists() or not rules_dir.is_dir():
        return []

    keys: set[str] = set()
    for item in rules_dir.glob("*.cypher"):
        if not item.is_file():
            continue
        try:
            keys.add(normalize_rule_key(item.stem))
        except AppError:
            continue

    meta_dir = _meta_dir(rules_dir)
    if meta_dir.exists() and meta_dir.is_dir():
        for item in meta_dir.glob("*.json"):
            if not item.is_file():
                continue
            try:
                keys.add(normalize_rule_key(item.stem))
            except AppError:
                continue

    draft_dir = _draft_dir(rules_dir)
    if draft_dir.exists() and draft_dir.is_dir():
        for item in draft_dir.glob("*.json"):
            if not item.is_file():
                continue
            try:
                keys.add(normalize_rule_key(item.stem))
            except AppError:
                continue

    versions_root = _versions_root(rules_dir)
    if versions_root.exists() and versions_root.is_dir():
        for item in versions_root.iterdir():
            if not item.is_dir():
                continue
            if not _has_version_files(item):
                continue
            try:
                keys.add(normalize_rule_key(item.name))
            except AppError:
                continue

    return sorted(keys, key=lambda value: value.lower())


def _ensure_rule_exists(rules_dir: Path, rule_key: str) -> None:
    if not _rule_exists(rules_dir, rule_key):
        raise AppError(code="NOT_FOUND", status_code=404, message="规则不存在")


def _rule_exists(rules_dir: Path, rule_key: str) -> bool:
    key = normalize_rule_key(rule_key)
    if _rule_file_path(rules_dir, key).exists():
        return True
    if _meta_path(rules_dir, key).exists():
        return True
    if _draft_path(rules_dir, key).exists():
        return True
    version_dir = _version_dir(rules_dir, key)
    if _has_version_files(version_dir):
        return True
    return False


def _has_version_files(version_dir: Path) -> bool:
    return (
        version_dir.exists()
        and version_dir.is_dir()
        and any(item.is_file() for item in version_dir.glob("*.json"))
    )


def _next_version(rules_dir: Path, rule_key: str) -> int:
    key = normalize_rule_key(rule_key)
    values: list[int] = []

    version_dir = _version_dir(rules_dir, key)
    if version_dir.exists() and version_dir.is_dir():
        for item in version_dir.glob("*.json"):
            if not item.is_file():
                continue
            try:
                values.append(int(item.stem))
            except ValueError:
                continue

    draft_path = _draft_path(rules_dir, key)
    if draft_path.exists() and draft_path.is_file():
        draft = _read_json_dict(draft_path)
        draft_version = _parse_positive_int(draft.get("version"), default=None)
        if draft_version is not None:
            values.append(draft_version)

    if not values:
        return 1
    return max(values) + 1


def _build_content_from_rule_file(
    *, rule_file: Path, meta: dict[str, object]
) -> dict[str, object]:
    query = rule_file.read_text(encoding="utf-8", errors="replace")
    timeout_ms = _parse_positive_int(
        meta.get("timeout_ms"), default=DEFAULT_RULE_TIMEOUT_MS
    )
    if timeout_ms is None:
        timeout_ms = DEFAULT_RULE_TIMEOUT_MS
    return {"query": query.strip(), "timeout_ms": int(timeout_ms)}


def _ensure_content_dict(
    value: object, *, default_query_path: Path | None
) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if (
        default_query_path is not None
        and default_query_path.exists()
        and default_query_path.is_file()
    ):
        return _build_content_from_rule_file(rule_file=default_query_path, meta={})
    return {}


def _load_meta(rules_dir: Path, rule_key: str) -> dict[str, object]:
    path = _meta_path(rules_dir, rule_key)
    if not path.exists() or not path.is_file():
        return {}
    return _read_json_dict(path)


def _write_meta(rules_dir: Path, rule_key: str, payload: dict[str, object]) -> None:
    _write_json(_meta_path(rules_dir, rule_key), payload)


def _read_json_dict(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppError(
            code="RULE_FILE_INVALID",
            status_code=422,
            message="规则文件解析失败",
            detail={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(
            code="RULE_FILE_INVALID",
            status_code=422,
            message="规则文件结构不正确",
            detail={"path": str(path)},
        )
    return raw


def _write_json(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _write_text(path, text + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _resolve_rules_dir(*, create_missing: bool = False) -> Path:
    settings = get_settings()
    raw = (settings.scan_external_rules_dir or "").strip()
    if not raw:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置规则目录",
        )

    path = Path(raw)
    if not path.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        path = (backend_root / path).resolve()
    else:
        path = path.resolve()

    if create_missing:
        path.mkdir(parents=True, exist_ok=True)
        return path

    if not path.exists() or not path.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="规则目录不存在",
            detail={"rules_dir": str(path)},
        )
    return path


def _rule_file_path(rules_dir: Path, rule_key: str) -> Path:
    return rules_dir / f"{normalize_rule_key(rule_key)}.cypher"


def _meta_dir(rules_dir: Path) -> Path:
    return rules_dir / ".meta"


def _meta_path(rules_dir: Path, rule_key: str) -> Path:
    return _meta_dir(rules_dir) / f"{normalize_rule_key(rule_key)}.json"


def _draft_dir(rules_dir: Path) -> Path:
    return rules_dir / ".drafts"


def _draft_path(rules_dir: Path, rule_key: str) -> Path:
    return _draft_dir(rules_dir) / f"{normalize_rule_key(rule_key)}.json"


def _versions_root(rules_dir: Path) -> Path:
    return rules_dir / ".versions"


def _version_dir(rules_dir: Path, rule_key: str) -> Path:
    return _versions_root(rules_dir) / normalize_rule_key(rule_key)


def _version_path(rules_dir: Path, rule_key: str, version: int) -> Path:
    return _version_dir(rules_dir, rule_key) / f"{int(version)}.json"


def _infer_vuln_type(rule_key: str) -> str:
    key = rule_key.lower()
    if "weekpass" in key or "weakpass" in key:
        return "WEAK_PASSWORD"
    if "weekhash" in key or "weakhash" in key:
        return "WEAK_HASH"
    if "cookiesecure" in key or key.startswith("cookie_"):
        return "COOKIE_FLAGS"
    if "hardcode" in key:
        return "HARDCODE_SECRET"
    if "alloworigin" in key or "cors" in key:
        return "CORS"
    if any(
        token in key for token in ["misconfig", "actuator", "swagger", "druid", "_h2_"]
    ):
        return "MISCONFIG"
    if "infoleak" in key:
        return "INFOLEAK"
    if "hpe" in key or "idor" in key:
        return "HPE"
    if "ldapi" in key or "ldap" in key:
        return "LDAPI"
    if "jndii" in key or "jndi" in key:
        return "JNDII"
    if "sqli" in key or key.endswith("_sql"):
        return "SQLI"
    if "xss" in key:
        return "XSS"
    if "ssrf" in key:
        return "SSRF"
    if "xxe" in key:
        return "XXE"
    if "upload" in key:
        return "UPLOAD"
    if "pathtraver" in key or "travers" in key:
        return "PATH_TRAVERSAL"
    if "cmdi" in key:
        return "CMDI"
    if "codei" in key:
        return "CODEI"
    if "deserialization" in key:
        return "DESERIALIZATION"
    if "redirect" in key:
        return "OPEN_REDIRECT"
    return "CUSTOM"


def _infer_severity(rule_key: str) -> str:
    key = rule_key.lower()
    if any(
        token in key
        for token in ["rce", "cmdi", "codei", "deserialization", "sqli", "xxe", "jndi"]
    ):
        return "HIGH"
    if any(
        token in key
        for token in [
            "xss",
            "ssrf",
            "upload",
            "pathtraver",
            "redirect",
            "ldapi",
            "hpe",
            "alloworigin",
            "cookiesecure",
        ]
    ):
        return "MED"
    return "LOW"


def _version_uuid(rule_key: str, version: int, status: str) -> uuid.UUID:
    seed = f"codescope-rule-version:{rule_key}:{version}:{status.upper()}"
    return uuid.uuid5(uuid.NAMESPACE_URL, seed)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _parse_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return fallback
    return fallback


def _parse_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _parse_positive_int(value: object, *, default: int | None) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_rule_content(*, rule_key: str, content: Any) -> dict[str, object]:
    from app.services.rule_validation_service import validate_rule_content_for_publish

    return validate_rule_content_for_publish(rule_key=rule_key, content=content)
