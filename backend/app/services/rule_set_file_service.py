from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core.errors import AppError
from app.services.rule_file_service import (
    list_runtime_rule_files,
    normalize_rule_selector,
    validate_runtime_rule_keys,
)


RULE_SET_KEY_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_UNSET = object()


@dataclass(slots=True)
class RuleSetFileItemRecord:
    id: uuid.UUID
    rule_set_id: uuid.UUID
    rule_key: str
    created_at: datetime


@dataclass(slots=True)
class RuleSetFileRecord:
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    enabled: bool
    rule_keys: list[str]
    created_at: datetime
    updated_at: datetime


def normalize_rule_set_key(value: str) -> str:
    normalized = (value or "").strip()
    if not RULE_SET_KEY_RE.fullmatch(normalized):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_set_key 仅支持字母数字以及 ._-，且长度不超过 128",
        )
    return normalized


def list_rule_sets(*, page: int, page_size: int) -> tuple[list[RuleSetFileRecord], int]:
    rows = [record for _path, record in _load_all_rule_sets()]
    rows.sort(key=lambda item: item.updated_at, reverse=True)
    total = len(rows)
    start = max(0, (page - 1) * page_size)
    return rows[start : start + page_size], total


def get_rule_set(*, rule_set_id: uuid.UUID) -> RuleSetFileRecord:
    _path, record = _find_rule_set_by_id(rule_set_id=rule_set_id)
    if record is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则集不存在")
    return record


def create_rule_set(
    *,
    key: str,
    name: str,
    description: str | None,
    enabled: bool,
) -> RuleSetFileRecord:
    normalized_key = normalize_rule_set_key(key)
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="规则集名称不能为空"
        )

    rows = [record for _path, record in _load_all_rule_sets()]
    if any(item.key.lower() == normalized_key.lower() for item in rows):
        raise AppError(
            code="RULE_SET_ALREADY_EXISTS", status_code=409, message="规则集 key 已存在"
        )
    if any(item.name.lower() == normalized_name.lower() for item in rows):
        raise AppError(
            code="RULE_SET_ALREADY_EXISTS", status_code=409, message="规则集名称已存在"
        )

    now = _now()
    record = RuleSetFileRecord(
        id=uuid.uuid4(),
        key=normalized_key,
        name=normalized_name,
        description=description,
        enabled=bool(enabled),
        rule_keys=[],
        created_at=now,
        updated_at=now,
    )
    _write_rule_set(
        path=_rule_set_path(
            _resolve_rule_sets_dir(create_missing=True), normalized_key
        ),
        record=record,
    )
    return record


def update_rule_set(
    *,
    rule_set_id: uuid.UUID,
    name: str | object = _UNSET,
    description: str | None | object = _UNSET,
    enabled: bool | object = _UNSET,
) -> RuleSetFileRecord:
    path, record = _find_rule_set_by_id(rule_set_id=rule_set_id)
    if record is None or path is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则集不存在")

    rows = [item for _p, item in _load_all_rule_sets() if item.id != rule_set_id]

    next_name = record.name
    if name is not _UNSET:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise AppError(
                code="INVALID_ARGUMENT", status_code=422, message="规则集名称不能为空"
            )
        if any(item.name.lower() == normalized_name.lower() for item in rows):
            raise AppError(
                code="RULE_SET_ALREADY_EXISTS",
                status_code=409,
                message="规则集名称已存在",
            )
        next_name = normalized_name

    next_description = record.description
    if description is not _UNSET:
        next_description = None if description is None else str(description)

    next_enabled = record.enabled
    if enabled is not _UNSET:
        next_enabled = bool(enabled)

    if (
        next_name == record.name
        and next_description == record.description
        and next_enabled == record.enabled
    ):
        return record

    next_record = RuleSetFileRecord(
        id=record.id,
        key=record.key,
        name=next_name,
        description=next_description,
        enabled=next_enabled,
        rule_keys=list(record.rule_keys),
        created_at=record.created_at,
        updated_at=_now(),
    )
    _write_rule_set(path=path, record=next_record)
    return next_record


def bind_rule_set_rules(
    *,
    rule_set_id: uuid.UUID,
    rule_keys: list[str],
) -> RuleSetFileRecord:
    path, record = _find_rule_set_by_id(rule_set_id=rule_set_id)
    if record is None or path is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则集不存在")

    normalized_rule_keys = _normalize_rule_key_list(rule_keys)
    validated_rule_keys = validate_runtime_rule_keys(
        requested_rule_names=normalized_rule_keys
    )

    next_record = RuleSetFileRecord(
        id=record.id,
        key=record.key,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        rule_keys=validated_rule_keys,
        created_at=record.created_at,
        updated_at=_now(),
    )
    _write_rule_set(path=path, record=next_record)
    return next_record


def resolve_scan_rule_keys(
    *,
    rule_set_keys: list[str],
    rule_keys: list[str],
) -> tuple[list[str], list[str], list[str]]:
    normalized_set_keys = _normalize_rule_set_key_list(rule_set_keys)
    normalized_rule_keys = _normalize_rule_key_list(rule_keys)

    if not normalized_set_keys and not normalized_rule_keys:
        resolved_keys = [item.stem for item in list_runtime_rule_files()]
        return normalized_set_keys, normalized_rule_keys, resolved_keys

    all_rows = [record for _path, record in _load_all_rule_sets()]
    by_key = {item.key.lower(): item for item in all_rows}

    missing_set_keys: list[str] = []
    disabled_set_keys: list[str] = []
    resolved_keys: list[str] = []
    seen_keys: set[str] = set()

    for key in normalized_set_keys:
        record = by_key.get(key.lower())
        if record is None:
            missing_set_keys.append(key)
            continue
        if not record.enabled:
            disabled_set_keys.append(key)
            continue
        for rule_key in record.rule_keys:
            marker = rule_key.lower()
            if marker in seen_keys:
                continue
            seen_keys.add(marker)
            resolved_keys.append(rule_key)

    if missing_set_keys:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_set_keys 中存在不存在的规则集",
            detail={"missing_rule_sets": missing_set_keys},
        )
    if disabled_set_keys:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_set_keys 中包含已停用规则集",
            detail={"disabled_rule_sets": disabled_set_keys},
        )

    for key in normalized_rule_keys:
        marker = key.lower()
        if marker in seen_keys:
            continue
        seen_keys.add(marker)
        resolved_keys.append(key)

    validated_keys = validate_runtime_rule_keys(requested_rule_names=resolved_keys)
    return normalized_set_keys, normalized_rule_keys, validated_keys


def build_rule_set_items(record: RuleSetFileRecord) -> list[RuleSetFileItemRecord]:
    items: list[RuleSetFileItemRecord] = []
    for rule_key in record.rule_keys:
        item_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"codescope-rule-set-item:{record.id}:{rule_key}"
        )
        items.append(
            RuleSetFileItemRecord(
                id=item_id,
                rule_set_id=record.id,
                rule_key=rule_key,
                created_at=record.updated_at,
            )
        )
    return items


def _normalize_rule_set_key_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = (value or "").strip()
        if not raw:
            continue
        key = normalize_rule_set_key(raw)
        marker = key.lower()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(key)
    return cleaned


def _normalize_rule_key_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = (value or "").strip()
        if not raw:
            continue
        key = normalize_rule_selector(raw)
        marker = key.lower()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(key)
    return cleaned


def _find_rule_set_by_id(
    *, rule_set_id: uuid.UUID
) -> tuple[Path | None, RuleSetFileRecord | None]:
    for path, record in _load_all_rule_sets():
        if record.id == rule_set_id:
            return path, record
    return None, None


def _load_all_rule_sets() -> list[tuple[Path, RuleSetFileRecord]]:
    directory = _resolve_rule_sets_dir(allow_missing=True)
    if not directory.exists() or not directory.is_dir():
        return []

    rows: list[tuple[Path, RuleSetFileRecord]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        rows.append((path, _read_rule_set(path)))
    return rows


def _read_rule_set(path: Path) -> RuleSetFileRecord:
    payload = _read_json_dict(path)

    key_raw = str(payload.get("key") or path.stem)
    key = normalize_rule_set_key(key_raw)

    id_raw = payload.get("id")
    try:
        rule_set_id = (
            uuid.UUID(str(id_raw))
            if id_raw is not None
            else uuid.uuid5(uuid.NAMESPACE_URL, f"codescope-rule-set:{key}")
        )
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="RULE_SET_FILE_INVALID",
            status_code=422,
            message="规则集文件 id 无效",
            detail={"path": str(path)},
        ) from exc

    name = str(payload.get("name") or key).strip()
    if not name:
        raise AppError(
            code="RULE_SET_FILE_INVALID",
            status_code=422,
            message="规则集名称不能为空",
            detail={"path": str(path)},
        )

    rules_raw = payload.get("rules")
    if rules_raw is None:
        rules_raw = []
    if not isinstance(rules_raw, list):
        raise AppError(
            code="RULE_SET_FILE_INVALID",
            status_code=422,
            message="规则集 rules 字段必须为数组",
            detail={"path": str(path)},
        )
    rule_keys = _normalize_rule_key_list([str(item) for item in rules_raw])

    created_at = _parse_datetime(payload.get("created_at"), fallback=_mtime(path))
    updated_at = _parse_datetime(payload.get("updated_at"), fallback=_mtime(path))

    return RuleSetFileRecord(
        id=rule_set_id,
        key=key,
        name=name,
        description=(
            None
            if payload.get("description") is None
            else str(payload.get("description"))
        ),
        enabled=bool(payload.get("enabled", True)),
        rule_keys=rule_keys,
        created_at=created_at,
        updated_at=updated_at,
    )


def _write_rule_set(*, path: Path, record: RuleSetFileRecord) -> None:
    payload = {
        "id": str(record.id),
        "key": record.key,
        "name": record.name,
        "description": record.description,
        "enabled": record.enabled,
        "rules": list(record.rule_keys),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    _write_json(path, payload)


def _resolve_rule_sets_dir(
    *, create_missing: bool = False, allow_missing: bool = False
) -> Path:
    settings = get_settings()
    raw = (settings.scan_external_rule_sets_dir or "").strip()
    if not raw:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置规则集目录",
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

    if allow_missing:
        return path

    if not path.exists() or not path.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="规则集目录不存在",
            detail={"rule_sets_dir": str(path)},
        )
    return path


def _rule_set_path(rule_sets_dir: Path, key: str) -> Path:
    return rule_sets_dir / f"{normalize_rule_set_key(key)}.json"


def _read_json_dict(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppError(
            code="RULE_SET_FILE_INVALID",
            status_code=422,
            message="规则集文件解析失败",
            detail={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(
            code="RULE_SET_FILE_INVALID",
            status_code=422,
            message="规则集文件结构不正确",
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


def _now() -> datetime:
    return datetime.now(UTC)
