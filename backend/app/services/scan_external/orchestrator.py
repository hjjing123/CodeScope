from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from app.core.errors import AppError
from app.models import Job, JobStage

from .builtin import run_builtin_stage
from .context import build_external_scan_context, render_template
from .contracts import (
    ExternalScanContext,
    ExternalScanResult,
    ExternalStageResult,
    ExternalStageSpec,
)
from .runtime_metadata import load_runtime_metadata


ROUND_FILE_RE = re.compile(r"^round_(\d+)\.json$", re.IGNORECASE)


def run_external_scan(
    *,
    job: Job,
    settings: Any,
    backend_root: Path,
    append_log: Callable[[str, str], None],
    severity_from_rule_key: Callable[[str], str],
    on_stage_status: Callable[[str, str], None] | None = None,
) -> ExternalScanResult:
    context = build_external_scan_context(
        job=job, settings=settings, backend_root=backend_root
    )
    stage_results: list[ExternalStageResult] = []

    try:
        for spec in context.stage_specs:
            if on_stage_status is not None:
                on_stage_status(spec.key, "running")
            stage_results.append(
                _run_stage_command(
                    job=job,
                    settings=settings,
                    spec=spec,
                    context=context,
                    append_log=append_log,
                )
            )
            if on_stage_status is not None:
                on_stage_status(spec.key, "succeeded")
    except AppError as exc:
        detail = dict(exc.detail) if isinstance(exc.detail, dict) else {}
        failed_stage = detail.pop("stage_result", None)
        failed_stage_key = str(detail.get("stage") or "")
        if on_stage_status is not None and failed_stage_key:
            on_stage_status(failed_stage_key, "failed")
        executed = [item.to_summary() for item in stage_results]
        if isinstance(failed_stage, dict):
            executed.append(failed_stage)
        detail["executed_stages"] = executed
        raise AppError(
            code=exc.code,
            status_code=exc.status_code,
            message=exc.message,
            detail=detail,
        ) from exc

    if not context.reports_dir.exists() or not context.reports_dir.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_MISSING",
            status_code=422,
            message="外部扫描结果目录不存在",
            detail={"reports_dir": str(context.reports_dir)},
        )

    round_number, round_report = _load_latest_round_report(context.reports_dir)
    append_log(
        JobStage.AGGREGATE.value,
        f"读取外部结果 round={round_number}, reports_dir={context.reports_dir}",
    )

    rule_rows_raw = round_report.get("rule_rows")
    rule_summary_raw = round_report.get("rule_summary")
    if not isinstance(rule_rows_raw, dict) or not isinstance(rule_summary_raw, dict):
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_INVALID",
            status_code=422,
            message="外部扫描结果缺少 rule_rows 或 rule_summary",
        )

    rule_rows: dict[str, int] = {}
    for key, value in rule_rows_raw.items():
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 0
        rule_rows[str(key)] = parsed

    hit_rules = [rule for rule, rows in rule_rows.items() if rows > 0]
    findings = [
        {"rule_key": rule_key, "severity": severity_from_rule_key(rule_key)}
        for rule_key in sorted(hit_rules)
    ]

    audit_summary = _load_external_audit_summary(
        reports_dir=context.reports_dir, round_number=round_number
    )
    audit_cases = sum(_safe_int(item.get("cases", 0)) for item in audit_summary)

    execution_summary_raw = (
        round_report.get("execution_summary")
        if isinstance(round_report.get("execution_summary"), dict)
        else {}
    )
    rule_results = _normalize_rule_results(round_report.get("rule_results"))
    failed_rule_keys = _normalize_failed_rule_keys(
        execution_summary_raw.get("failed_rule_keys")
    )
    partial_failures = _normalize_partial_failures(round_report.get("partial_failures"))
    runtime_metadata = load_runtime_metadata(reports_dir=context.reports_dir)

    summary_extra: dict[str, object] = {
        "external_round": round_number,
        "total_rules": _safe_int(
            rule_summary_raw.get("total_rules"), default=len(rule_rows)
        ),
        "hit_rules": _safe_int(
            rule_summary_raw.get("hit_rules"), default=len(hit_rules)
        ),
        "zero_rules": _safe_int(
            rule_summary_raw.get("zero_rules"),
            default=max(0, len(rule_rows) - len(hit_rules)),
        ),
        "total_rows": _safe_int(
            rule_summary_raw.get("total_rows"), default=sum(rule_rows.values())
        ),
        "exported_rule_count": len(audit_summary),
        "exported_case_count": audit_cases,
        "succeeded_rules": _safe_int(
            execution_summary_raw.get("succeeded_rules"),
            default=max(0, len(rule_rows) - len(partial_failures)),
        ),
        "failed_rules": _safe_int(
            execution_summary_raw.get("failed_rules"),
            default=len(partial_failures),
        ),
        "failed_rule_keys": failed_rule_keys,
        "rules_failure_mode": str(
            execution_summary_raw.get("failure_mode") or "permissive"
        ),
        "partial_failure_effect": str(
            execution_summary_raw.get("partial_failure_effect") or "none"
        ),
        "partial_failures": partial_failures,
        "rule_execution": {
            "summary": {
                "total_rules": _safe_int(
                    execution_summary_raw.get("total_rules"),
                    default=_safe_int(
                        rule_summary_raw.get("total_rules"), default=len(rule_rows)
                    ),
                ),
                "executed_rules": _safe_int(
                    execution_summary_raw.get("executed_rules"),
                    default=len(rule_rows),
                ),
                "succeeded_rules": _safe_int(
                    execution_summary_raw.get("succeeded_rules"),
                    default=max(0, len(rule_rows) - len(partial_failures)),
                ),
                "failed_rules": _safe_int(
                    execution_summary_raw.get("failed_rules"),
                    default=len(partial_failures),
                ),
                "failure_mode": str(
                    execution_summary_raw.get("failure_mode") or "permissive"
                ),
                "partial_failure_effect": str(
                    execution_summary_raw.get("partial_failure_effect") or "none"
                ),
                "has_partial_failures": bool(partial_failures),
            },
            "rule_rows": dict(rule_rows),
            "rule_results": rule_results,
            "partial_failures": partial_failures,
        },
        "neo4j_runtime": {
            "uri": str(context.base_env.get("CODESCOPE_SCAN_NEO4J_URI") or ""),
            "database": str(
                context.base_env.get("CODESCOPE_SCAN_NEO4J_DATABASE") or ""
            ),
            "import_database": str(
                context.base_env.get("CODESCOPE_SCAN_IMPORT_DATABASE") or ""
            ),
            "data_mount": str(
                context.base_env.get("CODESCOPE_SCAN_IMPORT_DATA_MOUNT") or ""
            ),
            "container_name": str(
                context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME")
                or ""
            ),
            "network": str(
                context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK") or ""
            ),
            "network_alias": str(
                context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK_ALIAS") or ""
            ),
            "restart_mode": str(
                getattr(settings, "scan_external_neo4j_runtime_restart_mode", "none")
                or "none"
            ),
            "runtime_profile": str(
                context.base_env.get("CODESCOPE_SCAN_RUNTIME_PROFILE") or ""
            ),
            **runtime_metadata,
        },
        "external_stages": [item.to_summary() for item in stage_results],
        "reports_dir": str(context.reports_dir),
    }
    return ExternalScanResult(findings=findings, summary_extra=summary_extra)


def _run_stage_command(
    *,
    job: Job,
    settings: Any,
    spec: ExternalStageSpec,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
) -> ExternalStageResult:
    command = render_template(spec.command, job=job).strip()
    if not command:
        append_log(spec.log_stage, f"[{spec.key}] 未配置命令，跳过。")
        return ExternalStageResult(
            key=spec.key,
            log_stage=spec.log_stage,
            skipped=True,
            exit_code=None,
            timeout_seconds=spec.timeout_seconds,
            duration_ms=0,
            stdout_tail="",
            stderr_tail="",
        )

    append_log(spec.log_stage, f"[{spec.key}] 执行命令: {command}")
    started_at = time.monotonic()
    env = {**context.base_env, "CODESCOPE_SCAN_EXTERNAL_STAGE": spec.key}

    try:
        if command.lower().startswith("builtin:"):
            builtin_key = command.split(":", 1)[1].strip().lower()
            stdout_raw, stderr_raw = run_builtin_stage(
                builtin_key=builtin_key,
                job=job,
                settings=settings,
                context=context,
                append_log=append_log,
                timeout_seconds=spec.timeout_seconds,
            )
            result = subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=stdout_raw,
                stderr=stderr_raw,
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=spec.timeout_seconds,
                check=False,
                cwd=context.workdir,
                env=env,
            )
    except AppError as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        detail = dict(exc.detail) if isinstance(exc.detail, dict) else {}
        if "stage_result" not in detail:
            detail["stage_result"] = {
                "stage": spec.key,
                "job_stage": spec.log_stage,
                "status": "failed",
                "exit_code": detail.get("exit_code"),
                "timeout_seconds": spec.timeout_seconds,
                "duration_ms": duration_ms,
                "stdout_tail": detail.get("stdout_tail", ""),
                "stderr_tail": detail.get("stderr_tail", ""),
            }
        raise AppError(
            code=exc.code,
            status_code=exc.status_code,
            message=exc.message,
            detail=detail,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        stdout_tail = _tail_text(
            _normalize_process_output(getattr(exc, "stdout", None))
        )
        stderr_tail = _tail_text(
            _normalize_process_output(getattr(exc, "stderr", None))
        )
        if stdout_tail:
            append_log(spec.log_stage, f"[{spec.key}] stdout: {stdout_tail}")
        if stderr_tail:
            append_log(spec.log_stage, f"[{spec.key}] stderr: {stderr_tail}")

        failed_stage = ExternalStageResult(
            key=spec.key,
            log_stage=spec.log_stage,
            skipped=False,
            exit_code=None,
            timeout_seconds=spec.timeout_seconds,
            duration_ms=duration_ms,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            timed_out=True,
        )
        raise AppError(
            code=spec.timeout_code,
            status_code=422,
            message=f"外部阶段 {spec.key} 执行超时",
            detail={
                "stage": spec.key,
                "timeout_seconds": spec.timeout_seconds,
                "duration_ms": duration_ms,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
                "stage_result": failed_stage.to_summary(),
            },
        ) from exc
    except TimeoutError as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        failed_stage = ExternalStageResult(
            key=spec.key,
            log_stage=spec.log_stage,
            skipped=False,
            exit_code=None,
            timeout_seconds=spec.timeout_seconds,
            duration_ms=duration_ms,
            stdout_tail="",
            stderr_tail="",
            timed_out=True,
        )
        raise AppError(
            code=spec.timeout_code,
            status_code=422,
            message=f"外部阶段 {spec.key} 执行超时",
            detail={
                "stage": spec.key,
                "timeout_seconds": spec.timeout_seconds,
                "duration_ms": duration_ms,
                "error": str(exc),
                "stage_result": failed_stage.to_summary(),
            },
        ) from exc
    except Exception as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        raise AppError(
            code=spec.failure_code,
            status_code=422,
            message=f"外部阶段 {spec.key} 执行异常",
            detail={
                "stage": spec.key,
                "duration_ms": duration_ms,
                "error": str(exc),
            },
        ) from exc

    duration_ms = int((time.monotonic() - started_at) * 1000)
    stdout_tail = _tail_text(_normalize_process_output(result.stdout))
    stderr_tail = _tail_text(_normalize_process_output(result.stderr))
    if stdout_tail:
        append_log(spec.log_stage, f"[{spec.key}] stdout: {stdout_tail}")
    if stderr_tail:
        append_log(spec.log_stage, f"[{spec.key}] stderr: {stderr_tail}")

    stage_result = ExternalStageResult(
        key=spec.key,
        log_stage=spec.log_stage,
        skipped=False,
        exit_code=result.returncode,
        timeout_seconds=spec.timeout_seconds,
        duration_ms=duration_ms,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
    )
    if result.returncode != 0:
        raise AppError(
            code=spec.failure_code,
            status_code=422,
            message=f"外部阶段 {spec.key} 执行失败",
            detail={
                "stage": spec.key,
                "exit_code": result.returncode,
                "duration_ms": duration_ms,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
                "stage_result": stage_result.to_summary(),
            },
        )

    append_log(
        spec.log_stage,
        f"[{spec.key}] 执行完成: exit_code={result.returncode}, duration_ms={duration_ms}",
    )
    return stage_result


def _load_latest_round_report(reports_dir: Path) -> tuple[int, dict[str, object]]:
    latest_number = -1
    latest_path: Path | None = None
    for item in reports_dir.iterdir():
        if not item.is_file():
            continue
        match = ROUND_FILE_RE.match(item.name)
        if match is None:
            continue
        number = int(match.group(1))
        if number > latest_number:
            latest_number = number
            latest_path = item

    if latest_path is None:
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_MISSING",
            status_code=422,
            message="未找到 round_*.json",
        )

    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_INVALID",
            status_code=422,
            message="round 结果文件解析失败",
        ) from exc

    if not isinstance(payload, dict):
        raise AppError(
            code="SCAN_EXTERNAL_RESULT_INVALID",
            status_code=422,
            message="round 结果文件结构不正确",
        )

    return latest_number, payload


def _load_external_audit_summary(
    reports_dir: Path, round_number: int
) -> list[dict[str, object]]:
    summary_path = (
        reports_dir / "audit_output" / f"round{round_number}" / "summary.json"
    )
    if not summary_path.exists() or not summary_path.is_file():
        return []

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _normalize_partial_failures(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(dict(item))
    return normalized


def _normalize_rule_results(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(dict(item))
    return normalized


def _normalize_failed_rule_keys(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if not key:
            continue
        marker = key.lower()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(key)
    return normalized


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_process_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _tail_text(value: str, max_chars: int = 2000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]
