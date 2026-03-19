from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

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
from app.security.secrets import decrypt_secret, encrypt_secret
from app.services.audit_service import append_audit_log
from app.services.project_service import refresh_project_status
from app.services.snapshot_storage_service import persist_snapshot_from_directory
from app.services.task_log_service import append_task_log


VALID_GIT_REF_TYPES = {"branch", "tag", "commit"}
VALID_GIT_REPO_VISIBILITY = {"public", "private"}
VALID_GIT_AUTH_TYPES = {"none", "https_token", "ssh_key"}
IMPORT_STAGE_SEQUENCE_BY_TYPE: dict[str, list[ImportJobStage]] = {
    ImportType.UPLOAD.value: [
        ImportJobStage.VALIDATE,
        ImportJobStage.EXTRACT,
        ImportJobStage.ARCHIVE,
        ImportJobStage.FINALIZE,
    ],
    ImportType.GIT.value: [
        ImportJobStage.VALIDATE,
        ImportJobStage.CHECKOUT,
        ImportJobStage.ARCHIVE,
        ImportJobStage.FINALIZE,
    ],
}

FAILURE_HINTS: dict[str, str] = {
    "UPLOAD_TOO_LARGE": "请压缩后重试，或按项目策略拆分上传。",
    "ARCHIVE_INVALID": "请确认上传 zip/tar.gz 且结构完整。",
    "ZIP_SLIP_DETECTED": "压缩包存在非法路径，请修复后重传。",
    "ARCHIVE_BOMB_SUSPECTED": "压缩包解压体积或文件数异常，请检查后重传。",
    "GIT_AUTH_FAILED": "请检查仓库权限、凭据或地址是否正确。",
    "GIT_REF_NOT_FOUND": "请确认分支/Tag/Commit 是否存在。",
    "GIT_NETWORK_ERROR": "请检查网络连通性后重试。",
    "GIT_PRIVATE_AUTH_REQUIRED": "私有仓库需要提供认证信息，请选择 HTTPS Token 或 SSH Key。",
    "GIT_AUTH_TYPE_INVALID": "Git 认证方式不受支持，请使用 none/https_token/ssh_key。",
    "GIT_AUTH_SCHEME_MISMATCH": "当前仓库地址与所选认证方式不匹配，请检查仓库 URL 与认证方式。",
    "GIT_AUTH_INPUT_INVALID": "Git 认证信息不完整，请检查用户名、Token 或 SSH Key。",
    "GIT_SSH_PASSPHRASE_UNSUPPORTED": "当前环境暂不支持带口令的 SSH Key，请先使用无口令 Key 或 HTTPS Token。",
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


def sanitize_repo_url_for_display(repo_url: str | None) -> str | None:
    normalized = str(repo_url or "").strip()
    if not normalized:
        return None
    if (
        "@" in normalized
        and ":" in normalized
        and not normalized.startswith(("http://", "https://", "ssh://"))
    ):
        user_host, _, path = normalized.partition(":")
        host = user_host.split("@", 1)[-1]
        return f"{host}:{path}" if path else host
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized
    host = parsed.hostname or parsed.netloc.rsplit("@", 1)[-1]
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    sanitized = SplitResult(
        scheme=parsed.scheme,
        netloc=netloc,
        path=parsed.path,
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(sanitized)


def normalize_git_auth_settings(
    *,
    repo_url: str,
    repo_visibility: str | None,
    auth_type: str | None,
    username: str | None,
    access_token: str | None,
    ssh_private_key: str | None,
    ssh_passphrase: str | None,
    credential_id: str | None,
) -> dict[str, object]:
    if credential_id is not None and str(credential_id).strip():
        raise AppError(
            code="CREDENTIAL_PROVIDER_NOT_CONFIGURED",
            status_code=501,
            message="当前环境未启用凭据提供器，请先使用公开仓库或直接填写私有仓认证信息",
        )

    has_auth_material = any(
        str(value or "").strip()
        for value in [
            auth_type,
            username,
            access_token,
            ssh_private_key,
            ssh_passphrase,
        ]
    )
    normalized_visibility = (
        str(repo_visibility or ("private" if has_auth_material else "public"))
        .strip()
        .lower()
    )
    if normalized_visibility not in VALID_GIT_REPO_VISIBILITY:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="repo_visibility 仅支持 public/private",
        )

    normalized_auth_type = (
        str(auth_type or ("none" if normalized_visibility == "public" else ""))
        .strip()
        .lower()
        or None
    )
    if normalized_auth_type is None:
        raise AppError(
            code="GIT_PRIVATE_AUTH_REQUIRED",
            status_code=422,
            message="私有仓库需要提供认证方式",
        )
    if normalized_auth_type not in VALID_GIT_AUTH_TYPES:
        raise AppError(
            code="GIT_AUTH_TYPE_INVALID",
            status_code=422,
            message="Git 认证方式不受支持",
        )

    normalized_repo_url = str(repo_url or "").strip()
    is_httpish = normalized_repo_url.startswith(("http://", "https://"))
    is_ssh = normalized_repo_url.startswith("ssh://") or (
        "@" in normalized_repo_url and ":" in normalized_repo_url and not is_httpish
    )

    normalized_username = str(username or "").strip() or None
    normalized_token = str(access_token or "").strip() or None
    normalized_ssh_key = str(ssh_private_key or "").strip() or None
    normalized_ssh_passphrase = str(ssh_passphrase or "").strip() or None

    if normalized_visibility == "private" and normalized_auth_type == "none":
        raise AppError(
            code="GIT_PRIVATE_AUTH_REQUIRED",
            status_code=422,
            message="私有仓库需要提供认证信息",
        )

    if normalized_auth_type == "https_token":
        if not is_httpish:
            raise AppError(
                code="GIT_AUTH_SCHEME_MISMATCH",
                status_code=422,
                message="HTTPS Token 仅适用于 HTTP/HTTPS 仓库地址",
            )
        if normalized_token is None:
            raise AppError(
                code="GIT_AUTH_INPUT_INVALID",
                status_code=422,
                message="请提供 HTTPS Token",
            )
        normalized_username = normalized_username or "git"
    elif normalized_auth_type == "ssh_key":
        if not is_ssh:
            raise AppError(
                code="GIT_AUTH_SCHEME_MISMATCH",
                status_code=422,
                message="SSH Key 仅适用于 SSH 仓库地址",
            )
        if normalized_ssh_key is None:
            raise AppError(
                code="GIT_AUTH_INPUT_INVALID",
                status_code=422,
                message="请提供 SSH 私钥",
            )
        if normalized_ssh_passphrase:
            raise AppError(
                code="GIT_SSH_PASSPHRASE_UNSUPPORTED",
                status_code=422,
                message="当前环境暂不支持带口令的 SSH Key",
            )
    else:
        normalized_username = None
        normalized_token = None
        normalized_ssh_key = None
        normalized_ssh_passphrase = None

    return {
        "repo_visibility": normalized_visibility,
        "auth_type": normalized_auth_type,
        "username": normalized_username,
        "access_token": normalized_token,
        "ssh_private_key": normalized_ssh_key,
        "ssh_passphrase": normalized_ssh_passphrase,
        "repo_url_display": sanitize_repo_url_for_display(normalized_repo_url)
        or normalized_repo_url,
        "repo_url_internal": normalized_repo_url,
        "repo_is_http": is_httpish,
        "repo_is_ssh": is_ssh,
    }


def serialize_git_auth_payload(auth_settings: dict[str, object]) -> dict[str, object]:
    payload = {
        "repo_visibility": auth_settings.get("repo_visibility"),
        "auth_type": auth_settings.get("auth_type"),
    }
    username = str(auth_settings.get("username") or "").strip()
    access_token = str(auth_settings.get("access_token") or "").strip()
    ssh_private_key = str(auth_settings.get("ssh_private_key") or "").strip()
    ssh_passphrase = str(auth_settings.get("ssh_passphrase") or "").strip()
    if username:
        payload["username"] = username
    if access_token:
        payload["access_token_encrypted"] = encrypt_secret(access_token)
    if ssh_private_key:
        payload["ssh_private_key_encrypted"] = encrypt_secret(ssh_private_key)
    if ssh_passphrase:
        payload["ssh_passphrase_encrypted"] = encrypt_secret(ssh_passphrase)
    return payload


def deserialize_git_auth_payload(payload: dict[str, object]) -> dict[str, object]:
    auth_type = str(payload.get("auth_type") or "none").strip().lower()
    normalized = {
        "repo_visibility": str(payload.get("repo_visibility") or "public")
        .strip()
        .lower(),
        "auth_type": auth_type,
        "username": str(payload.get("username") or "").strip() or None,
    }
    encrypted_access_token = str(payload.get("access_token_encrypted") or "").strip()
    encrypted_ssh_key = str(payload.get("ssh_private_key_encrypted") or "").strip()
    encrypted_ssh_passphrase = str(
        payload.get("ssh_passphrase_encrypted") or ""
    ).strip()
    if encrypted_access_token:
        normalized["access_token"] = decrypt_secret(encrypted_access_token)
    if encrypted_ssh_key:
        normalized["ssh_private_key"] = decrypt_secret(encrypted_ssh_key)
    if encrypted_ssh_passphrase:
        normalized["ssh_passphrase"] = decrypt_secret(encrypted_ssh_passphrase)
    return normalized


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


def build_import_progress_payload(job: ImportJob) -> dict[str, object]:
    stage_sequence = IMPORT_STAGE_SEQUENCE_BY_TYPE.get(
        job.import_type,
        [
            ImportJobStage.VALIDATE,
            ImportJobStage.CHECKOUT,
            ImportJobStage.ARCHIVE,
            ImportJobStage.FINALIZE,
        ],
    )
    total_stages = len(stage_sequence)
    current_stage = job.stage or stage_sequence[0].value
    try:
        stage_index = next(
            index
            for index, stage in enumerate(stage_sequence)
            if stage.value == current_stage
        )
    except StopIteration:
        stage_index = 0

    is_terminal = job.status in {
        ImportJobStatus.SUCCEEDED.value,
        ImportJobStatus.FAILED.value,
        ImportJobStatus.CANCELED.value,
        ImportJobStatus.TIMEOUT.value,
    }
    if job.status == ImportJobStatus.SUCCEEDED.value:
        completed_stages = total_stages
        percent = 100
    elif job.status == ImportJobStatus.RUNNING.value:
        completed_stages = stage_index
        percent = max(5, min(95, int((stage_index / max(1, total_stages)) * 100) + 10))
    elif is_terminal:
        completed_stages = max(0, min(total_stages, stage_index))
        percent = max(5, min(99, int((completed_stages / max(1, total_stages)) * 100)))
    else:
        completed_stages = 0
        percent = 0

    stages: list[dict[str, object]] = []
    for index, stage in enumerate(stage_sequence):
        if job.status == ImportJobStatus.SUCCEEDED.value:
            stage_status = "SUCCEEDED"
        elif index < stage_index:
            stage_status = "SUCCEEDED"
        elif stage.value == current_stage:
            stage_status = job.status
        else:
            stage_status = ImportJobStatus.PENDING.value
        stages.append(
            {
                "stage": stage.value,
                "display_name": stage.value,
                "order": index,
                "status": stage_status,
            }
        )

    return {
        "current_stage": current_stage,
        "percent": percent,
        "completed_stages": completed_stages,
        "total_stages": total_stages,
        "is_terminal": is_terminal,
        "stages": stages,
    }


def build_import_result_summary(job: ImportJob) -> dict[str, object]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    summary: dict[str, object] = {}
    for key in (
        "original_filename",
        "version_name",
        "resolved_commit",
        "snapshot_object_key",
        "size_bytes",
        "repo_visibility",
        "auth_type",
    ):
        if key in payload and payload.get(key) is not None:
            summary[key] = payload.get(key)
    if job.version_id is not None:
        summary["version_id"] = job.version_id
    return summary


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
    *, args: list[str], timeout: int, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            code="GIT_NETWORK_ERROR", status_code=422, message="Git 操作超时"
        ) from exc


def _mask_git_error_detail(value: str) -> str:
    normalized = str(value or "")
    if not normalized:
        return normalized
    for pattern in [r"https://[^\s/@:]+:[^\s/@]+@", r"ssh://[^\s/@]+@"]:
        normalized = re.sub(pattern, "https://***:***@", normalized)
    return normalized


@contextmanager
def _git_runtime_environment(
    *, git_auth: dict[str, object] | None, workspace: Path | None = None
):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    if not git_auth:
        yield env
        return

    auth_type = str(git_auth.get("auth_type") or "none").strip().lower()
    if auth_type == "none":
        yield env
        return

    temp_dir_ctx: tempfile.TemporaryDirectory[str] | None = None
    if workspace is not None:
        temp_dir = workspace / "auth"
        temp_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir_ctx = tempfile.TemporaryDirectory(prefix="codescope-git-auth-")
        temp_dir = Path(temp_dir_ctx.__enter__())

    try:
        if auth_type == "https_token":
            username = str(git_auth.get("username") or "git").strip() or "git"
            secret = str(git_auth.get("access_token") or "").strip()
            wrapper = _write_git_askpass_wrapper(temp_dir)
            env["GIT_ASKPASS"] = str(wrapper)
            env["CODESCOPE_GIT_USERNAME"] = username
            env["CODESCOPE_GIT_SECRET"] = secret
        elif auth_type == "ssh_key":
            key_path = temp_dir / "id_import"
            key_path.write_text(
                str(git_auth.get("ssh_private_key") or ""), encoding="utf-8"
            )
            try:
                key_path.chmod(0o600)
            except Exception:
                pass
            env["GIT_SSH_COMMAND"] = _build_git_ssh_command(key_path)
        yield env
    finally:
        if workspace is None and temp_dir_ctx is not None:
            temp_dir_ctx.__exit__(None, None, None)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _write_git_askpass_wrapper(directory: Path) -> Path:
    script_path = directory / "git_askpass.py"
    script_path.write_text(
        "import os\n"
        "import sys\n"
        "prompt = ' '.join(sys.argv[1:]).lower()\n"
        "if 'username' in prompt:\n"
        "    value = os.environ.get('CODESCOPE_GIT_USERNAME', '')\n"
        "else:\n"
        "    value = os.environ.get('CODESCOPE_GIT_SECRET', '')\n"
        "sys.stdout.write(value)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper = directory / "git_askpass.cmd"
        wrapper.write_text(
            f'@"{os.sys.executable}" "{script_path}" %*\r\n',
            encoding="utf-8",
        )
        return wrapper
    wrapper = directory / "git_askpass.sh"
    wrapper.write_text(
        f'#!/bin/sh\n"{os.sys.executable}" "{script_path}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return wrapper


def _build_git_ssh_command(key_path: Path) -> str:
    args = [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
    ]
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    import shlex

    return " ".join(shlex.quote(item) for item in args)


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


def _normalize_optional_git_ref(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_git_ref_inputs(
    *, ref_type: str | None, ref_value: str | None
) -> tuple[str | None, str | None]:
    normalized_ref_type = _normalize_optional_git_ref(ref_type)
    normalized_ref_value = _normalize_optional_git_ref(ref_value)
    if bool(normalized_ref_type) != bool(normalized_ref_value):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="ref_type 与 ref_value 需要同时填写，或同时留空使用默认分支",
        )
    if (
        normalized_ref_type is not None
        and normalized_ref_type not in VALID_GIT_REF_TYPES
    ):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="ref_type 仅支持 branch/tag/commit",
        )
    return normalized_ref_type, normalized_ref_value


def _git_command_error(
    *,
    result: subprocess.CompletedProcess[str],
    default_code: str = "GIT_NETWORK_ERROR",
    default_message: str = "Git 网络或仓库访问失败",
) -> AppError:
    stderr = _mask_git_error_detail(result.stderr)
    if result.returncode == 2 and not stderr.strip():
        return AppError(
            code="GIT_REF_NOT_FOUND",
            status_code=422,
            message="Git 引用不存在",
        )
    mapped = _map_git_error(stderr)
    if mapped.code == "GIT_NETWORK_ERROR" and default_code != "GIT_NETWORK_ERROR":
        return AppError(code=default_code, status_code=422, message=default_message)
    return mapped


def _parse_head_symref(stdout: str) -> tuple[str | None, str | None]:
    branch_line = None
    commit_line = None
    for line in stdout.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        if normalized.startswith("ref:") and normalized.endswith("\tHEAD"):
            branch_line = normalized
            continue
        if normalized.endswith("\tHEAD"):
            commit_line = normalized

    if branch_line is not None:
        ref_value = branch_line[len("ref:") :].split("\t", 1)[0].strip()
        if ref_value.startswith("refs/heads/"):
            return "branch", ref_value.removeprefix("refs/heads/")
        if ref_value.startswith("refs/tags/"):
            return "tag", ref_value.removeprefix("refs/tags/")
    if commit_line is not None:
        return "commit", commit_line.split("\t", 1)[0].strip()
    return None, None


def resolve_git_ref(
    *,
    repo_url: str,
    ref_type: str | None,
    ref_value: str | None,
    git_auth: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_ref_type, normalized_ref_value = _normalize_git_ref_inputs(
        ref_type=ref_type,
        ref_value=ref_value,
    )
    timeout = get_settings().git_command_timeout_seconds

    with _git_runtime_environment(git_auth=git_auth) as env:
        if normalized_ref_type is not None and normalized_ref_value is not None:
            result = _run_git_command(
                args=[
                    "git",
                    "ls-remote",
                    "--exit-code",
                    repo_url,
                    normalized_ref_value,
                ],
                timeout=timeout,
                env=env,
            )
            if result.returncode != 0:
                raise _git_command_error(result=result)
            return {
                "resolved_ref_type": normalized_ref_type,
                "resolved_ref_value": normalized_ref_value,
                "resolved_ref": f"{normalized_ref_type}:{normalized_ref_value}",
                "auto_detected": False,
            }

        result = _run_git_command(
            args=["git", "ls-remote", "--symref", repo_url, "HEAD"],
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            raise _git_command_error(result=result)
        detected_ref_type, detected_ref_value = _parse_head_symref(result.stdout)
        if detected_ref_type is None or detected_ref_value is None:
            raise AppError(
                code="GIT_REF_NOT_FOUND",
                status_code=422,
                message="无法自动解析仓库默认引用，请手动填写分支、标签或 Commit",
            )
        return {
            "resolved_ref_type": detected_ref_type,
            "resolved_ref_value": detected_ref_value,
            "resolved_ref": f"{detected_ref_type}:{detected_ref_value}",
            "auto_detected": True,
        }


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
                repo_url=str(
                    payload.get("repo_url_internal") or payload.get("repo_url") or ""
                ),
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
                git_auth=deserialize_git_auth_payload(payload),
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


def test_git_source(
    *,
    repo_url: str,
    ref_type: str | None,
    ref_value: str | None,
    git_auth: dict[str, object] | None = None,
) -> dict[str, object]:
    return resolve_git_ref(
        repo_url=repo_url,
        ref_type=ref_type,
        ref_value=ref_value,
        git_auth=git_auth,
    )


def run_git_import_job(
    *,
    import_job_id: uuid.UUID,
    repo_url: str,
    ref_type: str | None,
    ref_value: str | None,
    version_name: str | None,
    note: str | None,
    git_auth: dict[str, object] | None,
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

        _set_import_job_running(session, job=job, stage=ImportJobStage.VALIDATE.value)
        resolved_ref = test_git_source(
            repo_url=repo_url,
            ref_type=ref_type,
            ref_value=ref_value,
            git_auth=git_auth,
        )
        resolved_ref_type = (
            str(resolved_ref.get("resolved_ref_type") or "").strip().lower()
        )
        resolved_ref_value = str(resolved_ref.get("resolved_ref_value") or "").strip()
        if not resolved_ref_type or not resolved_ref_value:
            raise AppError(
                code="GIT_REF_NOT_FOUND",
                status_code=422,
                message="无法解析 Git 引用",
            )

        timeout = get_settings().git_command_timeout_seconds
        _set_import_job_running(session, job=job, stage=ImportJobStage.CHECKOUT.value)
        with _git_runtime_environment(git_auth=git_auth, workspace=workspace) as env:
            clone_result = _run_git_command(
                args=["git", "clone", repo_url, str(repo_dir)],
                timeout=timeout,
                env=env,
            )
            if clone_result.returncode != 0:
                raise _map_git_error(_mask_git_error_detail(clone_result.stderr))

            checkout_result = _run_git_command(
                args=["git", "-C", str(repo_dir), "checkout", resolved_ref_value],
                timeout=timeout,
                env=env,
            )
            if checkout_result.returncode != 0:
                raise _map_git_error(_mask_git_error_detail(checkout_result.stderr))

            rev_parse_result = _run_git_command(
                args=["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                timeout=timeout,
                env=env,
            )
            if rev_parse_result.returncode != 0:
                raise _map_git_error(_mask_git_error_detail(rev_parse_result.stderr))

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
            git_ref=f"{resolved_ref_type}:{resolved_ref_value}",
        )

        job.status = ImportJobStatus.SUCCEEDED.value
        job.stage = ImportJobStage.FINALIZE.value
        job.version_id = version.id
        job.failure_code = None
        job.payload = {
            **job.payload,
            "repo_url": sanitize_repo_url_for_display(repo_url),
            "repo_url_internal": repo_url,
            "ref_type": resolved_ref_type,
            "ref_value": resolved_ref_value,
            "resolved_ref_type": resolved_ref_type,
            "resolved_ref_value": resolved_ref_value,
            "resolved_ref": str(resolved_ref.get("resolved_ref") or ""),
            "auto_detected_ref": bool(resolved_ref.get("auto_detected")),
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
        repo_url = str(
            payload.get("repo_url_internal") or payload.get("repo_url") or ""
        ).strip()
        ref_type = _normalize_optional_git_ref(
            str(payload.get("resolved_ref_type") or payload.get("ref_type") or "")
        )
        ref_value = _normalize_optional_git_ref(
            str(payload.get("resolved_ref_value") or payload.get("ref_value") or "")
        )
        if not repo_url:
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
        git_auth=deserialize_git_auth_payload(payload),
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
