from __future__ import annotations

import io
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.models import (
    ImportJobStage,
    JobStage,
    SelfTestJobStage,
    TaskLogIndex,
    TaskLogType,
)

try:
    from minio import Minio
except Exception:  # pragma: no cover - optional dependency in local dev
    Minio = None

try:
    import urllib3
except Exception:  # pragma: no cover - optional dependency in local dev
    urllib3 = None


TASK_ALLOWED_STAGES: dict[str, list[str]] = {
    TaskLogType.SCAN.value: [
        JobStage.PREPARE.value,
        JobStage.ANALYZE.value,
        JobStage.QUERY.value,
        JobStage.AGGREGATE.value,
        JobStage.AI.value,
        JobStage.CLEANUP.value,
    ],
    TaskLogType.IMPORT.value: [
        ImportJobStage.VALIDATE.value,
        ImportJobStage.EXTRACT.value,
        ImportJobStage.CHECKOUT.value,
        ImportJobStage.ARCHIVE.value,
        ImportJobStage.FINALIZE.value,
    ],
    TaskLogType.AI.value: [
        JobStage.PREPARE.value,
        JobStage.AI.value,
        JobStage.CLEANUP.value,
    ],
    TaskLogType.OLLAMA_PULL.value: [
        "Prepare",
        "Pull",
        "Verify",
        "Finalize",
    ],
    TaskLogType.SELFTEST.value: [
        SelfTestJobStage.PREPARE.value,
        SelfTestJobStage.EXECUTE.value,
        SelfTestJobStage.AGGREGATE.value,
        SelfTestJobStage.CLEANUP.value,
    ],
}


def append_task_log(
    *,
    task_type: str,
    task_id: uuid.UUID,
    stage: str,
    message: str,
    project_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    normalized_task_type = _normalize_task_type(task_type)
    resolved_stage = _resolve_stages(task_type=normalized_task_type, stage=stage)[0]

    try:
        path = _task_stage_local_path(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=resolved_stage,
            create=True,
        )
        timestamp = datetime.utcnow().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as fp:
            fp.write(f"[{timestamp}] {message}\n")

        _upload_stage_log_to_minio(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=resolved_stage,
            path=path,
        )
        if db is not None:
            sync_task_log_index(
                task_type=normalized_task_type,
                task_id=task_id,
                project_id=project_id,
                db=db,
            )
    except Exception:
        return


def read_task_logs(
    *,
    task_type: str,
    task_id: uuid.UUID,
    stage: str | None,
    tail: int | None,
) -> list[dict[str, object]]:
    normalized_task_type = _normalize_task_type(task_type)
    safe_tail: int | None = None
    if tail is not None:
        raw_tail = int(tail)
        if raw_tail > 0:
            safe_tail = min(raw_tail, 5000)
    stages = _resolve_stages(task_type=normalized_task_type, stage=stage)

    items: list[dict[str, object]] = []
    for stage_name in stages:
        content = _read_stage_bytes(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=stage_name,
        )
        if content is None:
            continue
        lines = content.decode("utf-8", errors="replace").splitlines()
        line_count = len(lines)
        selected_lines = lines if safe_tail is None else lines[-safe_tail:]
        items.append(
            {
                "stage": stage_name,
                "lines": selected_lines,
                "line_count": line_count,
                "truncated": safe_tail is not None and line_count > safe_tail,
            }
        )
    return items


def read_task_log_events(
    *,
    task_type: str,
    task_id: uuid.UUID,
    stage: str | None,
    after_seq: int = 0,
    limit: int = 1000,
) -> list[dict[str, object]]:
    normalized_task_type = _normalize_task_type(task_type)
    safe_after_seq = max(0, int(after_seq))
    safe_limit = min(max(1, int(limit)), 5000)
    stages = _resolve_stages(task_type=normalized_task_type, stage=stage)

    events: list[dict[str, object]] = []
    seq = 0
    for stage_name in stages:
        content = _read_stage_bytes(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=stage_name,
        )
        if content is None:
            continue
        lines = content.decode("utf-8", errors="replace").splitlines()
        for line in lines:
            seq += 1
            if seq <= safe_after_seq:
                continue
            parsed = _parse_log_line(line)
            events.append(
                {
                    "seq": seq,
                    "stage": stage_name,
                    "step_key": _infer_step_key(parsed["message"]),
                    "timestamp": parsed["timestamp"],
                    "line": parsed["message"],
                    "raw_line": line,
                }
            )
            if len(events) >= safe_limit:
                return events
    return events


def build_task_stage_log_bytes(
    *, task_type: str, task_id: uuid.UUID, stage: str
) -> bytes:
    normalized_task_type = _normalize_task_type(task_type)
    stage_name = _resolve_stages(task_type=normalized_task_type, stage=stage)[0]
    content = _read_stage_bytes(
        task_type=normalized_task_type, task_id=task_id, stage=stage_name
    )
    if content is None:
        raise AppError(
            code="TASK_LOG_NOT_FOUND", status_code=404, message="任务阶段日志不存在"
        )
    return content


def build_task_logs_zip_bytes(*, task_type: str, task_id: uuid.UUID) -> bytes:
    normalized_task_type = _normalize_task_type(task_type)
    files: list[tuple[str, bytes]] = []
    for stage in TASK_ALLOWED_STAGES[normalized_task_type]:
        content = _read_stage_bytes(
            task_type=normalized_task_type, task_id=task_id, stage=stage
        )
        if content is None:
            continue
        files.append((f"{_safe_stage_name(stage)}.log", content))

    if not files:
        raise AppError(
            code="TASK_LOG_NOT_FOUND", status_code=404, message="任务日志不存在"
        )

    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    return buffer.getvalue()


def get_task_stage_log_path(*, task_type: str, task_id: uuid.UUID, stage: str) -> Path:
    normalized_task_type = _normalize_task_type(task_type)
    stage_name = _resolve_stages(task_type=normalized_task_type, stage=stage)[0]
    path = _task_stage_local_path(
        task_type=normalized_task_type,
        task_id=task_id,
        stage=stage_name,
        create=False,
    )
    if path is None or not path.exists() or not path.is_file():
        raise AppError(
            code="TASK_LOG_NOT_FOUND", status_code=404, message="任务阶段日志不存在"
        )
    return path


def sync_task_log_index(
    *,
    task_type: str,
    task_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    if db is None:
        return

    normalized_task_type = _normalize_task_type(task_type)
    try:
        present_stages: set[str] = set()
        for stage in TASK_ALLOWED_STAGES[normalized_task_type]:
            content = _read_stage_bytes(
                task_type=normalized_task_type,
                task_id=task_id,
                stage=stage,
            )
            if content is None:
                continue

            present_stages.add(stage)
            line_count = len(content.decode("utf-8", errors="replace").splitlines())
            size_bytes = len(content)
            storage_backend, object_key = _resolve_storage_reference(
                task_type=normalized_task_type,
                task_id=task_id,
                stage=stage,
            )
            existing = db.scalar(
                select(TaskLogIndex).where(
                    TaskLogIndex.task_type == normalized_task_type,
                    TaskLogIndex.task_id == task_id,
                    TaskLogIndex.stage == stage,
                )
            )
            if existing is None:
                db.add(
                    TaskLogIndex(
                        task_type=normalized_task_type,
                        task_id=task_id,
                        project_id=project_id,
                        stage=stage,
                        line_count=line_count,
                        size_bytes=size_bytes,
                        truncated=False,
                        storage_backend=storage_backend,
                        object_key=object_key,
                    )
                )
            else:
                if project_id is not None:
                    existing.project_id = project_id
                existing.line_count = line_count
                existing.size_bytes = size_bytes
                existing.truncated = False
                existing.storage_backend = storage_backend
                existing.object_key = object_key

        stale_rows = db.scalars(
            select(TaskLogIndex).where(
                TaskLogIndex.task_type == normalized_task_type,
                TaskLogIndex.task_id == task_id,
            )
        ).all()
        for row in stale_rows:
            if row.stage not in present_stages:
                db.delete(row)

        db.commit()
    except Exception:
        db.rollback()


def delete_task_logs(
    *, task_type: str, task_id: uuid.UUID, db: Session | None = None
) -> dict[str, int]:
    normalized_task_type = _normalize_task_type(task_type)
    deleted_log_files_count = 0
    deleted_task_log_index_count = 0

    for stage in TASK_ALLOWED_STAGES[normalized_task_type]:
        local_path = _task_stage_local_path(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=stage,
            create=False,
        )
        if local_path is not None and local_path.exists() and local_path.is_file():
            try:
                local_path.unlink()
                deleted_log_files_count += 1
            except OSError:
                pass

        object_key = _task_stage_object_key(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=stage,
        )
        _delete_from_minio(object_key)

    log_dir = _task_log_dir(
        task_type=normalized_task_type, task_id=task_id, create=False
    )
    if log_dir is not None and log_dir.exists() and log_dir.is_dir():
        if not any(log_dir.iterdir()):
            shutil.rmtree(log_dir, ignore_errors=True)

    if db is not None:
        rows = db.scalars(
            select(TaskLogIndex).where(
                TaskLogIndex.task_type == normalized_task_type,
                TaskLogIndex.task_id == task_id,
            )
        ).all()
        deleted_task_log_index_count = len(rows)
        for row in rows:
            db.delete(row)

    return {
        "deleted_log_files_count": deleted_log_files_count,
        "deleted_task_log_index_count": deleted_task_log_index_count,
    }


def _normalize_task_type(task_type: str) -> str:
    normalized = str(task_type).strip().upper()
    if normalized not in TASK_ALLOWED_STAGES:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="task_type 参数不合法",
            detail={"allowed_task_types": sorted(TASK_ALLOWED_STAGES.keys())},
        )
    return normalized


def _resolve_stages(*, task_type: str, stage: str | None) -> list[str]:
    allowed = TASK_ALLOWED_STAGES[task_type]
    if stage is None:
        return list(allowed)

    normalized = stage.strip().lower()
    for candidate in allowed:
        if candidate.lower() == normalized:
            return [candidate]

    raise AppError(
        code="INVALID_ARGUMENT",
        status_code=422,
        message="stage 参数不合法",
        detail={"allowed_stages": allowed},
    )


def _task_log_root(*, task_type: str) -> Path:
    settings = get_settings()
    normalized = _normalize_task_type(task_type)
    if normalized == TaskLogType.SCAN.value:
        return Path(settings.scan_log_root)
    if normalized == TaskLogType.IMPORT.value:
        return Path(settings.import_log_root)
    if normalized == TaskLogType.AI.value:
        return Path(settings.ai_log_root)
    if normalized == TaskLogType.OLLAMA_PULL.value:
        return Path(settings.ai_log_root)
    return Path(settings.selftest_log_root)


def _task_log_dir(*, task_type: str, task_id: uuid.UUID, create: bool) -> Path | None:
    root = _task_log_root(task_type=task_type)
    path = root / str(task_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
        return path
    if not path.exists() or not path.is_dir():
        return None
    return path


def _safe_stage_name(stage: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stage).strip("_") or "unknown"


def _parse_log_line(line: str) -> dict[str, str]:
    match = re.match(r"^\[(?P<timestamp>[^\]]+)\]\s*(?P<message>.*)$", line)
    if match is None:
        return {"timestamp": "", "message": line}
    timestamp = str(match.group("timestamp") or "").strip()
    message = str(match.group("message") or "").strip()
    return {"timestamp": timestamp, "message": message}


def _infer_step_key(message: str) -> str | None:
    marker = re.match(r"^\[(?P<step_key>[A-Za-z0-9_-]+)\]", message)
    if marker is None:
        return None
    step_key = str(marker.group("step_key") or "").strip().lower()
    return step_key or None


def _task_stage_local_path(
    *,
    task_type: str,
    task_id: uuid.UUID,
    stage: str,
    create: bool,
) -> Path | None:
    safe_stage = _safe_stage_name(stage)
    log_dir = _task_log_dir(task_type=task_type, task_id=task_id, create=create)
    if log_dir is None:
        return None
    return log_dir / f"{safe_stage}.log"


def _task_stage_object_key(*, task_type: str, task_id: uuid.UUID, stage: str) -> str:
    settings = get_settings()
    prefix = settings.task_log_object_prefix.strip("/")
    safe_stage = _safe_stage_name(stage)
    lower_type = task_type.lower()
    if prefix:
        return f"{prefix}/{lower_type}/{task_id}/{safe_stage}.log"
    return f"{lower_type}/{task_id}/{safe_stage}.log"


def _read_stage_bytes(
    *, task_type: str, task_id: uuid.UUID, stage: str
) -> bytes | None:
    normalized_task_type = _normalize_task_type(task_type)
    stage_name = _resolve_stages(task_type=normalized_task_type, stage=stage)[0]

    if _minio_enabled():
        object_key = _task_stage_object_key(
            task_type=normalized_task_type,
            task_id=task_id,
            stage=stage_name,
        )
        data = _download_from_minio(object_key)
        if data is not None:
            return data

    local_path = _task_stage_local_path(
        task_type=normalized_task_type,
        task_id=task_id,
        stage=stage_name,
        create=False,
    )
    if local_path is None or not local_path.exists() or not local_path.is_file():
        return None
    try:
        return local_path.read_bytes()
    except OSError:
        return None


def _resolve_storage_reference(
    *, task_type: str, task_id: uuid.UUID, stage: str
) -> tuple[str, str | None]:
    if _minio_enabled():
        object_key = _task_stage_object_key(
            task_type=task_type, task_id=task_id, stage=stage
        )
        if _minio_object_exists(object_key):
            return "minio", object_key
    return "local", None


def _upload_stage_log_to_minio(
    *,
    task_type: str,
    task_id: uuid.UUID,
    stage: str,
    path: Path,
) -> None:
    if not _minio_enabled():
        return
    if not path.exists() or not path.is_file():
        return

    try:
        data = path.read_bytes()
    except OSError:
        return
    object_key = _task_stage_object_key(
        task_type=task_type, task_id=task_id, stage=stage
    )
    _upload_to_minio(object_key=object_key, data=data)


def _minio_enabled() -> bool:
    settings = get_settings()
    if settings.task_log_storage_backend.strip().lower() != "minio":
        return False
    if Minio is None:
        return False
    return bool(
        settings.task_log_minio_endpoint.strip()
        and settings.task_log_minio_access_key.strip()
        and settings.task_log_minio_secret_key.strip()
        and settings.task_log_minio_bucket.strip()
    )


def _minio_client() -> Minio | None:
    if not _minio_enabled():
        return None
    settings = get_settings()
    http_client = None
    if urllib3 is not None:
        timeout = urllib3.Timeout(connect=2.0, read=4.0)
        retry = urllib3.Retry(total=0, connect=0, read=0, redirect=0)
        http_client = urllib3.PoolManager(timeout=timeout, retries=retry)

    return Minio(
        endpoint=settings.task_log_minio_endpoint.strip(),
        access_key=settings.task_log_minio_access_key.strip(),
        secret_key=settings.task_log_minio_secret_key.strip(),
        secure=bool(settings.task_log_minio_secure),
        region=settings.task_log_minio_region.strip() or None,
        http_client=http_client,
    )


def _ensure_minio_bucket(client: Minio) -> bool:
    settings = get_settings()
    bucket = settings.task_log_minio_bucket.strip()
    if not bucket:
        return False
    try:
        if client.bucket_exists(bucket):
            return True
        if not settings.task_log_minio_auto_create_bucket:
            return False
        client.make_bucket(bucket)
        return True
    except Exception:
        return False


def _upload_to_minio(*, object_key: str, data: bytes) -> bool:
    client = _minio_client()
    if client is None:
        return False

    settings = get_settings()
    bucket = settings.task_log_minio_bucket.strip()
    if not bucket:
        return False
    if not _ensure_minio_bucket(client):
        return False

    try:
        client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type="text/plain; charset=utf-8",
        )
        return True
    except Exception:
        return False


def _download_from_minio(object_key: str) -> bytes | None:
    client = _minio_client()
    if client is None:
        return None
    settings = get_settings()
    bucket = settings.task_log_minio_bucket.strip()
    if not bucket:
        return None

    try:
        response = client.get_object(bucket_name=bucket, object_name=object_key)
    except Exception:
        return None

    try:
        return response.read()
    except Exception:
        return None
    finally:
        try:
            response.close()
            response.release_conn()
        except Exception:
            pass


def _minio_object_exists(object_key: str) -> bool:
    client = _minio_client()
    if client is None:
        return False
    settings = get_settings()
    bucket = settings.task_log_minio_bucket.strip()
    if not bucket:
        return False
    try:
        client.stat_object(bucket_name=bucket, object_name=object_key)
        return True
    except Exception:
        return False


def _delete_from_minio(object_key: str) -> bool:
    client = _minio_client()
    if client is None:
        return False
    settings = get_settings()
    bucket = settings.task_log_minio_bucket.strip()
    if not bucket:
        return False
    try:
        client.remove_object(bucket_name=bucket, object_name=object_key)
        return True
    except Exception:
        return False
