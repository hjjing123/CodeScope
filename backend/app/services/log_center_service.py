from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, cast, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import RuntimeLogLevel, SystemLog


@dataclass(frozen=True, slots=True)
class AuditActionMeta:
    action: str
    action_zh: str
    action_group: str
    is_high_value: bool = True


_AUDIT_ACTION_META: dict[str, AuditActionMeta] = {
    "auth.register": AuditActionMeta("auth.register", "注册用户", "auth"),
    "auth.revoke": AuditActionMeta("auth.revoke", "注销会话", "auth"),
    "auth.first_password_reset": AuditActionMeta(
        "auth.first_password_reset", "首次登录重置密码", "auth"
    ),
    "project.create": AuditActionMeta("project.create", "创建项目", "project"),
    "project.update": AuditActionMeta("project.update", "更新项目", "project"),
    "project.delete": AuditActionMeta("project.delete", "删除项目", "project"),
    "project.member.add": AuditActionMeta(
        "project.member.add", "添加项目成员", "project"
    ),
    "project.member.update": AuditActionMeta(
        "project.member.update", "更新项目成员角色", "project"
    ),
    "project.member.remove": AuditActionMeta(
        "project.member.remove", "移除项目成员", "project"
    ),
    "version.create": AuditActionMeta("version.create", "创建代码快照", "version"),
    "version.archive": AuditActionMeta("version.archive", "归档代码快照", "version"),
    "version.delete": AuditActionMeta("version.delete", "删除代码快照", "version"),
    "scan.triggered": AuditActionMeta("scan.triggered", "触发扫描", "scan"),
    "scan.retry.triggered": AuditActionMeta("scan.retry.triggered", "重试扫描", "scan"),
    "scan.succeeded": AuditActionMeta("scan.succeeded", "扫描成功", "scan"),
    "scan.failed": AuditActionMeta("scan.failed", "扫描失败", "scan"),
    "scan.canceled": AuditActionMeta("scan.canceled", "取消扫描", "scan"),
    "scan.deleted": AuditActionMeta("scan.deleted", "删除扫描任务内容", "scan"),
    "import.upload.triggered": AuditActionMeta(
        "import.upload.triggered", "触发上传导入", "import"
    ),
    "import.upload.succeeded": AuditActionMeta(
        "import.upload.succeeded", "上传导入成功", "import"
    ),
    "import.upload.failed": AuditActionMeta(
        "import.upload.failed", "上传导入失败", "import"
    ),
    "import.git.triggered": AuditActionMeta(
        "import.git.triggered", "触发 Git 导入", "import"
    ),
    "import.git.sync.triggered": AuditActionMeta(
        "import.git.sync.triggered", "触发 Git 同步导入", "import"
    ),
    "import.dispatch.failed": AuditActionMeta(
        "import.dispatch.failed", "导入派发失败", "import"
    ),
    "import.git.succeeded": AuditActionMeta(
        "import.git.succeeded", "Git 导入成功", "import"
    ),
    "import.failed": AuditActionMeta("import.failed", "导入失败", "import"),
    "rule.create": AuditActionMeta("rule.create", "创建规则", "rule"),
    "rule.draft.update": AuditActionMeta("rule.draft.update", "更新规则草稿", "rule"),
    "rule.publish": AuditActionMeta("rule.publish", "发布规则", "rule"),
    "rule.rollback": AuditActionMeta("rule.rollback", "回滚规则版本", "rule"),
    "rule.toggle": AuditActionMeta("rule.toggle", "切换规则启停", "rule"),
    "rule.selftest.triggered": AuditActionMeta(
        "rule.selftest.triggered", "触发规则自测", "rule"
    ),
    "rule.selftest.upload.triggered": AuditActionMeta(
        "rule.selftest.upload.triggered", "触发上传样本自测", "rule"
    ),
    "rule.selftest.succeeded": AuditActionMeta(
        "rule.selftest.succeeded", "规则自测成功", "rule"
    ),
    "rule.selftest.failed": AuditActionMeta(
        "rule.selftest.failed", "规则自测失败", "rule"
    ),
    "rule.selftest.dispatch.failed": AuditActionMeta(
        "rule.selftest.dispatch.failed", "规则自测派发失败", "rule"
    ),
    "rule_set.create": AuditActionMeta("rule_set.create", "创建规则集", "rule_set"),
    "rule_set.update": AuditActionMeta("rule_set.update", "更新规则集", "rule_set"),
    "rule_set.bind_rules": AuditActionMeta(
        "rule_set.bind_rules", "绑定规则集规则", "rule_set"
    ),
    "finding.label": AuditActionMeta("finding.label", "标记漏洞", "finding"),
    "user.update": AuditActionMeta("user.update", "更新用户信息", "user"),
    "log.delete": AuditActionMeta("log.delete", "删除日志", "log"),
}


def resolve_audit_action_meta(action: str) -> AuditActionMeta:
    normalized = (action or "").strip()
    if normalized in _AUDIT_ACTION_META:
        return _AUDIT_ACTION_META[normalized]
    group = normalized.split(".", 1)[0] if normalized else "other"
    return AuditActionMeta(
        action=normalized or "unknown",
        action_zh=normalized or "未知动作",
        action_group=group or "other",
        is_high_value=True,
    )


def normalize_audit_detail(
    *, action: str, detail_json: dict[str, object] | None
) -> dict[str, object]:
    payload = detail_json or {}
    context: dict[str, object] = {}
    change: dict[str, object] = {}
    outcome: dict[str, object] = {}
    if isinstance(payload.get("context"), dict):
        context = dict(payload["context"])
    if isinstance(payload.get("change"), dict):
        change = dict(payload["change"])
    if isinstance(payload.get("outcome"), dict):
        outcome = dict(payload["outcome"])

    has_standard = bool(context or change or outcome)
    if not has_standard:
        context = {
            key: value
            for key, value in payload.items()
            if key not in {"before", "after", "result", "success"}
        }
        if "before" in payload or "after" in payload:
            change = {
                "before": payload.get("before"),
                "after": payload.get("after"),
            }
        if "result" in payload:
            outcome["result"] = payload.get("result")
        if "success" in payload:
            outcome["success"] = payload.get("success")

    if action == "rule.toggle":
        before_enabled = context.get("before_enabled")
        if before_enabled is None:
            before_enabled = payload.get("before_enabled")
        after_enabled = change.get("after_enabled")
        if after_enabled is None:
            after_enabled = payload.get("enabled")
        context["rule_key"] = str(
            context.get("rule_key")
            or payload.get("rule_key")
            or payload.get("resource_id")
            or ""
        )
        change["before_enabled"] = (
            bool(before_enabled) if before_enabled is not None else None
        )
        change["after_enabled"] = bool(after_enabled)
        outcome.setdefault("status", "SUCCEEDED")

    return {"context": context, "change": change, "outcome": outcome}


def build_audit_summary_zh(*, action: str, detail_json: dict[str, object]) -> str:
    normalized = normalize_audit_detail(action=action, detail_json=detail_json)
    meta = resolve_audit_action_meta(action)
    context = normalized.get("context")
    change = normalized.get("change")
    if action == "rule.toggle" and isinstance(change, dict):
        after_enabled = change.get("after_enabled")
        state = "启用" if after_enabled else "停用"
        rule_key = ""
        if isinstance(context, dict):
            rule_key = str(context.get("rule_key") or "")
        if rule_key:
            return f"规则 {rule_key} 已{state}"
        return f"规则状态已切换为{state}"
    return meta.action_zh


def normalize_action_groups(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    groups = [item.strip().lower() for item in raw_value.split(",")]
    return [item for item in groups if item]


def resolve_action_zh(*, action: str | None, action_zh: str | None) -> str:
    normalized_action = (action or "").strip()
    normalized_action_zh = (action_zh or "").strip()
    if normalized_action_zh and normalized_action_zh != normalized_action:
        return normalized_action_zh
    if normalized_action:
        return resolve_audit_action_meta(normalized_action).action_zh
    return normalized_action_zh


def build_log_keyword_condition(keyword: str) -> ColumnElement[bool]:
    token = f"%{keyword.strip()}%"
    return or_(
        SystemLog.action.ilike(token),
        SystemLog.action_zh.ilike(token),
        SystemLog.summary_zh.ilike(token),
        SystemLog.message.ilike(token),
        SystemLog.event.ilike(token),
        SystemLog.resource_id.ilike(token),
        SystemLog.error_code.ilike(token),
        cast(SystemLog.detail_json, String).ilike(token),
    )


def is_high_value_runtime_log(
    *,
    level: str,
    status_code: int | None,
    duration_ms: int | None,
    explicit_high_value: bool | None = None,
) -> bool:
    if explicit_high_value is not None:
        return explicit_high_value
    normalized_level = (level or "").strip().upper()
    if normalized_level in {RuntimeLogLevel.WARN.value, RuntimeLogLevel.ERROR.value}:
        return True
    if status_code is not None and status_code >= 400:
        return True
    if duration_ms is not None and duration_ms >= 1000:
        return True
    return False


def should_record_runtime_request(
    *,
    status_code: int,
    duration_ms: int,
    request_id: str,
    path: str,
    sample_rate: float,
    slow_threshold_ms: int,
    record_success: bool,
) -> tuple[bool, bool, str]:
    if status_code >= 400:
        return True, True, "error"
    if duration_ms >= max(1, slow_threshold_ms):
        return True, True, "slow"
    if not record_success and sample_rate <= 0:
        return False, False, "skip_success"
    if record_success:
        return True, False, "success_all"
    normalized_rate = min(max(sample_rate, 0.0), 1.0)
    if normalized_rate <= 0:
        return False, False, "skip_sample"
    key = f"{request_id}:{path}"
    ratio = (abs(hash(key)) % 10000) / 10000
    if ratio <= normalized_rate:
        return True, False, "sampled"
    return False, False, "skip_sample"


def summarize_log_delete_scope(
    *,
    log_kind: str | None,
    action_groups: list[str],
    high_value_only: bool,
    keyword: str | None,
    request_id: str | None,
    task_type: str | None,
    task_id: str | None,
    project_id: str | None,
) -> dict[str, Any]:
    return {
        "log_kind": log_kind,
        "action_groups": action_groups,
        "high_value_only": high_value_only,
        "keyword": keyword or "",
        "request_id": request_id or "",
        "task_type": task_type or "",
        "task_id": task_id or "",
        "project_id": project_id or "",
    }


def fill_system_log_meta_for_existing_row(row: Any) -> tuple[str, str, str, bool]:
    action = str(getattr(row, "action", "") or "")
    detail_json = getattr(row, "detail_json", {}) or {}
    meta = resolve_audit_action_meta(action)
    summary_zh = build_audit_summary_zh(action=action, detail_json=detail_json)
    return meta.action_zh, meta.action_group, summary_zh, meta.is_high_value


def normalize_audit_row_detail(
    detail_json: dict[str, object] | None, action: str
) -> dict[str, object]:
    return normalize_audit_detail(action=action, detail_json=detail_json)


def coalesce_json(data: Any) -> dict[str, object]:
    if isinstance(data, dict):
        return data
    return {}


def normalize_runtime_sample_rate(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def build_log_delete_outcome(*, deleted_count: int) -> dict[str, object]:
    return {"deleted_count": deleted_count}


def to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_text_summary_expr() -> ColumnElement[str]:
    return func.coalesce(SystemLog.summary_zh, "")
