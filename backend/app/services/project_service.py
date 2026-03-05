from __future__ import annotations

import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ImportJob,
    Job,
    Project,
    ProjectStatus,
    TaskLogIndex,
    Version,
    VersionStatus,
)


def refresh_project_status(db: Session, *, project: Project) -> None:
    db.flush()

    ready_count = (
        db.scalar(
            select(func.count())
            .select_from(Version)
            .where(
                Version.project_id == project.id,
                Version.status == VersionStatus.READY.value,
            )
        )
        or 0
    )
    if ready_count > 0:
        project.status = ProjectStatus.SCANNABLE.value
        return

    existing_count = (
        db.scalar(
            select(func.count())
            .select_from(Version)
            .where(
                Version.project_id == project.id,
                Version.status != VersionStatus.DELETED.value,
            )
        )
        or 0
    )
    if existing_count > 0:
        project.status = ProjectStatus.IMPORTED.value
        return

    project.status = ProjectStatus.NEW.value


def collect_project_resource_ids(
    db: Session, *, project_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
    version_ids = db.scalars(
        select(Version.id).where(Version.project_id == project_id)
    ).all()
    job_ids = db.scalars(select(Job.id).where(Job.project_id == project_id)).all()
    import_job_ids = db.scalars(
        select(ImportJob.id).where(ImportJob.project_id == project_id)
    ).all()
    return version_ids, job_ids, import_job_ids


def cleanup_project_task_log_index(db: Session, *, project_id: uuid.UUID) -> None:
    db.execute(delete(TaskLogIndex).where(TaskLogIndex.project_id == project_id))


def cleanup_project_local_artifacts(
    *,
    version_ids: Sequence[uuid.UUID],
    job_ids: Sequence[uuid.UUID],
    import_job_ids: Sequence[uuid.UUID],
) -> None:
    settings = get_settings()

    _cleanup_dirs(Path(settings.snapshot_storage_root), version_ids)
    _cleanup_dirs(Path(settings.scan_log_root), job_ids)
    _cleanup_dirs(Path(settings.scan_workspace_root), job_ids)
    _cleanup_dirs(Path(settings.import_log_root), import_job_ids)
    _cleanup_dirs(Path(settings.import_workspace_root), import_job_ids)


def _cleanup_dirs(root: Path, ids: Sequence[uuid.UUID]) -> None:
    for resource_id in ids:
        shutil.rmtree(root / str(resource_id), ignore_errors=True)
