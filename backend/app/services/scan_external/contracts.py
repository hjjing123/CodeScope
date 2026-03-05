from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ExternalStageSpec:
    key: str
    command: str
    log_stage: str
    timeout_seconds: int
    failure_code: str
    timeout_code: str


@dataclass(slots=True)
class ExternalStageResult:
    key: str
    log_stage: str
    skipped: bool
    exit_code: int | None
    timeout_seconds: int
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    timed_out: bool = False

    def to_summary(self) -> dict[str, object]:
        status = "skipped" if self.skipped else "succeeded"
        if self.timed_out:
            status = "timeout"
        return {
            "stage": self.key,
            "job_stage": self.log_stage,
            "status": status,
            "exit_code": self.exit_code,
            "timeout_seconds": self.timeout_seconds,
            "duration_ms": self.duration_ms,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass(slots=True)
class ExternalScanContext:
    reports_dir: Path
    workdir: str | None
    base_env: dict[str, str]
    stage_specs: list[ExternalStageSpec]
    backend_root: Path
    source_dir: Path
    workspace_dir: Path
    import_dir: Path
    cpg_file: Path


@dataclass(slots=True)
class ExternalScanResult:
    findings: list[dict[str, str]]
    summary_extra: dict[str, object]
