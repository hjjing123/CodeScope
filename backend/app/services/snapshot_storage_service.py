from __future__ import annotations

import os
import shutil
import tarfile
import uuid
from pathlib import Path, PurePosixPath

from app.config import get_settings
from app.core.errors import AppError


def _snapshot_root() -> Path:
    root = _absolute_storage_path(get_settings().snapshot_storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _absolute_storage_path(path: str | Path) -> Path:
    normalized = Path(os.path.normpath(str(path)))
    if normalized.is_absolute():
        return normalized
    backend_root = Path(__file__).resolve().parents[2]
    return Path(os.path.normpath(str(backend_root / normalized)))


def _version_base_dir(version_id: uuid.UUID) -> Path:
    return _snapshot_root() / str(version_id)


def _safe_relative_path(path: str | None) -> str:
    if path is None:
        return ""

    normalized = str(PurePosixPath(path.strip().replace("\\", "/")))
    if normalized in {"", "."}:
        return ""

    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="路径参数不合法"
        )

    return normalized.lstrip("/")


def _resolve_version_path(version_id: uuid.UUID, relative_path: str | None) -> Path:
    source_root = (_version_base_dir(version_id) / "source").resolve()
    if not source_root.exists():
        raise AppError(
            code="SNAPSHOT_NOT_FOUND", status_code=404, message="版本快照不存在"
        )

    rel = _safe_relative_path(relative_path)
    target = (source_root / rel).resolve()
    try:
        target.relative_to(source_root)
    except ValueError as exc:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="路径越界访问"
        ) from exc
    except RuntimeError as exc:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="路径越界访问"
        ) from exc

    return target


def _parse_snapshot_object_key(snapshot_object_key: str) -> tuple[str, uuid.UUID]:
    normalized = str(PurePosixPath(snapshot_object_key.strip().replace("\\", "/")))
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="snapshot_object_key 格式不合法",
        )

    parts = parsed.parts
    if len(parts) != 3 or parts[0] != "snapshots" or parts[2] != "snapshot.tar.gz":
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="snapshot_object_key 格式不合法",
        )

    try:
        source_version_id = uuid.UUID(parts[1])
    except ValueError as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="snapshot_object_key 格式不合法",
        ) from exc

    return normalized, source_version_id


def _resolve_source_archive_path(snapshot_object_key: str) -> tuple[str, Path, Path]:
    normalized_key, source_version_id = _parse_snapshot_object_key(snapshot_object_key)
    source_base = _version_base_dir(source_version_id)
    source_archive = source_base / "snapshot.tar.gz"
    if not source_archive.exists() or not source_archive.is_file():
        raise AppError(
            code="SNAPSHOT_NOT_FOUND",
            status_code=404,
            message="snapshot_object_key 对应快照不存在",
        )
    return normalized_key, source_base, source_archive


def _extract_snapshot_archive(*, archive_path: Path, target_dir: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                member_rel_path = _safe_relative_path(member.name)
                if not member_rel_path:
                    continue

                target_path = (target_dir / member_rel_path).resolve()
                try:
                    target_path.relative_to(target_dir.resolve())
                except ValueError as exc:
                    raise AppError(
                        code="ARCHIVE_INVALID",
                        status_code=422,
                        message="快照归档包含非法路径",
                    ) from exc

                if member.issym() or member.islnk():
                    raise AppError(
                        code="ARCHIVE_INVALID",
                        status_code=422,
                        message="快照归档不支持符号链接",
                    )

                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                if not member.isfile():
                    raise AppError(
                        code="ARCHIVE_INVALID",
                        status_code=422,
                        message="快照归档包含不支持的文件类型",
                    )

                target_path.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise AppError(
                        code="ARCHIVE_INVALID",
                        status_code=422,
                        message="快照归档内容损坏",
                    )
                with extracted:
                    with target_path.open("wb") as fp:
                        shutil.copyfileobj(extracted, fp)
    except AppError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise AppError(
            code="ARCHIVE_INVALID",
            status_code=422,
            message="快照归档不可用",
        ) from exc


def materialize_snapshot_from_object_key(
    *, version_id: uuid.UUID, snapshot_object_key: str
) -> str:
    _, source_base, source_archive = _resolve_source_archive_path(snapshot_object_key)

    target_base = _version_base_dir(version_id)
    target_source = target_base / "source"
    target_archive = target_base / "snapshot.tar.gz"
    source_source = source_base / "source"

    if target_base.exists():
        shutil.rmtree(target_base)
    target_base.mkdir(parents=True, exist_ok=True)

    try:
        if source_source.exists() and source_source.is_dir():
            shutil.copytree(source_source, target_source)
        else:
            target_source.mkdir(parents=True, exist_ok=True)
            _extract_snapshot_archive(
                archive_path=source_archive, target_dir=target_source
            )
        shutil.copy2(source_archive, target_archive)
    except AppError:
        shutil.rmtree(target_base, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(target_base, ignore_errors=True)
        raise AppError(
            code="SNAPSHOT_NOT_FOUND",
            status_code=404,
            message="snapshot_object_key 对应快照不可用",
        ) from exc

    return f"snapshots/{version_id}/snapshot.tar.gz"


def persist_snapshot_from_directory(*, version_id: uuid.UUID, source_dir: Path) -> str:
    if not source_dir.exists() or not source_dir.is_dir():
        raise AppError(
            code="ARCHIVE_INVALID", status_code=422, message="导入源目录不存在"
        )

    base_dir = _version_base_dir(version_id)
    source_out = base_dir / "source"
    archive_out = base_dir / "snapshot.tar.gz"

    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, source_out)

    with tarfile.open(archive_out, "w:gz") as tar:
        for child in source_out.rglob("*"):
            tar.add(child, arcname=child.relative_to(source_out).as_posix())

    return f"snapshots/{version_id}/snapshot.tar.gz"


def list_snapshot_tree(
    *, version_id: uuid.UUID, path: str | None
) -> list[dict[str, object]]:
    target = _resolve_version_path(version_id, path)
    if not target.exists():
        raise AppError(code="PATH_NOT_FOUND", status_code=404, message="目录不存在")
    if not target.is_dir():
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="目标路径不是目录"
        )

    source_root = (_version_base_dir(version_id) / "source").resolve()
    items: list[dict[str, object]] = []
    for entry in sorted(
        target.iterdir(), key=lambda item: (item.is_file(), item.name.lower())
    ):
        items.append(
            {
                "name": entry.name,
                "path": entry.relative_to(source_root).as_posix(),
                "node_type": "dir" if entry.is_dir() else "file",
                "size_bytes": None if entry.is_dir() else entry.stat().st_size,
            }
        )

    return items


def read_snapshot_file(*, version_id: uuid.UUID, path: str) -> tuple[str, bool, int]:
    target = _resolve_version_path(version_id, path)
    if not target.exists():
        raise AppError(code="PATH_NOT_FOUND", status_code=404, message="文件不存在")
    if not target.is_file():
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="目标路径不是文件"
        )

    settings = get_settings()
    file_size = target.stat().st_size
    if file_size > settings.version_file_preview_max_bytes:
        raise AppError(
            code="FILE_TOO_LARGE", status_code=413, message="文件过大，无法预览"
        )

    content_bytes = target.read_bytes()
    if b"\x00" in content_bytes[:1024]:
        raise AppError(
            code="FILE_BINARY_NOT_SUPPORTED",
            status_code=422,
            message="二进制文件不支持预览",
        )

    content_text = content_bytes.decode("utf-8", errors="replace")
    lines = content_text.splitlines()
    total_lines = len(lines)
    limit = settings.version_file_preview_max_lines
    truncated = total_lines > limit
    preview = "\n".join(lines[:limit])
    return preview, truncated, total_lines


def get_snapshot_archive_path(*, version_id: uuid.UUID) -> Path:
    archive_path = _version_base_dir(version_id) / "snapshot.tar.gz"
    if not archive_path.exists() or not archive_path.is_file():
        raise AppError(
            code="SNAPSHOT_NOT_FOUND", status_code=404, message="版本快照归档不存在"
        )
    return archive_path


def read_snapshot_file_context(
    *,
    version_id: uuid.UUID,
    path: str,
    line: int,
    before: int = 3,
    after: int = 3,
) -> tuple[list[str], int, int]:
    if line <= 0:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="line 必须为正整数"
        )

    target = _resolve_version_path(version_id, path)
    if not target.exists():
        raise AppError(code="PATH_NOT_FOUND", status_code=404, message="文件不存在")
    if not target.is_file():
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="目标路径不是文件"
        )

    content_bytes = target.read_bytes()
    if b"\x00" in content_bytes[:1024]:
        raise AppError(
            code="FILE_BINARY_NOT_SUPPORTED",
            status_code=422,
            message="二进制文件不支持预览",
        )

    lines = content_bytes.decode("utf-8", errors="replace").splitlines()
    if line > len(lines):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="line 超出文件总行数",
            detail={"line": line, "total_lines": len(lines)},
        )

    safe_before = max(0, before)
    safe_after = max(0, after)
    start_line = max(1, line - safe_before)
    end_line = min(len(lines), line + safe_after)
    return lines[start_line - 1 : end_line], start_line, end_line
