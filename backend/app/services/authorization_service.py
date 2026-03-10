from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden_error
from app.models import (
    Finding,
    ImportJob,
    Job,
    Project,
    ProjectRole,
    Report,
    SystemRole,
    UserProjectRole,
    Version,
)


ROLE_ACTIONS: dict[str, set[str]] = {
    SystemRole.ADMIN.value: {
        "project:read",
        "project:write",
        "project:delete",
        "version:read",
        "version:create",
        "version:archive",
        "job:read",
        "job:create",
        "job:cancel",
        "job:retry",
        "job:delete",
        "finding:read",
        "finding:label",
        "rule:read",
        "rule:write",
        "rule:publish",
        "rule:toggle",
        "rule:selftest",
        "report:read",
        "report:generate",
        "report:publish",
        "system:config",
        "system:auditlog",
    },
    SystemRole.USER.value: {
        "project:read",
        "project:write",
        "project:delete",
        "version:read",
        "version:create",
        "job:read",
        "job:create",
        "job:cancel",
        "job:retry",
        "job:delete",
        "finding:read",
        "finding:label",
        "report:read",
        "report:generate",
        "rule:read",
    },
}

PROJECT_ROLE_ACTIONS: dict[str, set[str]] = {
    ProjectRole.OWNER.value: {
        "project:read",
        "project:write",
        "project:delete",
        "version:read",
        "version:create",
        "version:archive",
        "job:read",
        "job:create",
        "job:cancel",
        "job:retry",
        "job:delete",
        "finding:read",
        "finding:label",
        "report:read",
        "report:generate",
        "report:publish",
    },
    ProjectRole.MAINTAINER.value: {
        "project:read",
        "project:write",
        "version:read",
        "version:create",
        "job:read",
        "job:create",
        "job:cancel",
        "job:retry",
        "job:delete",
        "finding:read",
        "finding:label",
        "report:read",
        "report:generate",
    },
    ProjectRole.READER.value: {
        "project:read",
        "version:read",
        "job:read",
        "finding:read",
        "finding:label",
        "report:read",
    },
}


def _parse_uuid_resource(*, value: str | uuid.UUID, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="资源标识格式不正确",
            detail={"field": field_name},
        ) from exc


def resolve_project_id(
    *, db: Session, resource_type: str, resource_id: str | uuid.UUID
) -> uuid.UUID:
    normalized = resource_type.strip().upper()

    if normalized == "PROJECT":
        project_id = _parse_uuid_resource(value=resource_id, field_name="project_id")
        project = db.get(Project, project_id)
        if project is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")
        return project_id

    if normalized in {"PROJECT_MEMBER", "USER_PROJECT_ROLE", "MEMBERSHIP"}:
        member_id = _parse_uuid_resource(value=resource_id, field_name="member_id")
        project_id = db.scalar(
            select(UserProjectRole.project_id).where(UserProjectRole.id == member_id)
        )
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="项目成员不存在")
        return project_id

    if normalized == "VERSION":
        version_id = _parse_uuid_resource(value=resource_id, field_name="version_id")
        project_id = db.scalar(
            select(Version.project_id).where(Version.id == version_id)
        )
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="版本不存在")
        return project_id

    if normalized == "JOB":
        job_id = _parse_uuid_resource(value=resource_id, field_name="job_id")
        project_id = db.scalar(select(Job.project_id).where(Job.id == job_id))
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
        return project_id

    if normalized == "FINDING":
        finding_id = _parse_uuid_resource(value=resource_id, field_name="finding_id")
        project_id = db.scalar(
            select(Finding.project_id).where(Finding.id == finding_id)
        )
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
        return project_id

    if normalized == "REPORT":
        report_id = _parse_uuid_resource(value=resource_id, field_name="report_id")
        project_id = db.scalar(select(Report.project_id).where(Report.id == report_id))
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="报告不存在")
        return project_id

    if normalized == "IMPORT_JOB":
        import_job_id = _parse_uuid_resource(value=resource_id, field_name="job_id")
        project_id = db.scalar(
            select(ImportJob.project_id).where(ImportJob.id == import_job_id)
        )
        if project_id is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="导入任务不存在")
        return project_id

    raise AppError(
        code="RESOURCE_TYPE_UNSUPPORTED",
        status_code=422,
        message="暂不支持该资源类型的项目归属解析",
        detail={"resource_type": resource_type},
    )


def ensure_platform_action(*, role: str, action: str) -> None:
    if role == SystemRole.ADMIN.value:
        return

    if action.startswith("system:"):
        raise forbidden_error(message="当前角色无平台级权限", code="INSUFFICIENT_SCOPE")

    allowed = ROLE_ACTIONS.get(role, set())
    if action not in allowed:
        raise forbidden_error()


def ensure_project_action(
    *,
    db: Session,
    user_id: uuid.UUID,
    role: str,
    project_id: uuid.UUID,
    action: str,
) -> UserProjectRole | None:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    if role == SystemRole.ADMIN.value:
        return None

    ensure_platform_action(role=role, action=action)
    membership = db.scalar(
        select(UserProjectRole).where(
            UserProjectRole.user_id == user_id,
            UserProjectRole.project_id == project_id,
        )
    )
    if membership is None:
        raise forbidden_error(
            message="当前用户不是该项目成员", code="PROJECT_MEMBERSHIP_REQUIRED"
        )

    project_allowed = PROJECT_ROLE_ACTIONS.get(membership.project_role, set())
    if action not in project_allowed:
        raise forbidden_error()

    return membership


def ensure_resource_action(
    *,
    db: Session,
    user_id: uuid.UUID,
    role: str,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID,
) -> UserProjectRole | None:
    project_id = resolve_project_id(
        db=db, resource_type=resource_type, resource_id=resource_id
    )
    return ensure_project_action(
        db=db,
        user_id=user_id,
        role=role,
        project_id=project_id,
        action=action,
    )


def list_context_actions(
    *,
    db: Session,
    user_id: uuid.UUID,
    role: str,
    project_id: uuid.UUID | None = None,
) -> tuple[set[str], str | None]:
    role_actions = set(ROLE_ACTIONS.get(role, set()))

    if project_id is None:
        return role_actions, None

    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    if role == SystemRole.ADMIN.value:
        return set(
            PROJECT_ROLE_ACTIONS[ProjectRole.OWNER.value]
        ), ProjectRole.OWNER.value

    membership = db.scalar(
        select(UserProjectRole).where(
            UserProjectRole.user_id == user_id,
            UserProjectRole.project_id == project_id,
        )
    )
    if membership is None:
        raise forbidden_error(
            message="当前用户不是该项目成员", code="PROJECT_MEMBERSHIP_REQUIRED"
        )

    project_actions = set(PROJECT_ROLE_ACTIONS.get(membership.project_role, set()))
    return role_actions.intersection(project_actions), membership.project_role
