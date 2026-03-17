from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import (
    require_project_action,
    require_project_resource_action,
)
from app.models import Project, Version, VersionSource, VersionStatus
from app.schemas.version import (
    VersionCreateRequest,
    VersionFilePayload,
    VersionListPayload,
    VersionPayload,
    VersionTreeEntryPayload,
    VersionTreePayload,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.project_service import refresh_project_status
from app.services.snapshot_storage_service import (
    get_snapshot_archive_path,
    list_snapshot_tree,
    materialize_snapshot_from_object_key,
    read_snapshot_file,
)


router = APIRouter(tags=["versions"])


def _get_existing_version(
    *, db: Session, version_id: uuid.UUID, allow_deleted: bool = False
) -> Version:
    version = db.get(Version, version_id)
    if version is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="代码快照不存在")
    if not allow_deleted and version.status == VersionStatus.DELETED.value:
        raise AppError(code="NOT_FOUND", status_code=404, message="代码快照不存在")
    return version


def _validate_version_source(source: str) -> str:
    valid = {item.value for item in VersionSource}
    if source not in valid:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="代码来源值不合法",
            detail={"allowed_sources": sorted(valid)},
        )
    return source


def _version_payload(*, version: Version) -> VersionPayload:
    return VersionPayload(
        id=version.id,
        project_id=version.project_id,
        name=version.name,
        source=version.source,
        note=version.note,
        tag=version.tag,
        git_repo_url=version.git_repo_url,
        git_ref=version.git_ref,
        snapshot_object_key=version.snapshot_object_key,
        status=version.status,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


@router.get("/api/v1/projects/{project_id}/versions")
def list_versions(
    request: Request,
    project_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_project_action("version:read")),
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 200)

    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    conditions = [
        Version.project_id == project_id,
        Version.status != VersionStatus.DELETED.value,
    ]
    total = db.scalar(select(func.count()).select_from(Version).where(*conditions)) or 0
    rows = db.scalars(
        select(Version)
        .where(*conditions)
        .order_by(Version.created_at.desc())
        .offset((safe_page - 1) * safe_size)
        .limit(safe_size)
    ).all()

    data = VersionListPayload(
        items=[_version_payload(version=item) for item in rows],
        total=total,
    )
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/projects/{project_id}/versions")
def create_version(
    request: Request,
    project_id: uuid.UUID,
    payload: VersionCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("version:create")),
):
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    source = _validate_version_source(payload.source)

    if payload.snapshot_object_key is None or not payload.snapshot_object_key.strip():
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="创建代码快照时必须提供 snapshot_object_key",
        )

    version_name = payload.name.strip()
    if not version_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="代码快照名称不能为空",
        )

    version_id = uuid.uuid4()
    snapshot_object_key = materialize_snapshot_from_object_key(
        version_id=version_id,
        snapshot_object_key=payload.snapshot_object_key,
    )

    version = Version(
        id=version_id,
        project_id=project_id,
        name=version_name,
        source=source,
        note=payload.note,
        tag=payload.tag,
        git_repo_url=payload.git_repo_url,
        git_ref=payload.git_ref,
        snapshot_object_key=snapshot_object_key,
        status=VersionStatus.READY.value,
    )
    db.add(version)
    db.flush()
    refresh_project_status(db, project=project)

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="version.create",
        resource_type="VERSION",
        resource_id=str(version.id),
        project_id=project_id,
        detail_json={
            "source": source,
            "snapshot_object_key": version.snapshot_object_key,
        },
    )

    db.commit()
    db.refresh(version)
    db.refresh(project)
    return success_response(
        request,
        data=_version_payload(version=version).model_dump(),
        status_code=201,
    )


@router.get("/api/v1/versions/{version_id}")
def get_version(
    request: Request,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:read",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)
    return success_response(
        request,
        data=_version_payload(version=version).model_dump(),
    )


@router.post("/api/v1/versions/{version_id}/archive")
def archive_version(
    request: Request,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:archive",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)

    project = db.get(Project, version.project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    version.status = VersionStatus.ARCHIVED.value
    refresh_project_status(db, project=project)

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="version.archive",
        resource_type="VERSION",
        resource_id=str(version.id),
        project_id=project.id,
    )
    db.commit()
    return success_response(request, data={"archived": True})


@router.delete("/api/v1/versions/{version_id}")
def delete_version(
    request: Request,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:archive",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)

    project = db.get(Project, version.project_id)
    version.status = VersionStatus.DELETED.value
    if project is not None:
        refresh_project_status(db, project=project)

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="version.delete",
        resource_type="VERSION",
        resource_id=str(version.id),
        project_id=version.project_id,
    )
    db.commit()
    return success_response(request, data={"deleted": True})


@router.get("/api/v1/versions/{version_id}/tree")
def version_tree(
    request: Request,
    version_id: uuid.UUID,
    path: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:read",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)

    items = list_snapshot_tree(version_id=version.id, path=path)
    data = VersionTreePayload(
        root_path=(path or ""),
        items=[VersionTreeEntryPayload(**item) for item in items],
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/versions/{version_id}/file")
def version_file(
    request: Request,
    version_id: uuid.UUID,
    path: str,
    full: bool = Query(default=False),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:read",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)

    content, truncated, total_lines = read_snapshot_file(
        version_id=version.id, path=path, full=full
    )
    data = VersionFilePayload(
        path=path, content=content, truncated=truncated, total_lines=total_lines
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/versions/{version_id}/download")
def download_version_snapshot(
    request: Request,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "version:read",
            resource_type="VERSION",
            resource_id_param="version_id",
        )
    ),
):
    version = _get_existing_version(db=db, version_id=version_id)

    archive_path = get_snapshot_archive_path(version_id=version.id)
    return FileResponse(
        path=archive_path,
        media_type="application/gzip",
        filename=f"version_{version.id}_snapshot.tar.gz",
    )
