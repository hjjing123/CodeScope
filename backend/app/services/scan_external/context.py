from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.models import Job, JobStage

from .contracts import ExternalScanContext, ExternalStageSpec

WSL_RUNTIME_PROFILE = "wsl"
CONTAINER_COMPAT_RUNTIME_PROFILE = "container_compat"


def build_external_scan_context(
    *, job: Job, settings: Any, backend_root: Path
) -> ExternalScanContext:
    reports_dir = _resolve_reports_dir(
        settings=settings, job=job, backend_root=backend_root
    )
    reports_dir.mkdir(parents=True, exist_ok=True)

    workdir = _resolve_workdir(settings=settings, job=job, backend_root=backend_root)
    stage_specs = _build_stage_specs(settings=settings)
    if not any(item.command.strip() for item in stage_specs):
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="外部扫描适配器未配置",
            detail={
                "required_any": [
                    "scan_external_runner_command",
                    "scan_external_stage_joern_command",
                    "scan_external_stage_import_command",
                    "scan_external_stage_post_labels_command",
                    "scan_external_stage_rules_command",
                ]
            },
        )

    source_dir = _resolve_source_dir(
        settings=settings,
        job=job,
        backend_root=backend_root,
        required=_requires_builtin_source(stage_specs),
    )
    workspace_dir, import_dir, cpg_file = _prepare_workspace_paths(
        settings=settings,
        job=job,
        backend_root=backend_root,
    )

    base_env = _build_scan_env(
        job=job,
        settings=settings,
        backend_root=backend_root,
        reports_dir=reports_dir,
        source_dir=source_dir,
        import_dir=import_dir,
        cpg_file=cpg_file,
        stage_specs=stage_specs,
    )
    return ExternalScanContext(
        reports_dir=reports_dir,
        workdir=workdir,
        base_env=base_env,
        stage_specs=stage_specs,
        backend_root=backend_root,
        source_dir=source_dir,
        workspace_dir=workspace_dir,
        import_dir=import_dir,
        cpg_file=cpg_file,
    )


def render_template(value: str, *, job: Job) -> str:
    rendered = value
    replacements = {
        "{job_id}": str(job.id),
        "{project_id}": str(job.project_id),
        "{version_id}": str(job.version_id),
    }
    for token, replacement in replacements.items():
        rendered = rendered.replace(token, replacement)
    return rendered


def resolve_external_path(
    *, raw_value: str, job: Job, backend_root: Path
) -> Path | None:
    rendered = render_template(raw_value.strip(), job=job)
    if not rendered:
        return None

    candidate = Path(rendered)
    if candidate.is_absolute():
        return candidate.resolve()
    return (backend_root / candidate).resolve()


def _safe_timeout_seconds(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _resolve_reports_dir(*, settings: Any, job: Job, backend_root: Path) -> Path:
    reports_dir_raw = (settings.scan_external_reports_dir or "").strip()
    if not reports_dir_raw:
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_MISSING",
            status_code=422,
            message="未配置外部扫描结果目录",
        )

    reports_dir = resolve_external_path(
        raw_value=reports_dir_raw, job=job, backend_root=backend_root
    )
    if reports_dir is None:
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_MISSING",
            status_code=422,
            message="未配置外部扫描结果目录",
        )
    if "{job_id}" not in reports_dir_raw:
        reports_dir = reports_dir / str(job.id)
    return reports_dir


def _resolve_workdir(*, settings: Any, job: Job, backend_root: Path) -> str | None:
    workdir_raw = (settings.scan_external_runner_workdir or "").strip()
    if not workdir_raw:
        return None

    workdir = resolve_external_path(
        raw_value=workdir_raw, job=job, backend_root=backend_root
    )
    if workdir is None:
        return None
    if not workdir.exists() or not workdir.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="外部扫描工作目录不存在",
            detail={"workdir": str(workdir)},
        )
    return str(workdir)


def _resolve_source_dir(
    *,
    settings: Any,
    job: Job,
    backend_root: Path,
    required: bool,
) -> Path:
    snapshot_root = resolve_external_path(
        raw_value=settings.snapshot_storage_root or "",
        job=job,
        backend_root=backend_root,
    )
    if snapshot_root is None:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置快照目录",
        )
    source_dir = snapshot_root / str(job.version_id) / "source"
    if required and (not source_dir.exists() or not source_dir.is_dir()):
        raise AppError(
            code="SNAPSHOT_NOT_FOUND",
            status_code=404,
            message="版本快照不存在",
            detail={"source_dir": str(source_dir)},
        )
    return source_dir


def _requires_builtin_source(stage_specs: list[ExternalStageSpec]) -> bool:
    for spec in stage_specs:
        command = (spec.command or "").strip().lower()
        if spec.key == "joern" and command.startswith("builtin:joern"):
            return True
    return False


def _prepare_workspace_paths(
    *, settings: Any, job: Job, backend_root: Path
) -> tuple[Path, Path, Path]:
    workspace_root = resolve_external_path(
        raw_value=settings.scan_workspace_root or "",
        job=job,
        backend_root=backend_root,
    )
    if workspace_root is None:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置扫描工作目录",
        )

    workspace_dir = workspace_root / str(job.project_id) / str(job.id) / "external"
    import_dir = workspace_dir / "import_csv"
    cpg_file = workspace_dir / "code.bin"

    import_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir, import_dir, cpg_file


def _build_stage_specs(*, settings: Any) -> list[ExternalStageSpec]:
    legacy_command = (
        getattr(settings, "scan_external_runner_command", "") or ""
    ).strip()
    if legacy_command:
        return [
            ExternalStageSpec(
                key="legacy_runner",
                command=legacy_command,
                log_stage=JobStage.QUERY.value,
                timeout_seconds=_safe_timeout_seconds(
                    getattr(settings, "scan_external_timeout_seconds", 3600),
                    default=3600,
                ),
                failure_code="SCAN_EXTERNAL_RUN_FAILED",
                timeout_code="SCAN_EXTERNAL_RUN_TIMEOUT",
            )
        ]

    return [
        ExternalStageSpec(
            key="joern",
            command=(
                getattr(settings, "scan_external_stage_joern_command", "") or ""
            ).strip(),
            log_stage=JobStage.ANALYZE.value,
            timeout_seconds=_safe_timeout_seconds(
                getattr(settings, "scan_external_stage_joern_timeout_seconds", 3600),
                default=getattr(settings, "scan_external_timeout_seconds", 3600),
            ),
            failure_code="SCAN_EXTERNAL_JOERN_FAILED",
            timeout_code="SCAN_EXTERNAL_JOERN_TIMEOUT",
        ),
        ExternalStageSpec(
            key="neo4j_import",
            command=(
                getattr(settings, "scan_external_stage_import_command", "") or ""
            ).strip(),
            log_stage=JobStage.ANALYZE.value,
            timeout_seconds=_safe_timeout_seconds(
                getattr(settings, "scan_external_stage_import_timeout_seconds", 3600),
                default=getattr(settings, "scan_external_timeout_seconds", 3600),
            ),
            failure_code="SCAN_EXTERNAL_IMPORT_FAILED",
            timeout_code="SCAN_EXTERNAL_IMPORT_TIMEOUT",
        ),
        ExternalStageSpec(
            key="post_labels",
            command=(
                getattr(settings, "scan_external_stage_post_labels_command", "") or ""
            ).strip(),
            log_stage=JobStage.QUERY.value,
            timeout_seconds=_safe_timeout_seconds(
                getattr(
                    settings, "scan_external_stage_post_labels_timeout_seconds", 1800
                ),
                default=getattr(settings, "scan_external_timeout_seconds", 3600),
            ),
            failure_code="SCAN_EXTERNAL_POST_LABELS_FAILED",
            timeout_code="SCAN_EXTERNAL_POST_LABELS_TIMEOUT",
        ),
        ExternalStageSpec(
            key="rules",
            command=(
                getattr(settings, "scan_external_stage_rules_command", "") or ""
            ).strip(),
            log_stage=JobStage.QUERY.value,
            timeout_seconds=_safe_timeout_seconds(
                getattr(settings, "scan_external_stage_rules_timeout_seconds", 3600),
                default=getattr(settings, "scan_external_timeout_seconds", 3600),
            ),
            failure_code="SCAN_EXTERNAL_RULES_FAILED",
            timeout_code="SCAN_EXTERNAL_RULES_TIMEOUT",
        ),
    ]


def _build_scan_env(
    *,
    job: Job,
    settings: Any,
    backend_root: Path,
    reports_dir: Path,
    source_dir: Path,
    import_dir: Path,
    cpg_file: Path,
    stage_specs: list[ExternalStageSpec] | None = None,
) -> dict[str, str]:
    resolved_stage_specs = stage_specs or _build_stage_specs(settings=settings)
    runtime_profile = _resolve_runtime_profile(settings=settings)
    env = dict(os.environ)
    env["CODESCOPE_SCAN_JOB_ID"] = str(job.id)
    env["CODESCOPE_SCAN_PROJECT_ID"] = str(job.project_id)
    env["CODESCOPE_SCAN_VERSION_ID"] = str(job.version_id)
    env["CODESCOPE_SCAN_REPORTS_DIR"] = str(reports_dir)
    env["CODESCOPE_SCAN_SOURCE_DIR"] = str(source_dir)
    env["CODESCOPE_SCAN_IMPORT_DIR"] = str(import_dir)
    env["CODESCOPE_SCAN_RUNTIME_PROFILE"] = runtime_profile
    env["CODESCOPE_SCAN_CONTAINER_COMPAT_MODE"] = (
        "1" if runtime_profile == CONTAINER_COMPAT_RUNTIME_PROFILE else "0"
    )
    env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = _resolve_import_host_path(
        settings=settings,
        job=job,
        backend_root=backend_root,
        import_dir=import_dir,
        runtime_profile=runtime_profile,
    )
    env["CODESCOPE_SCAN_CPG_FILE"] = str(cpg_file)
    env["CODESCOPE_SCAN_RULE_SET_KEYS"] = _json_list_string(
        job.payload.get("rule_set_keys")
    )
    env["CODESCOPE_SCAN_RULE_KEYS"] = _json_list_string(job.payload.get("rule_keys"))
    env["CODESCOPE_SCAN_RESOLVED_RULE_KEYS"] = _json_list_string(
        job.payload.get("resolved_rule_keys")
    )

    joern_home = resolve_external_path(
        raw_value=settings.scan_external_joern_home or "",
        job=job,
        backend_root=backend_root,
    )
    configured_joern_bin = resolve_external_path(
        raw_value=settings.scan_external_joern_bin or "",
        job=job,
        backend_root=backend_root,
    )
    joern_bin = _resolve_joern_bin(
        joern_home=joern_home,
        configured_joern_bin=configured_joern_bin,
        runtime_profile=runtime_profile,
    )
    joern_export_script_raw = str(
        settings.scan_external_joern_export_script or ""
    ).strip()
    if not joern_export_script_raw:
        joern_export_script_raw = "./assets/scan/joern/export_java_min.sc"
    joern_export_script = resolve_external_path(
        raw_value=joern_export_script_raw,
        job=job,
        backend_root=backend_root,
    )
    env["CODESCOPE_SCAN_JOERN_HOME"] = str(joern_home) if joern_home else ""
    env["CODESCOPE_SCAN_JOERN_BIN"] = str(joern_bin) if joern_bin else ""
    env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"] = (
        str(joern_export_script) if joern_export_script else ""
    )

    post_labels_cypher = resolve_external_path(
        raw_value=settings.scan_external_post_labels_cypher or "",
        job=job,
        backend_root=backend_root,
    )
    rules_dir = resolve_external_path(
        raw_value=settings.scan_external_rules_dir or "",
        job=job,
        backend_root=backend_root,
    )
    env["CODESCOPE_SCAN_POST_LABELS_CYPHER"] = (
        str(post_labels_cypher) if post_labels_cypher else ""
    )
    env["CODESCOPE_SCAN_RULES_DIR"] = str(rules_dir) if rules_dir else ""

    resolved_neo4j_database = _resolve_database_name(
        raw_value=str(settings.scan_external_neo4j_database or ""),
        fallback="neo4j",
        job=job,
    )
    resolved_import_database = _resolve_database_name(
        raw_value=str(getattr(settings, "scan_external_import_database", "") or ""),
        fallback=resolved_neo4j_database,
        job=job,
    )
    resolved_neo4j_uri = _resolve_string_value(
        raw_value=str(settings.scan_external_neo4j_uri or ""),
        fallback="",
        job=job,
    )
    resolved_import_data_mount = _resolve_string_value(
        raw_value=str(getattr(settings, "scan_external_import_data_mount", "") or ""),
        fallback="",
        job=job,
    )
    resolved_runtime_container_name = _resolve_string_value(
        raw_value=str(
            getattr(settings, "scan_external_neo4j_runtime_container_name", "") or ""
        ),
        fallback="",
        job=job,
    )
    resolved_runtime_network = _resolve_string_value(
        raw_value=str(
            getattr(settings, "scan_external_neo4j_runtime_network", "") or ""
        ),
        fallback="",
        job=job,
    )
    resolved_runtime_network_alias = _resolve_string_value(
        raw_value=str(
            getattr(settings, "scan_external_neo4j_runtime_network_alias", "") or ""
        ),
        fallback="",
        job=job,
    )

    env["CODESCOPE_SCAN_NEO4J_URI"] = resolved_neo4j_uri
    env["CODESCOPE_SCAN_NEO4J_USER"] = str(settings.scan_external_neo4j_user or "")
    env["CODESCOPE_SCAN_NEO4J_PASSWORD"] = str(
        settings.scan_external_neo4j_password or ""
    )
    env["CODESCOPE_SCAN_NEO4J_DATABASE"] = resolved_neo4j_database
    env["CODESCOPE_SCAN_IMPORT_DATABASE"] = resolved_import_database
    env["CODESCOPE_SCAN_IMPORT_DATA_MOUNT"] = resolved_import_data_mount
    env["CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME"] = resolved_runtime_container_name
    env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK"] = resolved_runtime_network
    env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK_ALIAS"] = resolved_runtime_network_alias

    _validate_builtin_dependencies(
        settings=settings,
        stage_specs=resolved_stage_specs,
        joern_home=joern_home,
        joern_bin=joern_bin,
        joern_export_script=joern_export_script,
    )

    return env


def _resolve_database_name(*, raw_value: str, fallback: str, job: Job) -> str:
    return _resolve_string_value(raw_value=raw_value, fallback=fallback, job=job)


def _resolve_string_value(*, raw_value: str, fallback: str, job: Job) -> str:
    rendered = render_template(raw_value.strip(), job=job)
    normalized = rendered.strip()
    if normalized:
        return normalized
    return fallback.strip()


def _json_list_string(value: object) -> str:
    if not isinstance(value, list):
        return "[]"

    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            cleaned.append(text)
    return json.dumps(cleaned, ensure_ascii=False)


def _resolve_import_host_path(
    *,
    settings: Any,
    job: Job,
    backend_root: Path,
    import_dir: Path,
    runtime_profile: str,
) -> str:
    raw_host_path = str(settings.scan_external_import_csv_host_path or "").strip()
    if runtime_profile == CONTAINER_COMPAT_RUNTIME_PROFILE and not raw_host_path:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="容器兼容模式要求配置导入目录宿主机路径",
            detail={
                "required": "scan_external_import_csv_host_path",
                "runtime_profile": runtime_profile,
            },
        )
    if not raw_host_path:
        return str(import_dir)
    resolved = resolve_external_path(
        raw_value=raw_host_path,
        job=job,
        backend_root=backend_root,
    )
    if resolved is None:
        return str(import_dir)
    return str(resolved)


def _validate_joern_paths(
    *, joern_home: Path | None, joern_bin: Path | None, joern_export_script: Path | None
) -> None:
    if joern_home is None or not joern_home.exists() or not joern_home.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 工具目录不存在",
            detail={"joern_home": str(joern_home) if joern_home else ""},
        )
    if joern_bin is None or not joern_bin.exists() or not joern_bin.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 可执行文件不存在",
            detail={"joern_bin": str(joern_bin) if joern_bin else ""},
        )
    if (
        joern_export_script is None
        or not joern_export_script.exists()
        or not joern_export_script.is_file()
    ):
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 导出脚本不存在",
            detail={
                "joern_export_script": str(joern_export_script)
                if joern_export_script
                else ""
            },
        )


def _resolve_joern_bin(
    *,
    joern_home: Path | None,
    configured_joern_bin: Path | None,
    runtime_profile: str,
) -> Path | None:
    if joern_home is not None:
        if runtime_profile == WSL_RUNTIME_PROFILE:
            return joern_home / "joern"
        if os.name == "nt":
            windows_bin = joern_home / "joern.bat"
            if windows_bin.exists() and windows_bin.is_file():
                return windows_bin
        return joern_home / "joern"
    return configured_joern_bin


def _resolve_runtime_profile(*, settings: Any) -> str:
    configured = (
        str(getattr(settings, "scan_external_runtime_profile", "") or "")
        .strip()
        .lower()
    )
    compat_mode = bool(getattr(settings, "scan_external_container_compat_mode", False))
    if configured == CONTAINER_COMPAT_RUNTIME_PROFILE or compat_mode:
        return CONTAINER_COMPAT_RUNTIME_PROFILE
    return WSL_RUNTIME_PROFILE


def _is_builtin_stage_enabled(
    *, stage_specs: list[ExternalStageSpec], stage_key: str, builtin_key: str
) -> bool:
    for spec in stage_specs:
        if spec.key != stage_key:
            continue
        command = (spec.command or "").strip().lower()
        if command.startswith(f"builtin:{builtin_key}"):
            return True
    return False


def _validate_builtin_dependencies(
    *,
    settings: Any,
    stage_specs: list[ExternalStageSpec],
    joern_home: Path | None,
    joern_bin: Path | None,
    joern_export_script: Path | None,
) -> None:
    if _is_builtin_stage_enabled(
        stage_specs=stage_specs, stage_key="joern", builtin_key="joern"
    ):
        _validate_joern_paths(
            joern_home=joern_home,
            joern_bin=joern_bin,
            joern_export_script=joern_export_script,
        )

    if _is_builtin_stage_enabled(
        stage_specs=stage_specs, stage_key="neo4j_import", builtin_key="neo4j_import"
    ):
        _validate_import_settings(settings=settings)

    if (
        _is_builtin_stage_enabled(
            stage_specs=stage_specs,
            stage_key="neo4j_import",
            builtin_key="neo4j_import",
        )
        or _is_builtin_stage_enabled(
            stage_specs=stage_specs, stage_key="post_labels", builtin_key="post_labels"
        )
        or _is_builtin_stage_enabled(
            stage_specs=stage_specs, stage_key="rules", builtin_key="rules"
        )
    ):
        _validate_neo4j_settings(settings=settings)


def _validate_import_settings(*, settings: Any) -> None:
    image = str(settings.scan_external_import_docker_image or "").strip()
    if not image:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 导入镜像",
            detail={"required": "scan_external_import_docker_image"},
        )
    data_mount = str(settings.scan_external_import_data_mount or "").strip()
    if not data_mount:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j data 挂载点",
            detail={"required": "scan_external_import_data_mount"},
        )


def _validate_neo4j_settings(*, settings: Any) -> None:
    uri = str(settings.scan_external_neo4j_uri or "").strip()
    if not uri:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 连接地址",
            detail={"required": "scan_external_neo4j_uri"},
        )
    user = str(settings.scan_external_neo4j_user or "").strip()
    if not user:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 用户名",
            detail={"required": "scan_external_neo4j_user"},
        )
    database = str(settings.scan_external_neo4j_database or "").strip()
    if not database:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 数据库名",
            detail={"required": "scan_external_neo4j_database"},
        )
