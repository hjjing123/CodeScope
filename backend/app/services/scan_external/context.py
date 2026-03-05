from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.models import Job, JobStage, ScanMode

from .contracts import ExternalScanContext, ExternalStageSpec


def build_external_scan_context(*, job: Job, settings: Any, backend_root: Path) -> ExternalScanContext:
    reports_dir = _resolve_reports_dir(settings=settings, job=job, backend_root=backend_root)
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


def resolve_external_path(*, raw_value: str, job: Job, backend_root: Path) -> Path | None:
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

    reports_dir = resolve_external_path(raw_value=reports_dir_raw, job=job, backend_root=backend_root)
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

    workdir = resolve_external_path(raw_value=workdir_raw, job=job, backend_root=backend_root)
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


def _prepare_workspace_paths(*, settings: Any, job: Job, backend_root: Path) -> tuple[Path, Path, Path]:
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

    workspace_dir = workspace_root / str(job.id) / "external"
    import_dir = workspace_dir / "import_csv"
    cpg_file = workspace_dir / "code.bin"

    import_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir, import_dir, cpg_file


def _build_stage_specs(*, settings: Any) -> list[ExternalStageSpec]:
    legacy_command = (settings.scan_external_runner_command or "").strip()
    if legacy_command:
        return [
            ExternalStageSpec(
                key="legacy_runner",
                command=legacy_command,
                log_stage=JobStage.QUERY.value,
                timeout_seconds=_safe_timeout_seconds(settings.scan_external_timeout_seconds, default=3600),
                failure_code="SCAN_EXTERNAL_RUN_FAILED",
                timeout_code="SCAN_EXTERNAL_RUN_TIMEOUT",
            )
        ]

    return [
        ExternalStageSpec(
            key="joern",
            command=(settings.scan_external_stage_joern_command or "").strip(),
            log_stage=JobStage.ANALYZE.value,
            timeout_seconds=_safe_timeout_seconds(
                settings.scan_external_stage_joern_timeout_seconds,
                default=settings.scan_external_timeout_seconds,
            ),
            failure_code="SCAN_EXTERNAL_JOERN_FAILED",
            timeout_code="SCAN_EXTERNAL_JOERN_TIMEOUT",
        ),
        ExternalStageSpec(
            key="neo4j_import",
            command=(settings.scan_external_stage_import_command or "").strip(),
            log_stage=JobStage.ANALYZE.value,
            timeout_seconds=_safe_timeout_seconds(
                settings.scan_external_stage_import_timeout_seconds,
                default=settings.scan_external_timeout_seconds,
            ),
            failure_code="SCAN_EXTERNAL_IMPORT_FAILED",
            timeout_code="SCAN_EXTERNAL_IMPORT_TIMEOUT",
        ),
        ExternalStageSpec(
            key="post_labels",
            command=(settings.scan_external_stage_post_labels_command or "").strip(),
            log_stage=JobStage.QUERY.value,
            timeout_seconds=_safe_timeout_seconds(
                settings.scan_external_stage_post_labels_timeout_seconds,
                default=settings.scan_external_timeout_seconds,
            ),
            failure_code="SCAN_EXTERNAL_POST_LABELS_FAILED",
            timeout_code="SCAN_EXTERNAL_POST_LABELS_TIMEOUT",
        ),
        ExternalStageSpec(
            key="rules",
            command=(settings.scan_external_stage_rules_command or "").strip(),
            log_stage=JobStage.QUERY.value,
            timeout_seconds=_safe_timeout_seconds(
                settings.scan_external_stage_rules_timeout_seconds,
                default=settings.scan_external_timeout_seconds,
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
) -> dict[str, str]:
    env = dict(os.environ)
    scan_mode = str(job.payload.get("scan_mode", ScanMode.FULL.value))
    env["CODESCOPE_SCAN_JOB_ID"] = str(job.id)
    env["CODESCOPE_SCAN_PROJECT_ID"] = str(job.project_id)
    env["CODESCOPE_SCAN_VERSION_ID"] = str(job.version_id)
    env["CODESCOPE_SCAN_MODE"] = scan_mode
    env["CODESCOPE_SCAN_REPORTS_DIR"] = str(reports_dir)
    env["CODESCOPE_SCAN_SOURCE_DIR"] = str(source_dir)
    env["CODESCOPE_SCAN_IMPORT_DIR"] = str(import_dir)
    env["CODESCOPE_SCAN_CPG_FILE"] = str(cpg_file)

    joern_home = resolve_external_path(
        raw_value=settings.scan_external_joern_home or "",
        job=job,
        backend_root=backend_root,
    )
    joern_bin = resolve_external_path(
        raw_value=settings.scan_external_joern_bin or "",
        job=job,
        backend_root=backend_root,
    )
    joern_export_script = resolve_external_path(
        raw_value=settings.scan_external_joern_export_script or "",
        job=job,
        backend_root=backend_root,
    )
    env["CODESCOPE_SCAN_JOERN_HOME"] = str(joern_home) if joern_home else ""
    env["CODESCOPE_SCAN_JOERN_BIN"] = str(joern_bin) if joern_bin else ""
    env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"] = str(joern_export_script) if joern_export_script else ""

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
    rules_allowlist = resolve_external_path(
        raw_value=settings.scan_external_rules_allowlist_file or "",
        job=job,
        backend_root=backend_root,
    )
    env["CODESCOPE_SCAN_POST_LABELS_CYPHER"] = str(post_labels_cypher) if post_labels_cypher else ""
    env["CODESCOPE_SCAN_RULES_DIR"] = str(rules_dir) if rules_dir else ""
    env["CODESCOPE_SCAN_RULES_ALLOWLIST_FILE"] = str(rules_allowlist) if rules_allowlist else ""

    env["CODESCOPE_SCAN_NEO4J_URI"] = str(settings.scan_external_neo4j_uri or "")
    env["CODESCOPE_SCAN_NEO4J_USER"] = str(settings.scan_external_neo4j_user or "")
    env["CODESCOPE_SCAN_NEO4J_PASSWORD"] = str(settings.scan_external_neo4j_password or "")
    env["CODESCOPE_SCAN_NEO4J_DATABASE"] = str(settings.scan_external_neo4j_database or "")

    joern_stage_enabled = bool((settings.scan_external_stage_joern_command or "").strip())
    if joern_stage_enabled:
        _validate_joern_paths(
            joern_home=joern_home,
            joern_bin=joern_bin,
            joern_export_script=joern_export_script,
        )

    return env


def _validate_joern_paths(*, joern_home: Path | None, joern_bin: Path | None, joern_export_script: Path | None) -> None:
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
    if joern_export_script is None or not joern_export_script.exists() or not joern_export_script.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 导出脚本不存在",
            detail={
                "joern_export_script": str(joern_export_script) if joern_export_script else ""
            },
        )
