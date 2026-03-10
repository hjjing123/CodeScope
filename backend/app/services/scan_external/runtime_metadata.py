from __future__ import annotations

import json
from pathlib import Path


RUNTIME_METADATA_FILE_NAME = "neo4j_runtime_meta.json"


def runtime_metadata_path(*, reports_dir: Path) -> Path:
    return reports_dir / RUNTIME_METADATA_FILE_NAME


def load_runtime_metadata(*, reports_dir: Path) -> dict[str, object]:
    target = runtime_metadata_path(reports_dir=reports_dir)
    if not target.exists() or not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_runtime_metadata(*, reports_dir: Path, payload: dict[str, object]) -> None:
    target = runtime_metadata_path(reports_dir=reports_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def merge_runtime_metadata(
    *, reports_dir: Path, section: str, payload: dict[str, object] | None
) -> dict[str, object]:
    current = load_runtime_metadata(reports_dir=reports_dir)
    if payload is None:
        current.pop(section, None)
    else:
        current[section] = payload
    write_runtime_metadata(reports_dir=reports_dir, payload=current)
    return current
