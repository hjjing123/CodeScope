from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROUND_FILE_RE = re.compile(r"^round_(\d+)\.json$", re.IGNORECASE)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class StageError(RuntimeError):
    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


@dataclass(slots=True)
class StageContext:
    job_id: str
    project_id: str
    version_id: str
    scan_mode: str
    reports_dir: Path
    workspace_root: Path
    snapshot_root: Path
    joern_home: Path | None
    joern_bin: Path | None
    joern_export_script: Path | None
    post_labels_script: Path | None
    rules_dir: Path | None
    rule_set_ids: list[str]
    target_rule_id: str
    stage_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "StageContext":
        job_id = _required_env("CODESCOPE_SCAN_JOB_ID")
        project_id = _required_env("CODESCOPE_SCAN_PROJECT_ID")
        version_id = _required_env("CODESCOPE_SCAN_VERSION_ID")
        scan_mode = _optional_env("CODESCOPE_SCAN_MODE", "FULL")

        reports_dir = _resolve_path(
            _optional_env("CODESCOPE_SCAN_REPORTS_DIR", "../graph_pipeline/reports")
        )
        workspace_root = _resolve_path(
            _optional_env("CODESCOPE_SCAN_WORKSPACE_ROOT", "./storage/workspaces/scans")
        )
        snapshot_root = _resolve_path(
            _optional_env("CODESCOPE_SNAPSHOT_STORAGE_ROOT", "./storage/snapshots")
        )

        joern_home = _resolve_optional_path(_optional_env("CODESCOPE_SCAN_JOERN_HOME", ""))
        joern_bin = _resolve_optional_path(_optional_env("CODESCOPE_SCAN_JOERN_BIN", ""))
        joern_export_script = _resolve_optional_path(
            _optional_env("CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT", "")
        )
        post_labels_script = _resolve_optional_path(
            _optional_env("CODESCOPE_SCAN_EXTERNAL_POST_LABELS_FILE", "")
        )
        rules_dir = _resolve_optional_path(_optional_env("CODESCOPE_SCAN_EXTERNAL_RULES_DIR", ""))

        stage_timeout_seconds = _safe_int(
            _optional_env("CODESCOPE_SCAN_EXTERNAL_STAGE_TIMEOUT_SECONDS", "3600"),
            default=3600,
        )
        rule_set_ids = _json_list_env("CODESCOPE_SCAN_RULE_SET_IDS")
        target_rule_id = _optional_env("CODESCOPE_SCAN_TARGET_RULE_ID", "")

        return cls(
            job_id=job_id,
            project_id=project_id,
            version_id=version_id,
            scan_mode=scan_mode,
            reports_dir=reports_dir,
            workspace_root=workspace_root,
            snapshot_root=snapshot_root,
            joern_home=joern_home,
            joern_bin=joern_bin,
            joern_export_script=joern_export_script,
            post_labels_script=post_labels_script,
            rules_dir=rules_dir,
            rule_set_ids=rule_set_ids,
            target_rule_id=target_rule_id,
            stage_timeout_seconds=max(1, stage_timeout_seconds),
        )

    def workspace_dir(self) -> Path:
        return ensure_dir(self.workspace_root / self.job_id / "external")

    def render(self, template: str, *, extra: dict[str, str] | None = None) -> str:
        rendered = template
        replacements = {
            "{job_id}": self.job_id,
            "{project_id}": self.project_id,
            "{version_id}": self.version_id,
            "{scan_mode}": self.scan_mode,
            "{reports_dir}": str(self.reports_dir),
            "{workspace_dir}": str(self.workspace_dir()),
            "{snapshot_root}": str(self.snapshot_root),
            "{joern_home}": str(self.joern_home) if self.joern_home else "",
            "{joern_bin}": str(self.joern_bin) if self.joern_bin else "",
            "{joern_export_script}": str(self.joern_export_script) if self.joern_export_script else "",
            "{post_labels_script}": str(self.post_labels_script) if self.post_labels_script else "",
            "{rules_dir}": str(self.rules_dir) if self.rules_dir else "",
        }
        if extra:
            replacements.update(extra)

        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        return rendered


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise StageError(f"missing required env: {name}")
    return value


def _optional_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _safe_int(raw: str, *, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _json_list_env(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    result: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)
    return result


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    return path


def _resolve_optional_path(raw: str) -> Path | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    return _resolve_path(cleaned)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StageError("failed to parse json file", detail={"path": str(path), "error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise StageError("json file must be an object", detail={"path": str(path)})
    return payload


def find_latest_round(reports_dir: Path) -> int:
    latest = 0
    if not reports_dir.exists() or not reports_dir.is_dir():
        return latest
    for item in reports_dir.iterdir():
        if not item.is_file():
            continue
        match = ROUND_FILE_RE.match(item.name)
        if match is None:
            continue
        latest = max(latest, int(match.group(1)))
    return latest


def run_process(
    args: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        raise StageError(
            "command timeout",
            detail={
                "command": " ".join(shlex.quote(item) for item in args),
                "timeout_seconds": timeout_seconds,
                "duration_ms": duration_ms,
            },
        ) from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise StageError(
            "command failed",
            detail={
                "command": " ".join(shlex.quote(item) for item in args),
                "exit_code": result.returncode,
                "duration_ms": duration_ms,
            },
        )

    return {
        "command": " ".join(shlex.quote(item) for item in args),
        "exit_code": result.returncode,
        "duration_ms": duration_ms,
    }


def run_shell_command(
    command: str,
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        raise StageError(
            "shell command timeout",
            detail={
                "command": command,
                "timeout_seconds": timeout_seconds,
                "duration_ms": duration_ms,
            },
        ) from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise StageError(
            "shell command failed",
            detail={
                "command": command,
                "exit_code": result.returncode,
                "duration_ms": duration_ms,
            },
        )
    return {
        "command": command,
        "exit_code": result.returncode,
        "duration_ms": duration_ms,
    }


def run_stage(main_fn) -> None:
    try:
        main_fn()
    except StageError as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "detail": exc.detail,
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from exc
