from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path, PurePosixPath

from app.config import get_settings
from app.core.errors import AppError


def _absolute_storage_path(path: str | Path) -> Path:
    normalized = Path(os.path.normpath(str(path)))
    if normalized.is_absolute():
        return normalized
    backend_root = Path(__file__).resolve().parents[2]
    return Path(os.path.normpath(str(backend_root / normalized)))


def _report_root() -> Path:
    root = _absolute_storage_path(get_settings().report_storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_relative_key(object_key: str) -> str:
    normalized = str(PurePosixPath(str(object_key or "").strip().replace("\\", "/")))
    parsed = PurePosixPath(normalized)
    if not normalized or normalized in {"", "."}:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="report object_key 不能为空",
        )
    if parsed.is_absolute() or ".." in parsed.parts:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="report object_key 不合法",
        )
    return normalized.lstrip("/")


def build_generated_report_object_key(
    *, report_job_id: uuid.UUID, filename: str
) -> str:
    safe_name = PurePosixPath(str(filename).strip()).name
    if not safe_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="报告文件名不能为空",
        )
    return f"jobs/{report_job_id}/generated/{safe_name}"


def build_report_manifest_object_key(*, report_job_id: uuid.UUID) -> str:
    return f"jobs/{report_job_id}/manifest.json"


def build_report_bundle_object_key(*, report_job_id: uuid.UUID, filename: str) -> str:
    safe_name = PurePosixPath(str(filename).strip()).name
    if not safe_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="压缩包文件名不能为空",
        )
    return f"jobs/{report_job_id}/bundle/{safe_name}"


def get_report_job_root(*, report_job_id: uuid.UUID, create: bool) -> Path | None:
    root = _report_root() / "jobs" / str(report_job_id)
    if create:
        root.mkdir(parents=True, exist_ok=True)
        return root
    if not root.exists() or not root.is_dir():
        return None
    return root


def reset_report_job_root(*, report_job_id: uuid.UUID) -> Path:
    root = _report_root() / "jobs" / str(report_job_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def delete_report_object(*, object_key: str) -> bool:
    try:
        target = resolve_report_object_path(object_key=object_key)
    except AppError:
        return False
    if not target.exists() or not target.is_file():
        return False
    try:
        target.unlink()
    except OSError:
        return False
    _prune_empty_report_dirs(target.parent)
    return True


def delete_report_job_root(*, report_job_id: uuid.UUID) -> dict[str, int | bool]:
    root = get_report_job_root(report_job_id=report_job_id, create=False)
    if root is None:
        return {"deleted": False, "deleted_files_count": 0}

    deleted_files_count = sum(1 for item in root.rglob("*") if item.is_file())
    shutil.rmtree(root, ignore_errors=True)
    return {
        "deleted": True,
        "deleted_files_count": deleted_files_count,
    }


def resolve_report_object_path(*, object_key: str) -> Path:
    normalized = _safe_relative_key(object_key)
    target = (_report_root() / normalized).resolve()
    root = _report_root().resolve()
    if not target.is_relative_to(root):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="报告路径越界",
        )
    return target


def write_report_text(*, object_key: str, content: str) -> Path:
    target = resolve_report_object_path(object_key=object_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def write_report_bytes(*, object_key: str, content: bytes) -> Path:
    target = resolve_report_object_path(object_key=object_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def _prune_empty_report_dirs(start: Path) -> None:
    root = _report_root().resolve()
    current = start.resolve()
    while current != root and current.is_relative_to(root):
        try:
            next(current.iterdir())
            break
        except StopIteration:
            current.rmdir()
            current = current.parent
        except OSError:
            break
