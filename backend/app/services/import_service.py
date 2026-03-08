from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    ImportJob,
    ImportJobStage,
    ImportJobStatus,
    ImportType,
    Project,
    TaskLogType,
    Version,
    VersionSource,
    VersionStatus,
)
from app.services.audit_service import append_audit_log
from app.services.project_service import refresh_project_status
from app.services.snapshot_storage_service import persist_snapshot_from_directory
from app.services.task_log_service import append_task_log


VALID_GIT_REF_TYPES = {"branch", "tag", "commit"}

FAILURE_HINTS: dict[str, str] = {
    "UPLOAD_TOO_LARGE": "请压缩后重试，或按项目策略拆分上传。",
    "ARCHIVE_INVALID": "请确认上传 zip/tar.gz 且结构完整。",
    "ZIP_SLIP_DETECTED": "压缩包存在非法路径，请修复后重传。",
    "ARCHIVE_BOMB_SUSPECTED": "压缩包解压体积或文件数异常，请检查后重传。",
    "GIT_AUTH_FAILED": "请检查仓库权限、凭据或地址是否正确。",
    "GIT_REF_NOT_FOUND": "请确认分支/Tag/Commit 是否存在。",
    "GIT_NETWORK_ERROR": "请检查网络连通性后重试。",
    "GIT_SYNC_SOURCE_MISSING": "请先执行一次成功的 Git 导入，再进行同步。",
    "CREDENTIAL_PROVIDER_NOT_CONFIGURED": "当前环境未启用凭据提供器，请先使用公开仓库或本地仓路径。",
    "IDEMPOTENCY_KEY_REUSED": "同一个 Idempotency-Key 必须绑定相同请求参数。",
    "IMPORT_DISPATCH_FAILED": "导入任务派发失败，请检查调度器配置后重试。",
    "DB_WRITE_FAILED": "系统写入失败，请稍后重试。",
}


def failure_hint_for_code(failure_code: str | None) -> str | None:
    if failure_code is None:
        return None
    return FAILURE_HINTS.get(failure_code)


def compute_request_fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_existing_idempotent_import_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    idempotency_key: str | None,
    request_fingerprint: str,
) -> ImportJob | None:
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key:
        return None

    existing = db.scalar(
        select(ImportJob).where(
            ImportJob.project_id == project_id,
            ImportJob.idempotency_key == normalized_key,
        )
    )
    if existing is None:
        return None

    if (
        existing.request_fingerprint is not None
        and existing.request_fingerprint != request_fingerprint
    ):
        raise AppError(
            code="IDEMPOTENCY_KEY_REUSED",
            status_code=409,
            message="同一个 Idempotency-Key 不能用于不同参数请求",
        )
    return existing


def _normalize_version_name(value: str | None, *, fallback_prefix: str) -> str:
    if value is not None and value.strip():
        return value.strip()
    return f"{fallback_prefix}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"


def _workspace_dir(job_id: uuid.UUID) -> Path:
    path = Path(get_settings().import_workspace_root) / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_archive_member_path(raw_path: str) -> PurePosixPath:
    raw_normalized = raw_path.replace("\\", "/")
    normalized = PurePosixPath(raw_normalized)
    settings = get_settings()
    if normalized.is_absolute() or ".." in normalized.parts:
        raise AppError(
            code="ZIP_SLIP_DETECTED", status_code=422, message="压缩包包含非法路径"
        )
    if normalized.parts and ":" in normalized.parts[0]:
        raise AppError(
            code="ZIP_SLIP_DETECTED", status_code=422, message="压缩包包含非法路径"
        )
    if len(normalized.parts) > settings.import_archive_max_depth:
        raise AppError(
            code="ARCHIVE_INVALID", status_code=422, message="压缩包目录层级超限"
        )
    if not normalized.parts:
        raise AppError(
            code="ARCHIVE_INVALID", status_code=422, message="压缩包路径为空"
        )
    return normalized


def _enforce_archive_limits(*, file_count: int, total_uncompressed: int) -> None:
    settings = get_settings()
    if file_count > settings.import_archive_max_entries:
        raise AppError(
            code="ARCHIVE_BOMB_SUSPECTED", status_code=422, message="压缩包文件数量超限"
        )
    if total_uncompressed > settings.import_archive_max_uncompressed_bytes:
        raise AppError(
            code="ARCHIVE_BOMB_SUSPECTED",
            status_code=422,
            message="压缩包解压后体积超限",
        )


def _extract_zip(*, archive_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        file_count = 0
        total_uncompressed = 0
        for info in infos:
            safe_rel = _safe_archive_member_path(info.filename)
            if info.is_dir():
                (extract_dir / Path(*safe_rel.parts)).mkdir(parents=True, exist_ok=True)
                continue

            file_count += 1
            total_uncompressed += info.file_size
            _enforce_archive_limits(
                file_count=file_count, total_uncompressed=total_uncompressed
            )

            target = extract_dir / Path(*safe_rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)


def _extract_tar(*, archive_path: Path, extract_dir: Path) -> None:
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        file_count = 0
        total_uncompressed = 0
        for member in members:
            safe_rel = _safe_archive_member_path(member.name)
            if member.issym() or member.islnk():
                raise AppError(
                    code="ARCHIVE_INVALID",
                    status_code=422,
                    message="压缩包不允许符号链接",
                )

            target = extract_dir / Path(*safe_rel.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue

            file_count += 1
            total_uncompressed += member.size
            _enforce_archive_limits(
                file_count=file_count, total_uncompressed=total_uncompressed
            )

            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)


def _extract_archive(*, archive_path: Path, extract_dir: Path) -> None:
    lower_name = archive_path.name.lower()
    if lower_name.endswith(".zip"):
        _extract_zip(archive_path=archive_path, extract_dir=extract_dir)
        return
    if lower_name.endswith(".tar.gz") or lower_name.endswith(".tgz"):
        _extract_tar(archive_path=archive_path, extract_dir=extract_dir)
        return

    raise AppError(
        code="ARCHIVE_INVALID", status_code=422, message="仅支持 zip/tar.gz 文件"
    )


def _resolve_source_root(extract_dir: Path) -> Path:
    children = [item for item in extract_dir.iterdir() if item.name not in {"__MACOSX"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extract_dir


def _create_version_from_source(
    db: Session,
    *,
    project: Project,
    source_dir: Path,
    source: str,
    version_name: str,
    note: str | None,
    git_repo_url: str | None,
    git_ref: str | None,
) -> Version:
    version_id = uuid.uuid4()
    object_key = persist_snapshot_from_directory(
        version_id=version_id, source_dir=source_dir
    )
    version = Version(
        id=version_id,
        project_id=project.id,
        name=version_name,
        source=source,
        note=note,
        git_repo_url=git_repo_url,
        git_ref=git_ref,
        snapshot_object_key=object_key,
        status=VersionStatus.READY.value,
    )
    db.add(version)
    db.flush()
    refresh_project_status(db, project=project)
    return version


def _run_git_command(
    *, args: list[str], timeout: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            code="GIT_NETWORK_ERROR", status_code=422, message="Git 操作超时"
        ) from exc


def _map_git_error(stderr: str) -> AppError:
    lowered = stderr.lower()
    if (
        "authentication failed" in lowered
        or "permission denied" in lowered
        or "could not read username" in lowered
        or "repository not found" in lowered
    ):
        return AppError(code="GIT_AUTH_FAILED", status_code=422, message="Git 认证失败")
    if (
        "pathspec" in lowered
        or "unknown revision" in lowered
        or "did not match any file" in lowered
        or "not found" in lowered
    ):
        return AppError(
            code="GIT_REF_NOT_FOUND", status_code=422, message="Git 引用不存在"
        )
    return AppError(
        code="GIT_NETWORK_ERROR", status_code=422, message="Git 网络或仓库访问失败"
    )


def _set_import_job_running(db: Session, *, job: ImportJob, stage: str) -> None:
    job.status = ImportJobStatus.RUNNING.value
    job.stage = stage
    job.failure_code = None
    _append_import_log(job=job, stage=stage, message=f"进入阶段 {stage}")
    db.commit()


def _fail_import_job(
    db: Session,
    *,
    job: ImportJob,
    stage: str,
    failure_code: str,
    request_id: str,
) -> None:
    job.status = ImportJobStatus.FAILED.value
    job.stage = stage
    job.failure_code = failure_code
    _append_import_log(
        job=job,
        stage=stage,
        message=f"任务失败: code={failure_code}",
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="import.failed",
        resource_type="IMPORT_JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result="FAILED",
        error_code=failure_code,
    )
    db.commit()


def create_import_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    import_type: str,
    payload: dict[str, object],
    created_by: uuid.UUID,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
) -> ImportJob:
    job = ImportJob(
        project_id=project_id,
        import_type=import_type,
        payload=payload,
        created_by=created_by,
        idempotency_key=(idempotency_key or "").strip() or None,
        request_fingerprint=request_fingerprint,
        status=ImportJobStatus.PENDING.value,
        stage=ImportJobStage.VALIDATE.value,
    )
    db.add(job)
    db.flush()
    return job


def dispatch_import_job(db: Session, *, job: ImportJob) -> dict[str, Any]:
    from app.worker.tasks import enqueue_import_job

    bind = db.get_bind()
    bind_engine = getattr(bind, "engine", bind)

    try:
        task_id = enqueue_import_job(import_job_id=job.id, db_bind=bind_engine)
    except Exception as exc:
        raise AppError(
            code="IMPORT_DISPATCH_FAILED",
            status_code=503,
            message="导入任务派发失败",
        ) from exc

    if not task_id:
        raise AppError(
            code="IMPORT_DISPATCH_FAILED",
            status_code=503,
            message="导入任务派发失败",
        )

    dispatch_info: dict[str, Any] = {"backend": "celery", "task_id": task_id}
    refreshed = db.get(ImportJob, job.id)
    if refreshed is not None:
        refreshed.payload = {**(refreshed.payload or {}), "dispatch": dispatch_info}
        _append_import_log(
            job=refreshed,
            stage=refreshed.stage,
            message=f"任务已投递执行队列，task_id={task_id}",
        )
        db.commit()
    return dispatch_info


def mark_import_job_dispatch_failed(
    db: Session,
    *,
    job_id: uuid.UUID,
    request_id: str,
    operator_user_id: uuid.UUID | None,
) -> None:
    job = db.get(ImportJob, job_id)
    if job is None:
        return
    job.status = ImportJobStatus.FAILED.value
    job.stage = ImportJobStage.VALIDATE.value
    job.failure_code = "IMPORT_DISPATCH_FAILED"
    _append_import_log(
        job=job,
        stage=job.stage,
        message="任务派发失败: code=IMPORT_DISPATCH_FAILED",
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="import.dispatch.failed",
        resource_type="IMPORT_JOB",
        resource_id=str(job_id),
        project_id=job.project_id,
        result="FAILED",
        error_code="IMPORT_DISPATCH_FAILED",
    )
    db.commit()


def run_import_job(*, import_job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()

    try:
        job = session.get(ImportJob, import_job_id)
        if job is None:
            return

        if job.status in {
            ImportJobStatus.SUCCEEDED.value,
            ImportJobStatus.FAILED.value,
            ImportJobStatus.CANCELED.value,
            ImportJobStatus.TIMEOUT.value,
        }:
            return

        payload = job.payload if isinstance(job.payload, dict) else {}
        if job.import_type == ImportType.UPLOAD.value:
            run_upload_import_job(
                import_job_id=job.id,
                archive_path=str(payload.get("archive_path") or ""),
                original_filename=str(payload.get("original_filename") or "upload.zip"),
                version_name=(
                    str(payload.get("version_name")).strip()
                    if payload.get("version_name") is not None
                    else None
                ),
                note=(
                    str(payload.get("note")).strip()
                    if payload.get("note") is not None
                    else None
                ),
                db=session,
            )
            return

        if job.import_type == ImportType.GIT.value and bool(payload.get("sync")):
            run_git_sync_job(import_job_id=job.id, db=session)
            return

        if job.import_type == ImportType.GIT.value:
            run_git_import_job(
                import_job_id=job.id,
                repo_url=str(payload.get("repo_url") or ""),
                ref_type=str(payload.get("ref_type") or ""),
                ref_value=str(payload.get("ref_value") or ""),
                version_name=(
                    str(payload.get("version_name")).strip()
                    if payload.get("version_name") is not None
                    else None
                ),
                note=(
                    str(payload.get("note")).strip()
                    if payload.get("note") is not None
                    else None
                ),
                credential_id=(
                    str(payload.get("credential_id")).strip()
                    if payload.get("credential_id") is not None
                    else None
                ),
                db=session,
            )
            return

        _fail_import_job(
            session,
            job=job,
            stage=ImportJobStage.VALIDATE.value,
            failure_code="INVALID_ARGUMENT",
            request_id=str(payload.get("request_id", "")),
        )
    finally:
        if owns_db:
            session.close()


def run_upload_import_job(
    *,
    import_job_id: uuid.UUID,
    archive_path: str,
    original_filename: str,
    version_name: str | None,
    note: str | None,
    db: Session | None = None,
) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    workspace = _workspace_dir(import_job_id)
    extract_dir = workspace / "extract"

    try:
        job = session.get(ImportJob, import_job_id)
        if job is None:
            return
        request_id = str(job.payload.get("request_id", ""))
        project = session.get(Project, job.project_id)
        if project is None:
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="NOT_FOUND",
                request_id=request_id,
            )
            return

        archive_file = Path(archive_path)
        if not archive_file.exists() or not archive_file.is_file():
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="ARCHIVE_INVALID",
                request_id=request_id,
            )
            return

        _set_import_job_running(session, job=job, stage=ImportJobStage.VALIDATE.value)
        _set_import_job_running(session, job=job, stage=ImportJobStage.EXTRACT.value)
        extract_dir.mkdir(parents=True, exist_ok=True)
        _extract_archive(archive_path=archive_file, extract_dir=extract_dir)

        _set_import_job_running(session, job=job, stage=ImportJobStage.ARCHIVE.value)
        source_root = _resolve_source_root(extract_dir)
        resolved_name = _normalize_version_name(version_name, fallback_prefix="upload")
        version = _create_version_from_source(
            session,
            project=project,
            source_dir=source_root,
            source=VersionSource.UPLOAD.value,
            version_name=resolved_name,
            note=note,
            git_repo_url=None,
            git_ref=None,
        )

        job.status = ImportJobStatus.SUCCEEDED.value
        job.stage = ImportJobStage.FINALIZE.value
        job.version_id = version.id
        job.failure_code = None
        job.payload = {
            **job.payload,
            "original_filename": original_filename,
            "version_name": resolved_name,
            "note": note,
            "snapshot_object_key": version.snapshot_object_key,
        }
        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="import.upload.succeeded",
            resource_type="IMPORT_JOB",
            resource_id=str(job.id),
            project_id=job.project_id,
            detail_json={
                "version_id": str(version.id),
                "source": VersionSource.UPLOAD.value,
            },
        )
        _append_import_log(
            job=job,
            stage=ImportJobStage.FINALIZE.value,
            message=f"上传导入完成，version_id={version.id}",
        )
        session.commit()
    except AppError as exc:
        session.rollback()
        job = session.get(ImportJob, import_job_id)
        if job is not None:
            request_id = str(job.payload.get("request_id", ""))
            _fail_import_job(
                session,
                job=job,
                stage=job.stage,
                failure_code=exc.code,
                request_id=request_id,
            )
    except Exception:
        session.rollback()
        job = session.get(ImportJob, import_job_id)
        if job is not None:
            request_id = str(job.payload.get("request_id", ""))
            _fail_import_job(
                session,
                job=job,
                stage=job.stage,
                failure_code="DB_WRITE_FAILED",
                request_id=request_id,
            )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        if owns_db:
            session.close()


def test_git_source(*, repo_url: str, ref_type: str, ref_value: str) -> str:
    normalized_ref_type = ref_type.strip().lower()
    if normalized_ref_type not in VALID_GIT_REF_TYPES:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="ref_type 仅支持 branch/tag/commit",
        )

    timeout = get_settings().git_command_timeout_seconds
    result = _run_git_command(
        args=["git", "ls-remote", "--exit-code", repo_url, ref_value],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise _map_git_error(result.stderr)

    return ref_value


def run_git_import_job(
    *,
    import_job_id: uuid.UUID,
    repo_url: str,
    ref_type: str,
    ref_value: str,
    version_name: str | None,
    note: str | None,
    credential_id: str | None,
    db: Session | None = None,
) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    workspace = _workspace_dir(import_job_id)
    repo_dir = workspace / "repo"
    source_dir = workspace / "source"

    try:
        job = session.get(ImportJob, import_job_id)
        if job is None:
            return
        request_id = str(job.payload.get("request_id", ""))
        project = session.get(Project, job.project_id)
        if project is None:
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="NOT_FOUND",
                request_id=request_id,
            )
            return

        normalized_ref_type = ref_type.strip().lower()
        if normalized_ref_type not in VALID_GIT_REF_TYPES:
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="INVALID_ARGUMENT",
                request_id=request_id,
            )
            return

        _set_import_job_running(session, job=job, stage=ImportJobStage.VALIDATE.value)
        test_git_source(
            repo_url=repo_url, ref_type=normalized_ref_type, ref_value=ref_value
        )

        timeout = get_settings().git_command_timeout_seconds
        _set_import_job_running(session, job=job, stage=ImportJobStage.CHECKOUT.value)
        clone_result = _run_git_command(
            args=["git", "clone", repo_url, str(repo_dir)],
            timeout=timeout,
        )
        if clone_result.returncode != 0:
            raise _map_git_error(clone_result.stderr)

        checkout_result = _run_git_command(
            args=["git", "-C", str(repo_dir), "checkout", ref_value],
            timeout=timeout,
        )
        if checkout_result.returncode != 0:
            raise _map_git_error(checkout_result.stderr)

        rev_parse_result = _run_git_command(
            args=["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            timeout=timeout,
        )
        if rev_parse_result.returncode != 0:
            raise _map_git_error(rev_parse_result.stderr)

        commit_sha = rev_parse_result.stdout.strip()
        shutil.copytree(repo_dir, source_dir, ignore=shutil.ignore_patterns(".git"))

        _set_import_job_running(session, job=job, stage=ImportJobStage.ARCHIVE.value)
        resolved_name = _normalize_version_name(
            version_name, fallback_prefix=f"git-{commit_sha[:8]}"
        )
        version = _create_version_from_source(
            session,
            project=project,
            source_dir=source_dir,
            source=VersionSource.GIT.value,
            version_name=resolved_name,
            note=note,
            git_repo_url=repo_url,
            git_ref=f"{normalized_ref_type}:{ref_value}",
        )

        job.status = ImportJobStatus.SUCCEEDED.value
        job.stage = ImportJobStage.FINALIZE.value
        job.version_id = version.id
        job.failure_code = None
        job.payload = {
            **job.payload,
            "repo_url": repo_url,
            "ref_type": normalized_ref_type,
            "ref_value": ref_value,
            "credential_id": credential_id,
            "resolved_commit": commit_sha,
            "version_name": resolved_name,
            "note": note,
            "snapshot_object_key": version.snapshot_object_key,
        }
        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="import.git.succeeded",
            resource_type="IMPORT_JOB",
            resource_id=str(job.id),
            project_id=job.project_id,
            detail_json={"version_id": str(version.id), "resolved_commit": commit_sha},
        )
        _append_import_log(
            job=job,
            stage=ImportJobStage.FINALIZE.value,
            message=f"Git 导入完成，version_id={version.id}, commit={commit_sha}",
        )
        session.commit()
    except AppError as exc:
        session.rollback()
        job = session.get(ImportJob, import_job_id)
        if job is not None:
            request_id = str(job.payload.get("request_id", ""))
            _fail_import_job(
                session,
                job=job,
                stage=job.stage,
                failure_code=exc.code,
                request_id=request_id,
            )
    except Exception:
        session.rollback()
        job = session.get(ImportJob, import_job_id)
        if job is not None:
            request_id = str(job.payload.get("request_id", ""))
            _fail_import_job(
                session,
                job=job,
                stage=job.stage,
                failure_code="DB_WRITE_FAILED",
                request_id=request_id,
            )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        if owns_db:
            session.close()


def run_git_sync_job(*, import_job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    try:
        job = session.get(ImportJob, import_job_id)
        if job is None:
            return

        previous_job = session.scalar(
            select(ImportJob)
            .where(
                ImportJob.project_id == job.project_id,
                ImportJob.import_type == ImportType.GIT.value,
                ImportJob.status == ImportJobStatus.SUCCEEDED.value,
                ImportJob.id != job.id,
            )
            .order_by(ImportJob.created_at.desc())
        )
        if previous_job is None:
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="GIT_SYNC_SOURCE_MISSING",
                request_id=str(job.payload.get("request_id", "")),
            )
            return

        payload = previous_job.payload
        repo_url = str(payload.get("repo_url", "")).strip()
        ref_type = str(payload.get("ref_type", "")).strip()
        ref_value = str(payload.get("ref_value", "")).strip()
        if not repo_url or not ref_type or not ref_value:
            _fail_import_job(
                session,
                job=job,
                stage=ImportJobStage.VALIDATE.value,
                failure_code="GIT_SYNC_SOURCE_MISSING",
                request_id=str(job.payload.get("request_id", "")),
            )
            return

        note = str(job.payload.get("note", "") or "").strip() or None
    finally:
        if owns_db:
            session.close()

    run_git_import_job(
        import_job_id=import_job_id,
        repo_url=repo_url,
        ref_type=ref_type,
        ref_value=ref_value,
        version_name=None,
        note=note,
        credential_id=None,
        db=None if owns_db else session,
    )


def _append_import_log(*, job: ImportJob, stage: str, message: str) -> None:
    append_task_log(
        task_type=TaskLogType.IMPORT.value,
        task_id=job.id,
        stage=stage,
        message=message,
        project_id=job.project_id,
    )
