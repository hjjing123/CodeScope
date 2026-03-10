from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.config import get_settings
from app.services import artifact_service as artifact_service_module
from app.services import scan_service as scan_service_module


def test_attach_code_contexts_and_ai_payloads_use_snapshot_source(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        '  String input = request.getParameter("id");\n'
        '  String sql = "select * from user where id=" + input;\n'
        "  statement.executeQuery(sql);\n"
        "}\n",
        encoding="utf-8",
    )

    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding_drafts = [
            {
                "rule_key": "any_any_sqli",
                "severity": "HIGH",
                "vuln_type": "SQLI",
                "file_path": "src/Main.java",
                "line_start": 3,
                "line_end": 4,
                "source": {"file": "src/Main.java", "line": 2},
                "sink": {"file": "src/Main.java", "line": 4},
                "evidence": {"items": ["request.id", "executeQuery"]},
                "trace_summary": "request -> sql -> executeQuery",
                "has_path": True,
                "path_length": 3,
            }
        ]

        enriched = scan_service_module._attach_code_contexts(
            job=SimpleNamespace(version_id=version_id),
            finding_drafts=finding_drafts,
        )
        assert enriched[0]["code_context"]["focus"]["file_path"] == "src/Main.java"
        assert "3:   String sql" in enriched[0]["code_context"]["focus"]["snippet"]

        llm_enriched = scan_service_module._attach_ai_payloads(enriched)
        payload = llm_enriched[0]["llm_payload"]
        assert payload["why_flagged"]
        assert payload["code_context"]["focus"]
        assert "Code:" in llm_enriched[0]["llm_prompt_block"]
        assert "Reason:" in llm_enriched[0]["llm_prompt_block"]
    finally:
        settings.snapshot_storage_root = old_snapshot_root


def test_run_stub_scan_emits_snapshot_location_when_source_exists(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "README.md").write_text("hello\nworld\n", encoding="utf-8")

    settings.snapshot_storage_root = str(tmp_path)
    try:
        result = scan_service_module._run_stub_scan(
            job=SimpleNamespace(
                id=uuid.uuid4(),
                version_id=version_id,
                payload={"rule_keys": ["any_any_xss"]},
            )
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert result.findings
    first = result.findings[0]
    assert first["file_path"] == "README.md"
    assert first["line_start"] == 1
    assert first["sink_line"] >= 1


def test_write_scan_result_archive_persists_job_summary(tmp_path: Path) -> None:
    settings = get_settings()
    old_log_root = settings.scan_log_root
    settings.scan_log_root = str(tmp_path / "job-logs")
    job_id = uuid.uuid4()
    try:
        archive = scan_service_module._write_scan_result_archive(
            job=SimpleNamespace(
                id=job_id,
                project_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                job_type="SCAN",
                status="SUCCEEDED",
                stage="CLEANUP",
                failure_code=None,
                failure_stage=None,
                failure_category=None,
                failure_hint=None,
                started_at=None,
                finished_at=None,
                result_summary={"total_findings": 2, "partial_failures": []},
            )
        )
        archive_path = Path(archive["path"])
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
    finally:
        settings.scan_log_root = old_log_root

    assert archive_path.exists()
    assert payload["job_id"] == str(job_id)
    assert payload["status"] == "SUCCEEDED"
    assert payload["result_summary"]["total_findings"] == 2


def test_list_job_artifacts_includes_scan_result_archive(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    old_log_root = settings.scan_log_root
    settings.snapshot_storage_root = str(tmp_path / "snapshots")
    settings.scan_log_root = str(tmp_path / "job-logs")
    job_id = uuid.uuid4()
    version_id = uuid.uuid4()
    try:
        log_dir = Path(settings.scan_log_root) / str(job_id)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "prepare.log").write_text("prepare\n", encoding="utf-8")
        (log_dir / "scan_result.json").write_text("{}\n", encoding="utf-8")

        snapshot_dir = Path(settings.snapshot_storage_root) / str(version_id)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "snapshot.tar.gz").write_bytes(b"snapshot")

        items = artifact_service_module.list_job_artifacts(
            job=SimpleNamespace(id=job_id, version_id=version_id, result_summary={})
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        settings.scan_log_root = old_log_root

    artifact_types = {item["artifact_type"] for item in items}
    assert "LOG" in artifact_types
    assert "ARCHIVE" in artifact_types
    assert "SNAPSHOT" in artifact_types


def test_cleanup_external_neo4j_database_drops_job_scoped_database(
    monkeypatch,
) -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = True
    captured: dict[str, object] = {}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    try:
        monkeypatch.setattr(
            scan_service_module,
            "drop_database_if_exists",
            lambda **kwargs: captured.update(kwargs),
        )
        monkeypatch.setattr(
            scan_service_module,
            "_load_external_runtime_metadata",
            lambda **kwargs: {},
        )
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=job,
            result_summary={
                "neo4j_runtime": {
                    "uri": "bolt://127.0.0.1:17687",
                    "database": "scan_job_123",
                }
            },
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert captured["uri"] == "bolt://127.0.0.1:17687"
    assert captured["database"] == "scan_job_123"
    assert summary["cleanup_attempted"] is True
    assert summary["cleanup_succeeded"] is True


def test_cleanup_external_neo4j_database_skips_protected_database() -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = True
    try:
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=SimpleNamespace(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
            ),
            result_summary={"neo4j_runtime": {"database": "neo4j"}},
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert summary["cleanup_attempted"] is False
    assert summary["cleanup_succeeded"] is False
    assert summary["cleanup_skipped_reason"] == "protected_database"


def test_cleanup_external_neo4j_database_cleans_ephemeral_runtime_even_when_db_cleanup_disabled(
    monkeypatch,
) -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = False
    captured: dict[str, object] = {}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    try:
        monkeypatch.setattr(
            scan_service_module,
            "cleanup_ephemeral_runtime_resources",
            lambda **kwargs: (
                captured.update(kwargs)
                or {
                    "container_cleanup_attempted": True,
                    "container_cleanup_succeeded": True,
                    "data_cleanup_attempted": True,
                    "data_cleanup_succeeded": True,
                    "network_cleanup_attempted": True,
                    "network_cleanup_succeeded": True,
                }
            ),
        )
        monkeypatch.setattr(
            scan_service_module,
            "_load_external_runtime_metadata",
            lambda **kwargs: {},
        )
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=job,
            result_summary={
                "neo4j_runtime": {
                    "restart_mode": "docker_ephemeral",
                    "container_name": "neo4j-job-1",
                    "data_mount": "/tmp/neo4j-job-1",
                    "network": "codescope-net-job-1",
                    "network_created_by_job": True,
                }
            },
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert captured["container_name"] == "neo4j-job-1"
    assert captured["data_mount"] == "/tmp/neo4j-job-1"
    assert captured["network_name"] == "codescope-net-job-1"
    assert captured["cleanup_network"] is True
    assert summary["cleanup_attempted"] is True
    assert summary["cleanup_succeeded"] is True
    assert summary["container_cleanup_succeeded"] is True
    assert summary["data_cleanup_succeeded"] is True
    assert summary["network_cleanup_succeeded"] is True
