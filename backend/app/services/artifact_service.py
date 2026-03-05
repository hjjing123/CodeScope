from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import get_settings
from app.core.errors import AppError
from app.models import Job


def list_job_artifacts(*, job: Job) -> list[dict[str, object]]:
    settings = get_settings()
    artifacts: list[dict[str, object]] = []

    logs_root = Path(settings.scan_log_root) / str(job.id)
    if logs_root.exists() and logs_root.is_dir():
        for item in sorted(logs_root.glob("*.log"), key=lambda p: p.name.lower()):
            rel = item.name
            artifacts.append(
                _artifact_payload(
                    source="scan_log",
                    relative_path=rel,
                    artifact_type="LOG",
                    display_name=f"log/{rel}",
                    size_bytes=_stat_size(item),
                )
            )

    workspace_root = Path(settings.scan_workspace_root) / str(job.id)
    if workspace_root.exists() and workspace_root.is_dir():
        for item in sorted(_iter_files(workspace_root), key=lambda p: p.as_posix().lower()):
            artifacts.append(
                _artifact_payload(
                    source="scan_workspace",
                    relative_path=item.as_posix(),
                    artifact_type="INTERMEDIATE",
                    display_name=f"workspace/{item.as_posix()}",
                    size_bytes=_stat_size(workspace_root / item),
                )
            )

    reports_root = _external_reports_root(job=job)
    if reports_root is not None and reports_root.exists() and reports_root.is_dir():
        for item in sorted(_iter_files(reports_root), key=lambda p: p.as_posix().lower()):
            artifacts.append(
                _artifact_payload(
                    source="external_reports",
                    relative_path=item.as_posix(),
                    artifact_type="RESULT",
                    display_name=f"reports/{item.as_posix()}",
                    size_bytes=_stat_size(reports_root / item),
                )
            )

    archive_file = Path(settings.snapshot_storage_root) / str(job.version_id) / "snapshot.tar.gz"
    if archive_file.exists() and archive_file.is_file():
        artifacts.append(
            _artifact_payload(
                source="snapshot_archive",
                relative_path="snapshot.tar.gz",
                artifact_type="SNAPSHOT",
                display_name="snapshot/snapshot.tar.gz",
                size_bytes=_stat_size(archive_file),
            )
        )

    return artifacts


def resolve_job_artifact(*, job: Job, artifact_id: str) -> tuple[Path, dict[str, object]]:
    source, relative_path = decode_artifact_id(artifact_id)
    root = _artifact_root(job=job, source=source)
    if root is None or not root.exists() or not root.is_dir():
        raise AppError(code="OBJECT_NOT_FOUND", status_code=404, message="产物不存在")

    target = _safe_join(root, relative_path)
    if not target.exists() or not target.is_file():
        raise AppError(code="OBJECT_NOT_FOUND", status_code=404, message="产物不存在")

    payload = {
        "artifact_id": artifact_id,
        "source": source,
        "relative_path": relative_path,
        "filename": target.name,
    }
    return target, payload


def build_job_logs_zip_bytes(*, job_id: str) -> bytes:
    settings = get_settings()
    root = Path(settings.scan_log_root) / job_id
    if not root.exists() or not root.is_dir():
        raise AppError(code="JOB_LOG_NOT_FOUND", status_code=404, message="任务日志不存在")

    files = sorted(root.glob("*.log"), key=lambda item: item.name.lower())
    if not files:
        raise AppError(code="JOB_LOG_NOT_FOUND", status_code=404, message="任务日志不存在")

    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        for item in files:
            zf.write(item, arcname=item.name)
    return buffer.getvalue()


def get_job_stage_log_path(*, job_id: str, stage: str) -> Path:
    safe_stage = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in stage).strip("_")
    if not safe_stage:
        safe_stage = "unknown"

    settings = get_settings()
    root = Path(settings.scan_log_root) / job_id
    path = root / f"{safe_stage}.log"
    if not path.exists() or not path.is_file():
        raise AppError(code="JOB_LOG_NOT_FOUND", status_code=404, message="任务阶段日志不存在")
    return path


def decode_artifact_id(artifact_id: str) -> tuple[str, str]:
    token = artifact_id.strip()
    if not token:
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="artifact_id 不能为空")

    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    except (UnicodeDecodeError, binascii.Error) as exc:
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="artifact_id 格式不正确") from exc

    source, sep, rel = raw.partition("|")
    if not sep or not source or not rel:
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="artifact_id 内容不正确")
    return source, rel


def _artifact_payload(
    *,
    source: str,
    relative_path: str,
    artifact_type: str,
    display_name: str,
    size_bytes: int | None,
) -> dict[str, object]:
    raw = f"{source}|{relative_path}".encode("utf-8")
    artifact_id = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "display_name": display_name,
        "size_bytes": size_bytes,
        "source": source,
    }


def _artifact_root(*, job: Job, source: str) -> Path | None:
    settings = get_settings()
    if source == "scan_log":
        return Path(settings.scan_log_root) / str(job.id)
    if source == "scan_workspace":
        return Path(settings.scan_workspace_root) / str(job.id)
    if source == "external_reports":
        return _external_reports_root(job=job)
    if source == "snapshot_archive":
        return Path(settings.snapshot_storage_root) / str(job.version_id)
    raise AppError(code="INVALID_ARGUMENT", status_code=422, message="不支持的产物来源")


def _external_reports_root(*, job: Job) -> Path | None:
    summary = job.result_summary if isinstance(job.result_summary, dict) else {}
    raw = str(summary.get("reports_dir") or "").strip()
    if not raw:
        return None
    return Path(raw)


def _safe_join(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="产物路径不合法")

    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if not target.is_relative_to(root_resolved):
        raise AppError(code="INVALID_ARGUMENT", status_code=422, message="产物路径越界")
    return target


def _iter_files(root: Path):
    for item in root.rglob("*"):
        if item.is_file():
            yield item.relative_to(root)


def _stat_size(path: Path) -> int | None:
    try:
        return int(path.stat().st_size)
    except OSError:
        return None
