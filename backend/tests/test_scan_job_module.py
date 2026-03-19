from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    Finding,
    FindingLabel,
    Job,
    JobStepStatus,
    JobStage,
    JobStatus,
    JobType,
    Project,
    ProjectRole,
    SystemRole,
    User,
    UserProjectRole,
    Version,
    VersionSource,
    VersionStatus,
    utc_now,
)
from app.services.job_stream_service import append_job_stream_event
from app.security.password import hash_password


def _create_user(
    db,
    *,
    email: str,
    password: str,
    role: str,
    display_name: str = "tester",
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, *, email: str, password: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _create_project(db, *, name: str) -> Project:
    project = Project(name=name, description="scan-test")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _add_member(
    db, *, user_id: uuid.UUID, project_id: uuid.UUID, role: str
) -> UserProjectRole:
    member = UserProjectRole(user_id=user_id, project_id=project_id, project_role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _create_version(db, *, project_id: uuid.UUID, name: str = "v1") -> Version:
    version = Version(
        project_id=project_id,
        name=name,
        source=VersionSource.UPLOAD.value,
        snapshot_object_key=f"snapshots/{name}.zip",
        status=VersionStatus.READY.value,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def _seed_snapshot_object_key(files: dict[str, str]) -> str:
    source_version_id = uuid.uuid4()
    snapshot_base = Path(get_settings().snapshot_storage_root) / str(source_version_id)
    source_dir = snapshot_base / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        file_path = source_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    archive_path = snapshot_base / "snapshot.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for child in source_dir.rglob("*"):
            archive.add(child, arcname=child.relative_to(source_dir).as_posix())

    return f"snapshots/{source_version_id}/snapshot.tar.gz"


@pytest.fixture()
def external_scan_settings(tmp_path: Path):
    settings = get_settings()
    tracked_keys = [
        "scan_engine_mode",
        "scan_dispatch_backend",
        "scan_dispatch_fallback_to_sync",
        "snapshot_storage_root",
        "scan_workspace_root",
        "scan_external_runner_command",
        "scan_external_runner_workdir",
        "scan_external_reports_dir",
        "scan_external_timeout_seconds",
        "scan_external_joern_home",
        "scan_external_joern_bin",
        "scan_external_joern_export_script",
        "scan_external_post_labels_cypher",
        "scan_external_rules_dir",
        "scan_external_rule_sets_dir",
        "scan_external_rules_max_count",
        "scan_external_neo4j_uri",
        "scan_external_neo4j_user",
        "scan_external_neo4j_password",
        "scan_external_neo4j_database",
        "scan_external_neo4j_connect_retry",
        "scan_external_neo4j_connect_wait_seconds",
        "scan_external_import_docker_image",
        "scan_external_import_data_mount",
        "scan_external_import_csv_host_path",
        "scan_external_import_database",
        "scan_external_import_id_type",
        "scan_external_import_array_delimiter",
        "scan_external_import_clean_db",
        "scan_external_import_multiline_fields",
        "scan_external_import_multiline_fields_format",
        "scan_external_import_preflight",
        "scan_external_import_preflight_check_docker",
        "scan_external_neo4j_runtime_restart_mode",
        "scan_external_neo4j_runtime_container_name",
        "scan_external_neo4j_runtime_restart_wait_seconds",
        "scan_external_stage_joern_command",
        "scan_external_stage_import_command",
        "scan_external_stage_post_labels_command",
        "scan_external_stage_source_semantic_command",
        "scan_external_stage_rules_command",
        "scan_external_stage_joern_timeout_seconds",
        "scan_external_stage_import_timeout_seconds",
        "scan_external_stage_post_labels_timeout_seconds",
        "scan_external_stage_source_semantic_timeout_seconds",
        "scan_external_stage_rules_timeout_seconds",
    ]
    old_values = {key: getattr(settings, key) for key in tracked_keys}

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    scan_workspace_root = tmp_path / "scan-workspaces"
    scan_workspace_root.mkdir(parents=True, exist_ok=True)
    post_labels_file = tmp_path / "post_labels.cypher"
    post_labels_file.write_text("RETURN 0;\n", encoding="utf-8")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "sample.cypher").write_text("RETURN 0;\n", encoding="utf-8")
    rule_sets_dir = tmp_path / "rule-sets"
    rule_sets_dir.mkdir(parents=True, exist_ok=True)

    joern_home = tmp_path / "joern-cli"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    joern_parse_bin = joern_home / "joern-parse"
    joern_parse_bin.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    joern_export_script = tmp_path / "export_java_min.sc"
    joern_export_script.write_text("// test export script\n", encoding="utf-8")

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_dispatch_fallback_to_sync = True
    settings.snapshot_storage_root = str(snapshot_root)
    settings.scan_workspace_root = str(scan_workspace_root)
    settings.scan_external_runner_command = ""
    settings.scan_external_runner_workdir = str(tmp_path)
    settings.scan_external_reports_dir = str(reports_dir / "{job_id}")
    settings.scan_external_timeout_seconds = 30
    settings.scan_external_joern_home = str(joern_home)
    settings.scan_external_joern_bin = str(joern_bin)
    settings.scan_external_joern_export_script = str(joern_export_script)
    settings.scan_external_post_labels_cypher = str(post_labels_file)
    settings.scan_external_rules_dir = str(rules_dir)
    settings.scan_external_rule_sets_dir = str(rule_sets_dir)
    settings.scan_external_rules_max_count = 0
    settings.scan_external_neo4j_uri = "bolt://127.0.0.1:7687"
    settings.scan_external_neo4j_user = "neo4j"
    settings.scan_external_neo4j_password = ""
    settings.scan_external_neo4j_database = "neo4j"
    settings.scan_external_neo4j_connect_retry = 1
    settings.scan_external_neo4j_connect_wait_seconds = 1
    settings.scan_external_import_docker_image = "neo4j:5.26"
    settings.scan_external_import_data_mount = "data"
    settings.scan_external_import_csv_host_path = ""
    settings.scan_external_import_database = "neo4j"
    settings.scan_external_import_id_type = "string"
    settings.scan_external_import_array_delimiter = "\\001"
    settings.scan_external_import_clean_db = False
    settings.scan_external_import_multiline_fields = True
    settings.scan_external_import_multiline_fields_format = ""
    settings.scan_external_import_preflight = False
    settings.scan_external_import_preflight_check_docker = True
    settings.scan_external_neo4j_runtime_restart_mode = "none"
    settings.scan_external_neo4j_runtime_container_name = "CodeScope_neo4j"
    settings.scan_external_neo4j_runtime_restart_wait_seconds = 0
    settings.scan_external_stage_joern_command = "stage-joern-{job_id}"
    settings.scan_external_stage_import_command = "stage-import-{job_id}"
    settings.scan_external_stage_post_labels_command = "stage-post-labels-{job_id}"
    settings.scan_external_stage_source_semantic_command = (
        "stage-source-semantic-{job_id}"
    )
    settings.scan_external_stage_rules_command = "stage-rules-{job_id}"
    settings.scan_external_stage_joern_timeout_seconds = 30
    settings.scan_external_stage_import_timeout_seconds = 30
    settings.scan_external_stage_post_labels_timeout_seconds = 30
    settings.scan_external_stage_source_semantic_timeout_seconds = 30
    settings.scan_external_stage_rules_timeout_seconds = 30

    try:
        yield {"settings": settings, "reports_dir": reports_dir}
    finally:
        for key, value in old_values.items():
            setattr(settings, key, value)


@pytest.fixture()
def rule_set_settings(tmp_path: Path):
    settings = get_settings()
    old_value = settings.scan_external_rule_sets_dir
    rule_sets_dir = tmp_path / "rule-sets"
    rule_sets_dir.mkdir(parents=True, exist_ok=True)
    settings.scan_external_rule_sets_dir = str(rule_sets_dir)
    try:
        yield rule_sets_dir
    finally:
        settings.scan_external_rule_sets_dir = old_value
        shutil.rmtree(rule_sets_dir, ignore_errors=True)


def _write_round_report(
    reports_dir: Path,
    *,
    rule_rows: dict[str, int] | None = None,
    round_number: int = 1,
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows = rule_rows or {
        "any_any_xss.cypher": 2,
        "any_any_urlredirect.cypher": 0,
    }
    payload = {
        "rule_rows": rows,
        "rule_summary": {
            "total_rules": len(rows),
            "hit_rules": sum(1 for value in rows.values() if int(value) > 0),
            "zero_rules": sum(1 for value in rows.values() if int(value) <= 0),
            "total_rows": sum(int(value) for value in rows.values()),
        },
    }
    (reports_dir / f"round_{round_number}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        chunk = block.strip()
        if not chunk:
            continue
        payload: dict[str, object] = {"event": "message", "id": None, "data": {}}
        data_lines: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                payload["event"] = line.split(":", 1)[1].strip()
                continue
            if line.startswith("id:"):
                raw_id = line.split(":", 1)[1].strip()
                try:
                    payload["id"] = int(raw_id)
                except ValueError:
                    payload["id"] = None
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            payload["data"] = json.loads("\n".join(data_lines))
        events.append(payload)
    return events


def test_scan_job_create_and_get_succeeds(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "scan\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss", "any_any_urlredirect"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    job_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert job_resp.status_code == 200
    assert job_resp.json()["data"]["job_type"] == "SCAN"
    assert job_resp.json()["data"]["status"] == "SUCCEEDED"
    assert job_resp.json()["data"]["stage"] == JobStage.CLEANUP.value
    assert job_resp.json()["data"]["result_summary"]["engine_mode"] == "stub"
    assert job_resp.json()["data"]["result_summary"]["total_findings"] >= 1


def test_scan_job_cleanup_failure_marks_job_failed_and_logs_reason(
    client, db_session, monkeypatch: pytest.MonkeyPatch
):
    from app.services import scan_service as scan_service_module

    release_calls = {"count": 0}

    def _fake_release_scan_workspace(*, job):
        release_calls["count"] += 1
        if release_calls["count"] == 1:
            raise RuntimeError("cleanup boom")
        return {
            "workspace_dir": f"workspace/{job.id}",
            "workspace_existed_before": True,
            "workspace_exists_after": False,
            "workspace_released": True,
            "workspace_cleanup_error": None,
        }

    monkeypatch.setattr(
        scan_service_module,
        "_release_scan_workspace",
        _fake_release_scan_workspace,
    )

    developer = _create_user(
        db_session,
        email="scan-cleanup-fail@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-cleanup-fail-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-cleanup-fail-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "cleanup\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    job_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert job_resp.status_code == 200
    payload = job_resp.json()["data"]
    assert payload["status"] == JobStatus.FAILED.value
    assert payload["failure_stage"] == JobStage.CLEANUP.value
    assert payload["progress"]["current_step"] == "cleanup"
    step_by_key = {item["step_key"]: item for item in payload["steps"]}
    assert step_by_key["archive"]["status"] == JobStepStatus.SUCCEEDED.value
    assert step_by_key["cleanup"]["status"] == JobStepStatus.FAILED.value

    log_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": JobStage.CLEANUP.value, "tail": 50},
    )
    assert log_resp.status_code == 200
    joined = "\n".join(log_resp.json()["data"]["items"][0]["lines"])
    assert "cleanup boom" in joined
    assert "任务失败" in joined or "任务异常收口" in joined


def test_scan_job_defaults_to_full_mode_and_all_rules(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-defaults@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-default-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-default-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "scan-default\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    job_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert job_resp.status_code == 200
    payload = job_resp.json()["data"]["payload"]
    assert "scan_mode" not in payload
    assert payload["rule_set_keys"] == []
    assert payload["rule_keys"] == []
    assert len(payload["resolved_rule_keys"]) > 0


def test_delete_scan_job_selected_content_keeps_job_record(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-delete-content@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-delete-content-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-delete-content-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "scan\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    settings = get_settings()
    external_workspace = (
        Path(settings.scan_workspace_root) / project_id / job_id / "external"
    )
    external_workspace.mkdir(parents=True, exist_ok=True)
    (external_workspace / "temp.txt").write_text("workspace", encoding="utf-8")
    legacy_workspace = Path(settings.scan_workspace_root) / job_id
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "legacy.txt").write_text("legacy", encoding="utf-8")

    findings_before = db_session.scalars(
        select(Finding.id).where(Finding.job_id == uuid.UUID(job_id))
    ).all()
    assert findings_before

    delete_resp = client.post(
        f"/api/v1/jobs/{job_id}/delete",
        headers=_auth_header(tokens["access_token"]),
        json={"targets": ["logs", "artifacts", "workspace"]},
    )
    assert delete_resp.status_code == 200, delete_resp.text
    payload = delete_resp.json()["data"]
    assert payload["deleted_job_record"] is False
    assert payload["deleted_log_files_count"] >= 1
    assert payload["deleted_archive_files_count"] >= 1
    assert payload["deleted_workspace_paths_count"] >= 1

    job_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert job_resp.status_code == 200

    logs_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs", headers=_auth_header(tokens["access_token"])
    )
    assert logs_resp.status_code == 200
    assert logs_resp.json()["data"]["items"] == []

    artifacts_resp = client.get(
        f"/api/v1/jobs/{job_id}/artifacts", headers=_auth_header(tokens["access_token"])
    )
    assert artifacts_resp.status_code == 200
    remaining_sources = {
        item["source"] for item in artifacts_resp.json()["data"]["items"]
    }
    assert "scan_log" not in remaining_sources
    assert "scan_workspace" not in remaining_sources
    assert "external_reports" not in remaining_sources

    findings_after = db_session.scalars(
        select(Finding.id).where(Finding.job_id == uuid.UUID(job_id))
    ).all()
    assert len(findings_after) == len(findings_before)


def test_delete_scan_job_record_forces_findings_removal(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-delete-job@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-delete-job-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-delete-job-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "scan\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    delete_resp = client.post(
        f"/api/v1/jobs/{job_id}/delete",
        headers=_auth_header(tokens["access_token"]),
        json={"targets": ["job_record"]},
    )
    assert delete_resp.status_code == 200, delete_resp.text
    payload = delete_resp.json()["data"]
    assert payload["deleted_job_record"] is True
    assert payload["forced_targets"] == ["findings"]
    assert payload["deleted_findings_count"] >= 1

    job_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert job_resp.status_code == 404

    remaining_findings = db_session.scalars(
        select(Finding.id).where(Finding.job_id == uuid.UUID(job_id))
    ).all()
    assert remaining_findings == []


def test_scan_job_accepts_rule_set_keys_and_rule_keys_union(
    client, db_session, rule_set_settings
):
    admin = _create_user(
        db_session,
        email="scan-ruleset-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    rule_set_resp = client.post(
        "/api/v1/rule-sets",
        headers=_auth_header(tokens["access_token"]),
        json={
            "key": "scan-default",
            "name": "scan-default",
            "description": "scan defaults",
        },
    )
    assert rule_set_resp.status_code == 201
    rule_set_id = rule_set_resp.json()["data"]["id"]

    bind_resp = client.post(
        f"/api/v1/rule-sets/{rule_set_id}/rules",
        headers=_auth_header(tokens["access_token"]),
        json={"rule_keys": ["any_any_xss"]},
    )
    assert bind_resp.status_code == 200

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-ruleset-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-ruleset-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "scan-ruleset\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_set_keys": ["scan-default"],
            "rule_keys": ["any_any_urlredirect"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["payload"]["rule_set_keys"] == ["scan-default"]
    assert payload["payload"]["rule_keys"] == ["any_any_urlredirect"]
    assert payload["payload"]["resolved_rule_keys"] == [
        "any_any_xss",
        "any_any_urlredirect",
    ]


def test_scan_job_idempotency_replay(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-idem@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-idem-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-idem-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "idem\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    key = "scan-idem-001"
    first_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={"project_id": project_id, "version_id": version_id},
    )
    assert first_resp.status_code == 202
    first_job_id = first_resp.json()["data"]["job_id"]
    assert first_resp.json()["data"]["idempotent_replay"] is False

    second_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={"project_id": project_id, "version_id": version_id},
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["data"]["idempotent_replay"] is True
    assert second_resp.json()["data"]["job_id"] == first_job_id


def test_scan_job_idempotency_conflict(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-idem-conflict@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-idem-conflict-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-idem-c-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "idem-c\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    key = "scan-idem-002"
    first_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss"],
        },
    )
    assert first_resp.status_code == 202

    second_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_urlredirect"],
        },
    )
    assert second_resp.status_code == 409
    assert second_resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_scan_job_rejects_legacy_rule_set_ids_field(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-legacy-field@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-legacy-field-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-legacy-field-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "legacy\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_set_ids": ["any_any_xss"],
        },
    )
    assert create_resp.status_code == 422


def test_scan_job_rejects_legacy_scan_mode_and_target_rule_id_fields(
    client, db_session
):
    developer = _create_user(
        db_session,
        email="scan-legacy-mode@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-legacy-mode-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-legacy-mode-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "legacy-mode\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "scan_mode": "FULL",
            "target_rule_id": "any_any_xss",
        },
    )
    assert create_resp.status_code == 422


def test_scan_job_requires_project_membership(client, db_session):
    owner = _create_user(
        db_session,
        email="scan-owner@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    outsider = _create_user(
        db_session,
        email="scan-outsider@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    owner_tokens = _login(client, email=owner.email, password="Password123!")
    outsider_tokens = _login(client, email=outsider.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"name": "scan-member-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "name": "scan-member-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "member\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    scan_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert scan_resp.status_code == 202
    job_id = scan_resp.json()["data"]["job_id"]

    denied_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert denied_resp.status_code == 403
    assert denied_resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"


def test_scan_job_cancel_running(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-cancel@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="scan-cancel-project")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(db_session, project_id=project.id, name="scan-cancel-v1")
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        payload={"request_id": "req_cancel", "rule_keys": []},
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        created_by=developer.id,
        started_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    workspace_dir = (
        Path(get_settings().scan_workspace_root)
        / str(project.id)
        / str(job.id)
        / "external"
    )
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "temp.txt").write_text("cancel\n", encoding="utf-8")

    tokens = _login(client, email=developer.email, password="Password123!")
    cancel_resp = client.post(
        f"/api/v1/jobs/{job.id}/cancel", headers=_auth_header(tokens["access_token"])
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["status"] == JobStatus.CANCELED.value

    detail_resp = client.get(
        f"/api/v1/jobs/{job.id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.CANCELED.value
    assert payload["progress"]["percent"] == 10
    assert payload["result_summary"]["cleanup"]["workspace_released"] is True
    step_by_key = {item["step_key"]: item["status"] for item in payload["steps"]}
    assert all(status != JobStepStatus.RUNNING.value for status in step_by_key.values())
    assert any(
        status == JobStepStatus.CANCELED.value for status in step_by_key.values()
    )
    assert not workspace_dir.exists()


def test_scan_job_retry_failed(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-retry@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="scan-retry-project")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(db_session, project_id=project.id, name="scan-retry-v1")
    failed_job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        payload={
            "request_id": "req_retry",
            "scan_mode": "VERIFY",
            "target_rule_id": "verify.rule",
        },
        status=JobStatus.FAILED.value,
        stage=JobStage.QUERY.value,
        failure_code="SCAN_INTERNAL_ERROR",
        created_by=developer.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    db_session.add(failed_job)
    db_session.commit()
    db_session.refresh(failed_job)

    tokens = _login(client, email=developer.email, password="Password123!")
    retry_resp = client.post(
        f"/api/v1/jobs/{failed_job.id}/retry",
        headers=_auth_header(tokens["access_token"]),
    )
    assert retry_resp.status_code == 202
    retried_job_id = retry_resp.json()["data"]["job_id"]
    assert retried_job_id != str(failed_job.id)

    detail_resp = client.get(
        f"/api/v1/jobs/{retried_job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["status"] == JobStatus.SUCCEEDED.value
    assert detail_resp.json()["data"]["payload"]["retry_of_job_id"] == str(
        failed_job.id
    )
    assert "scan_mode" not in detail_resp.json()["data"]["payload"]
    assert "target_rule_id" not in detail_resp.json()["data"]["payload"]


def test_list_jobs_non_admin_is_project_scoped(client, db_session):
    user = _create_user(
        db_session,
        email="scan-scope-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    admin = _create_user(
        db_session,
        email="scan-scope-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )

    project_a = _create_project(db_session, name="scope-project-a")
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project_a.id,
        role=ProjectRole.OWNER.value,
    )
    version_a = _create_version(db_session, project_id=project_a.id, name="scope-a-v1")

    project_b = _create_project(db_session, name="scope-project-b")
    _add_member(
        db_session,
        user_id=admin.id,
        project_id=project_b.id,
        role=ProjectRole.OWNER.value,
    )
    version_b = _create_version(db_session, project_id=project_b.id, name="scope-b-v1")

    job_a = Job(
        project_id=project_a.id,
        version_id=version_a.id,
        job_type=JobType.SCAN.value,
        payload={"request_id": "req_scope_a"},
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        created_by=user.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    job_b = Job(
        project_id=project_b.id,
        version_id=version_b.id,
        job_type=JobType.SCAN.value,
        payload={"request_id": "req_scope_b"},
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        created_by=admin.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    db_session.add(job_a)
    db_session.add(job_b)
    db_session.commit()

    tokens = _login(client, email=user.email, password="Password123!")
    list_resp = client.get("/api/v1/jobs", headers=_auth_header(tokens["access_token"]))
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["project_id"] == str(project_a.id)
    assert items[0]["project_name"] == "scope-project-a"
    assert items[0]["version_name"] == "scope-a-v1"


def test_get_job_returns_project_and_version_names(client, db_session):
    user = _create_user(
        db_session,
        email="scan-job-names@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="job-name-project")
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(db_session, project_id=project.id, name="job-name-v1")
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        payload={"request_id": "req_job_names"},
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        created_by=user.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()

    tokens = _login(client, email=user.email, password="Password123!")
    detail_resp = client.get(
        f"/api/v1/jobs/{job.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["project_id"] == str(project.id)
    assert payload["project_name"] == "job-name-project"
    assert payload["version_id"] == str(version.id)
    assert payload["version_name"] == "job-name-v1"


def test_scan_job_logs_endpoint_returns_stage_logs(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-logs@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-logs-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-logs-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "logs\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    logs_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs",
        headers=_auth_header(tokens["access_token"]),
    )
    assert logs_resp.status_code == 200
    items = logs_resp.json()["data"]["items"]
    assert len(items) >= 1
    assert any(item["stage"] == JobStage.PREPARE.value for item in items)


def test_scan_job_logs_endpoint_supports_full_log_output(client, db_session):
    from app.services.task_log_service import append_task_log

    developer = _create_user(
        db_session,
        email="scan-full-logs@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="scan-full-logs-project")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(
        db_session, project_id=project.id, name="scan-full-logs-v1"
    )
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        payload={"request_id": "req-full-logs"},
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        created_by=developer.id,
        started_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    for index in range(205):
        append_task_log(
            task_type="SCAN",
            task_id=job.id,
            stage=JobStage.QUERY.value,
            message=f"full-log-line-{index}",
            project_id=project.id,
        )

    tokens = _login(client, email=developer.email, password="Password123!")

    logs_resp = client.get(
        f"/api/v1/jobs/{job.id}/logs",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": JobStage.QUERY.value},
    )
    assert logs_resp.status_code == 200
    default_item = logs_resp.json()["data"]["items"][0]
    assert default_item["stage"] == JobStage.QUERY.value
    assert default_item["truncated"] is True
    assert default_item["line_count"] == 205
    assert len(default_item["lines"]) == 200
    assert "full-log-line-0" not in "\n".join(default_item["lines"])
    assert "full-log-line-204" in default_item["lines"][-1]

    full_logs_resp = client.get(
        f"/api/v1/jobs/{job.id}/logs",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": JobStage.QUERY.value, "tail": 0},
    )
    assert full_logs_resp.status_code == 200
    full_item = full_logs_resp.json()["data"]["items"][0]
    assert full_item["stage"] == JobStage.QUERY.value
    assert full_item["truncated"] is False
    assert full_item["line_count"] == 205
    assert len(full_item["lines"]) == 205
    assert "full-log-line-0" in full_item["lines"][0]
    assert "full-log-line-204" in full_item["lines"][-1]


def test_findings_list_supports_job_id_filter(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-findings@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-findings-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-findings-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "findings\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss", "any_any_urlredirect"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    findings_resp = client.get(
        "/api/v1/findings",
        headers=_auth_header(tokens["access_token"]),
        params={"job_id": job_id},
    )
    assert findings_resp.status_code == 200
    payload = findings_resp.json()["data"]
    assert payload["total"] >= 1
    assert all(item["job_id"] == job_id for item in payload["items"])
    assert "rule_version" in payload["items"][0]
    assert "evidence_json" in payload["items"][0]


def test_scan_job_result_summary_contains_finding_drafts_and_ai_payload(
    client, db_session
):
    developer = _create_user(
        db_session,
        email="scan-draft-ai@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-draft-ai-project"},
    )
    project_id = project_resp.json()["data"]["id"]
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-draft-ai-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"src/Main.java": "class Main {}"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["any_any_xss"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    drafts = payload["result_summary"]["finding_drafts"]
    assert drafts
    first = drafts[0]
    required = {
        "rule_key",
        "severity",
        "file_path",
        "line_start",
        "line_end",
        "source",
        "sink",
        "evidence",
        "trace_summary",
        "code_context",
        "llm_payload",
        "llm_prompt_block",
    }
    assert required.issubset(first.keys())
    assert isinstance(first["code_context"], dict)
    assert "focus" in first["code_context"]
    assert isinstance(first["llm_payload"], dict)
    assert isinstance(first["llm_prompt_block"], str)
    assert isinstance(first["llm_payload"]["code_context"], dict)
    assert first["llm_payload"]["why_flagged"]
    assert "Code:" in first["llm_prompt_block"]
    assert len(first["llm_prompt_block"]) <= 1600
    assert payload["result_summary"]["ai_summary"]["code_context_ready"] >= 1


def test_scan_job_skips_invalid_finding_draft_before_persist(
    client, db_session, monkeypatch: pytest.MonkeyPatch
):
    from app.services import scan_service as scan_service_module

    def fake_stub_scan(*, job):
        return scan_service_module.ScanExecutionResult(
            findings=[
                {"rule_key": "", "severity": "HIGH"},
                {"rule_key": "any_any_xss", "severity": "MED", "evidence": {"k": "v"}},
            ],
            result_summary={
                "engine_mode": "stub",
                "total_findings": 2,
                "severity_counts": {"HIGH": 1, "MED": 1, "LOW": 0},
                "hit_rule_count": 1,
                "partial_failures": [],
            },
        )

    monkeypatch.setattr(scan_service_module, "_run_stub_scan", fake_stub_scan)

    developer = _create_user(
        db_session,
        email="scan-draft-validate@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-draft-validate-project"},
    )
    project_id = project_resp.json()["data"]["id"]
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-draft-validate-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "validate\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["result_summary"]["normalized_finding_count"] == 1

    findings_resp = client.get(
        "/api/v1/findings",
        headers=_auth_header(tokens["access_token"]),
        params={"job_id": job_id},
    )
    assert findings_resp.status_code == 200
    assert findings_resp.json()["data"]["total"] == 1


def test_scan_job_log_stream_supports_seq_resume_and_stage_filter(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-sse@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-sse-project"},
    )
    project_id = project_resp.json()["data"]["id"]
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-sse-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key({"README.md": "sse\n"}),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    stream_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs/stream",
        headers=_auth_header(tokens["access_token"]),
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")
    events = _parse_sse_events(stream_resp.text)
    log_events = [item for item in events if item["event"] == "log"]
    done_events = [item for item in events if item["event"] == "done"]
    assert log_events
    assert done_events
    seqs = [int(item["data"]["seq"]) for item in log_events]
    assert seqs == sorted(seqs)

    resume_seq = seqs[max(0, len(seqs) // 2 - 1)]
    resumed_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs/stream",
        headers=_auth_header(tokens["access_token"]),
        params={"seq": resume_seq},
    )
    assert resumed_resp.status_code == 200
    resumed_events = _parse_sse_events(resumed_resp.text)
    resumed_log_events = [item for item in resumed_events if item["event"] == "log"]
    assert resumed_log_events
    assert all(int(item["data"]["seq"]) > resume_seq for item in resumed_log_events)

    stage_resp = client.get(
        f"/api/v1/jobs/{job_id}/logs/stream",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": "Prepare"},
    )
    assert stage_resp.status_code == 200
    stage_events = _parse_sse_events(stage_resp.text)
    stage_logs = [item for item in stage_events if item["event"] == "log"]
    assert stage_logs
    assert all(item["data"]["stage"] == JobStage.PREPARE.value for item in stage_logs)


def test_scan_job_event_stream_returns_persisted_events(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-event-stream@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")
    project = _create_project(db_session, name="scan-event-stream-project")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(db_session, project_id=project.id, name="event-stream-v1")
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        payload={},
        result_summary={},
        created_by=developer.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    db_session.add(job)
    db_session.flush()
    append_job_stream_event(
        db_session,
        job_id=job.id,
        project_id=project.id,
        event_type="summary_update",
        payload={"total_findings": 3, "severity_counts": {"HIGH": 1}},
    )
    db_session.commit()

    stream_resp = client.get(
        f"/api/v1/jobs/{job.id}/events/stream",
        headers=_auth_header(tokens["access_token"]),
    )

    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")
    events = _parse_sse_events(stream_resp.text)
    assert events[0]["event"] == "summary_update"
    assert events[0]["data"]["payload"]["total_findings"] == 3
    assert events[-1]["event"] == "done"


def test_scan_job_external_stage_orchestration_succeeds(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module
    from app.services import scan_service as scan_service_module

    reports_dir: Path = external_scan_settings["reports_dir"]

    commands: list[str] = []
    cleanup_statuses: list[str] = []

    def _fake_run(command, **kwargs):
        commands.append(command)
        command_text = str(command)
        marker = "stage-rules-"
        if marker in command_text:
            suffix = command_text.split(marker, 1)[1].strip().split()[0]
            _write_round_report(reports_dir / suffix)
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="ok", stderr=""
        )

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)
    original_release_scan_workspace = scan_service_module._release_scan_workspace

    def _capture_release_scan_workspace(*, job):
        cleanup_statuses.append(job.status)
        return original_release_scan_workspace(job=job)

    monkeypatch.setattr(
        scan_service_module,
        "_release_scan_workspace",
        _capture_release_scan_workspace,
    )

    developer = _create_user(
        db_session,
        email="scan-external-success@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-success-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-success-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-success\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["progress"]["percent"] == 100
    assert payload["progress"]["completed_steps"] == len(payload["steps"])
    assert all(
        item["status"] == JobStepStatus.SUCCEEDED.value for item in payload["steps"]
    )
    assert payload["result_summary"]["engine_mode"] == "external"
    assert payload["result_summary"]["hit_rules"] == 1
    assert "rule_execution" in payload["result_summary"]
    assert "summary" in payload["result_summary"]["rule_execution"]
    assert "rule_results" in payload["result_summary"]["rule_execution"]
    assert len(payload["result_summary"]["external_stages"]) == 5
    assert all(
        item["status"] == "succeeded"
        for item in payload["result_summary"]["external_stages"]
    )
    assert len(commands) == 5
    assert cleanup_statuses == [JobStatus.RUNNING.value]
    workspace_dir = (
        Path(external_scan_settings["settings"].scan_workspace_root)
        / project_id
        / job_id
        / "external"
    )
    assert payload["result_summary"]["cleanup"]["workspace_released"] is True
    assert not workspace_dir.exists()


def test_scan_job_external_joern_failure_maps_failure_code(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module

    def _fake_run(command, **kwargs):
        if "stage-joern" in command:
            return subprocess.CompletedProcess(
                args=command, returncode=13, stdout="", stderr="joern failed"
            )
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="ok", stderr=""
        )

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)

    developer = _create_user(
        db_session,
        email="scan-external-joern-failed@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-joern-failed-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-joern-failed-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-joern\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.FAILED.value
    assert payload["failure_code"] == "SCAN_EXTERNAL_JOERN_FAILED"
    step_by_key = {item["step_key"]: item for item in payload["steps"]}
    assert step_by_key["prepare"]["status"] == JobStepStatus.SUCCEEDED.value
    assert step_by_key["joern"]["status"] == JobStepStatus.FAILED.value
    assert step_by_key["neo4j_import"]["status"] == JobStepStatus.CANCELED.value
    workspace_dir = (
        Path(external_scan_settings["settings"].scan_workspace_root)
        / project_id
        / job_id
        / "external"
    )
    assert payload["result_summary"]["cleanup"]["workspace_released"] is True
    assert not workspace_dir.exists()


def test_scan_job_external_builtin_joern_contract_failure_maps_failure_code(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import builtin as builtin_module

    settings = external_scan_settings["settings"]
    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_source_semantic_command = "builtin:source_semantic"
    settings.scan_external_stage_rules_command = "builtin:rules"

    def _fake_run_builtin_command(command, *, deadline, env=None):
        if "--script" in command:
            out_dir = Path(env["outDir"]) if env else None
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "nodes_File_header.csv").write_text("h\n", encoding="utf-8")
                (out_dir / "nodes_File_data.csv").write_text("d\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "export-ok", "")
        return subprocess.CompletedProcess(command, 0, "parse-ok", "")

    monkeypatch.setattr(
        builtin_module, "_run_command_with_deadline", _fake_run_builtin_command
    )

    developer = _create_user(
        db_session,
        email="scan-external-builtin-joern-contract@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-builtin-joern-contract-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-builtin-joern-contract-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-builtin-joern-contract\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.FAILED.value
    assert payload["failure_code"] == "SCAN_EXTERNAL_JOERN_FAILED"


def test_scan_job_external_rules_timeout_maps_failure_code(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module

    def _fake_run(command, **kwargs):
        if "stage-rules" in command:
            raise subprocess.TimeoutExpired(cmd=command, timeout=30)
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="ok", stderr=""
        )

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)

    developer = _create_user(
        db_session,
        email="scan-external-rules-timeout@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-rules-timeout-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-rules-timeout-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-rules\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.TIMEOUT.value
    assert payload["failure_code"] == "SCAN_EXTERNAL_RULES_TIMEOUT"
    step_by_key = {item["step_key"]: item for item in payload["steps"]}
    assert step_by_key["rules"]["status"] == JobStepStatus.FAILED.value
    assert step_by_key["aggregate"]["status"] == JobStepStatus.CANCELED.value
    workspace_dir = (
        Path(external_scan_settings["settings"].scan_workspace_root)
        / project_id
        / job_id
        / "external"
    )
    assert payload["result_summary"]["cleanup"]["workspace_released"] is True
    assert not workspace_dir.exists()


def test_scan_job_external_builtin_stage_pipeline(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module

    settings = external_scan_settings["settings"]
    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_source_semantic_command = "builtin:source_semantic"
    settings.scan_external_stage_rules_command = "builtin:rules"
    joern_home = Path(settings.scan_external_joern_home)
    windows_joern_bin = joern_home / "joern.bat"
    windows_joern_bin.write_text("@echo off\n", encoding="utf-8")
    settings.scan_external_joern_bin = str(windows_joern_bin)

    executed: list[str] = []
    captured_paths: dict[str, str] = {}

    def _fake_builtin_stage(
        *,
        builtin_key,
        job,
        settings,
        context,
        append_log,
        timeout_seconds,
        on_rule_finding=None,
    ):
        executed.append(str(builtin_key))
        if builtin_key == "joern":
            captured_paths["joern_bin"] = context.base_env.get(
                "CODESCOPE_SCAN_JOERN_BIN", ""
            )
            captured_paths["import_dir"] = str(context.import_dir)
            captured_paths["cpg_file"] = str(context.cpg_file)
        if builtin_key == "rules":
            _write_round_report(context.reports_dir)
        return f"{builtin_key} ok", ""

    monkeypatch.setattr(orchestrator_module, "run_builtin_stage", _fake_builtin_stage)

    developer = _create_user(
        db_session,
        email="scan-external-builtin@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-builtin-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-builtin-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-builtin\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    source_dir = Path(settings.snapshot_storage_root) / version_id / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "App.java").write_text("class App {}\n", encoding="utf-8")

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert executed == [
        "joern",
        "neo4j_import",
        "post_labels",
        "source_semantic",
        "rules",
    ]
    assert captured_paths["joern_bin"] == str(joern_home / "joern")
    assert Path(captured_paths["import_dir"]).parts[-4:] == (
        project_id,
        job_id,
        "external",
        "import_csv",
    )
    assert Path(captured_paths["cpg_file"]).parts[-4:] == (
        project_id,
        job_id,
        "external",
        "code.bin",
    )


def test_scan_job_external_builtin_stage_pipeline_paths_stable_across_retries(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module

    settings = external_scan_settings["settings"]
    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_source_semantic_command = "builtin:source_semantic"
    settings.scan_external_stage_rules_command = "builtin:rules"

    joern_runs: list[dict[str, str]] = []

    def _fake_builtin_stage(
        *,
        builtin_key,
        job,
        settings,
        context,
        append_log,
        timeout_seconds,
        on_rule_finding=None,
    ):
        if builtin_key == "joern":
            joern_runs.append(
                {
                    "import_dir": str(context.import_dir),
                    "cpg_file": str(context.cpg_file),
                }
            )
        if builtin_key == "rules":
            _write_round_report(context.reports_dir)
        return f"{builtin_key} ok", ""

    monkeypatch.setattr(orchestrator_module, "run_builtin_stage", _fake_builtin_stage)

    developer = _create_user(
        db_session,
        email="scan-external-builtin-stable@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-builtin-stable-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-builtin-stable-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-builtin-stable\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    job_ids: list[str] = []
    for _ in range(2):
        create_resp = client.post(
            "/api/v1/scan-jobs",
            headers=_auth_header(tokens["access_token"]),
            json={"project_id": project_id, "version_id": version_id},
        )
        assert create_resp.status_code == 202
        job_id = create_resp.json()["data"]["job_id"]
        job_ids.append(job_id)
        detail_resp = client.get(
            f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["data"]["status"] == JobStatus.SUCCEEDED.value

    assert len(joern_runs) == 2
    assert joern_runs[0]["import_dir"] != joern_runs[1]["import_dir"]
    assert joern_runs[0]["cpg_file"] != joern_runs[1]["cpg_file"]
    assert Path(joern_runs[0]["import_dir"]).parts[-4:] == (
        project_id,
        job_ids[0],
        "external",
        "import_csv",
    )
    assert Path(joern_runs[1]["import_dir"]).parts[-4:] == (
        project_id,
        job_ids[1],
        "external",
        "import_csv",
    )
    assert Path(joern_runs[0]["cpg_file"]).parts[-4:] == (
        project_id,
        job_ids[0],
        "external",
        "code.bin",
    )
    assert Path(joern_runs[1]["cpg_file"]).parts[-4:] == (
        project_id,
        job_ids[1],
        "external",
        "code.bin",
    )


def test_builtin_neo4j_import_creates_runtime_container_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external.builtin import _run_builtin_neo4j_import
    from app.services.scan_external.context import build_external_scan_context

    settings = external_scan_settings["settings"]
    settings.scan_external_stage_joern_command = ""
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = ""
    settings.scan_external_stage_source_semantic_command = ""
    settings.scan_external_stage_rules_command = ""
    settings.scan_external_neo4j_runtime_restart_mode = "docker"
    settings.scan_external_neo4j_runtime_container_name = "CodeScope_neo4j"
    settings.scan_external_import_data_mount = "codescope_neo4j_data"
    settings.scan_external_neo4j_password = "codescope123"

    project_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()
    source_dir = Path(settings.snapshot_storage_root) / str(version_id) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "README.md").write_text("scan\n", encoding="utf-8")

    job = Job(
        id=job_id,
        project_id=project_id,
        version_id=version_id,
        job_type=JobType.SCAN.value,
        status=JobStatus.RUNNING.value,
        stage=JobStage.ANALYZE.value,
        payload={},
        result_summary={},
    )
    context = build_external_scan_context(
        job=job,
        settings=settings,
        backend_root=Path(__file__).resolve().parents[1],
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.scan_external.builtin._ensure_docker_cli_available",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._detect_neo4j_major",
        lambda *, image, deadline: 5,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._collect_csv_pairs",
        lambda import_dir, *, failure_code: (
            [("File", "nodes_File_header.csv", "nodes_File_data.csv")],
            [("AST", "edges_AST_header.csv", "edges_AST_data.csv")],
        ),
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._build_admin_parts",
        lambda **kwargs: ["neo4j-admin", "database", "import", "full", "neo4j"],
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._container_exists",
        lambda *, container_name, deadline: False,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._is_container_running",
        lambda *, container_name, deadline: False,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._resolve_import_host_mount_path",
        lambda *, context, runtime_profile: "/tmp/import_csv",
    )

    def fake_run_command(command, *, deadline, env=None, cwd=None):
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="IMPORT DONE",
            stderr="",
        )

    def fake_run_runtime_container(**kwargs):
        captured["runtime_container"] = kwargs
        return {}

    def fake_wait_runtime_ready(**kwargs):
        captured["runtime_ready"] = kwargs

    monkeypatch.setattr(
        "app.services.scan_external.builtin._run_command_with_deadline",
        fake_run_command,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._run_ephemeral_runtime_container",
        fake_run_runtime_container,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._wait_for_ephemeral_runtime_ready",
        fake_wait_runtime_ready,
    )
    monkeypatch.setattr(
        "app.services.scan_external.builtin._start_container",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("should not start existing container")
        ),
    )

    stdout, stderr = _run_builtin_neo4j_import(
        settings=settings,
        context=context,
        append_log=lambda stage, message: None,
        deadline=1_000_000_000.0,
    )

    assert stdout == "IMPORT DONE"
    assert stderr == ""
    assert captured["runtime_container"]["container_name"] == "CodeScope_neo4j"
    assert captured["runtime_container"]["data_mount"] == "codescope_neo4j_data"
    assert captured["runtime_container"]["uri"] == "bolt://127.0.0.1:7687"
    assert captured["runtime_ready"]["container_name"] == "CodeScope_neo4j"


def test_scan_job_external_builtin_rules_honors_string_rule_names(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import builtin as builtin_module
    from app.services.scan_external.neo4j_runner import CypherExecutionSummary

    settings = external_scan_settings["settings"]
    rules_dir = Path(settings.scan_external_rules_dir)
    (rules_dir / "rule_a.cypher").write_text("RETURN 1;\n", encoding="utf-8")
    (rules_dir / "rule_b.cypher").write_text("RETURN 1;\n", encoding="utf-8")

    settings.scan_external_stage_joern_command = ""
    settings.scan_external_stage_import_command = ""
    settings.scan_external_stage_post_labels_command = ""
    settings.scan_external_stage_source_semantic_command = ""
    settings.scan_external_stage_rules_command = "builtin:rules"

    executed_rules: list[str] = []

    def _fake_execute_cypher_file(**kwargs):
        executed_rules.append(Path(kwargs["cypher_file"]).name)
        return CypherExecutionSummary(statement_count=1, total_rows=1, row_counts=[1])

    monkeypatch.setattr(
        builtin_module, "execute_cypher_file_stream", _fake_execute_cypher_file
    )

    developer = _create_user(
        db_session,
        email="scan-external-rule-filter@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-rule-filter-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-rule-filter-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-rule-filter\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["rule_b"],
        },
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert executed_rules == ["rule_b.cypher"]


@pytest.mark.skipif(
    os.getenv("CODESCOPE_RUN_EXTERNAL_SMOKE") != "1",
    reason="set CODESCOPE_RUN_EXTERNAL_SMOKE=1 to enable live external smoke",
)
def test_scan_job_external_builtin_live_smoke(
    client,
    db_session,
    external_scan_settings,
):
    settings = external_scan_settings["settings"]

    neo4j_uri = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_URI", settings.scan_external_neo4j_uri
    )
    neo4j_user = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_USER", settings.scan_external_neo4j_user
    )
    neo4j_password = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD", settings.scan_external_neo4j_password
    )
    neo4j_database = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE", settings.scan_external_neo4j_database
    )
    if not neo4j_password:
        pytest.skip("missing CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD for live smoke")

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password), connection_timeout=5
        )
        driver.verify_connectivity()
        driver.close()
    except Exception as exc:  # pragma: no cover - optional smoke path
        pytest.skip(f"neo4j unavailable for live smoke: {exc}")

    backend_root = Path(__file__).resolve().parents[1]

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_external_stage_joern_command = ""
    settings.scan_external_stage_import_command = ""
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_source_semantic_command = "builtin:source_semantic"
    settings.scan_external_stage_rules_command = "builtin:rules"
    settings.scan_external_post_labels_cypher = str(
        backend_root / "assets" / "scan" / "query" / "post_labels.cypher"
    )
    settings.scan_external_rules_dir = str(backend_root / "assets" / "scan" / "rules")
    settings.scan_external_neo4j_uri = neo4j_uri
    settings.scan_external_neo4j_user = neo4j_user
    settings.scan_external_neo4j_password = neo4j_password
    settings.scan_external_neo4j_database = neo4j_database

    developer = _create_user(
        db_session,
        email="scan-external-live-smoke@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-live-smoke-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-live-smoke-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-live-smoke\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["result_summary"]["engine_mode"] == "external"


@pytest.mark.skipif(
    os.getenv("CODESCOPE_RUN_EXTERNAL_FULL_SMOKE") != "1",
    reason="set CODESCOPE_RUN_EXTERNAL_FULL_SMOKE=1 to enable live external full smoke",
)
def test_scan_job_external_builtin_live_full_smoke(
    client,
    db_session,
    external_scan_settings,
):
    settings = external_scan_settings["settings"]
    neo4j_uri = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_URI", "bolt://127.0.0.1:7687")
    neo4j_user = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD", "")
    neo4j_database = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE", "neo4j")
    if not neo4j_password:
        pytest.skip(
            "missing CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD for live full smoke"
        )

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password), connection_timeout=5
        )
        driver.verify_connectivity()
        driver.close()
    except Exception as exc:  # pragma: no cover - optional smoke path
        pytest.skip(f"neo4j unavailable for live full smoke: {exc}")

    backend_root = Path(__file__).resolve().parents[1]
    workspace_root = backend_root.parent
    joern_home = workspace_root / "infra" / "tools" / "joern-cli"
    joern_bin = joern_home / "joern"
    export_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    post_labels = backend_root / "assets" / "scan" / "query" / "post_labels.cypher"
    rules_dir = backend_root / "assets" / "scan" / "rules"

    if not joern_bin.exists():
        pytest.skip(f"joern binary missing for full smoke: {joern_bin}")

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_source_semantic_command = "builtin:source_semantic"
    settings.scan_external_stage_rules_command = "builtin:rules"

    settings.scan_external_joern_home = str(joern_home)
    settings.scan_external_joern_bin = str(joern_bin)
    settings.scan_external_joern_export_script = str(export_script)

    settings.scan_external_post_labels_cypher = str(post_labels)
    settings.scan_external_rules_dir = str(rules_dir)
    settings.scan_external_rules_max_count = 1

    settings.scan_external_neo4j_uri = neo4j_uri
    settings.scan_external_neo4j_user = neo4j_user
    settings.scan_external_neo4j_password = neo4j_password
    settings.scan_external_neo4j_database = neo4j_database
    settings.scan_external_neo4j_connect_retry = 30
    settings.scan_external_neo4j_connect_wait_seconds = 1

    settings.scan_external_import_docker_image = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_IMPORT_DOCKER_IMAGE", "neo4j:latest"
    )
    settings.scan_external_import_data_mount = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT", "data"
    )
    settings.scan_external_import_database = neo4j_database
    settings.scan_external_import_clean_db = True
    settings.scan_external_import_preflight = True

    settings.scan_external_neo4j_runtime_restart_mode = "docker"
    settings.scan_external_neo4j_runtime_container_name = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_CONTAINER_NAME",
        "CodeScope_neo4j",
    )
    settings.scan_external_neo4j_runtime_restart_wait_seconds = 8

    developer = _create_user(
        db_session,
        email="scan-external-live-full-smoke@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "scan-external-live-full-smoke-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "scan-external-live-full-smoke-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "external-live-full\n"}
            ),
        },
    )
    version_id = version_resp.json()["data"]["id"]

    source_dir = Path(settings.snapshot_storage_root) / version_id / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SmokeController.java").write_text(
        (
            "public class SmokeController {\n"
            "  public String echo(String input) {\n"
            "    return input;\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    create_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["result_summary"]["engine_mode"] == "external"
    stages = payload["result_summary"].get("external_stages", [])
    assert len(stages) == 5
    assert [item["stage"] for item in stages] == [
        "joern",
        "neo4j_import",
        "post_labels",
        "source_semantic",
        "rules",
    ]


def test_results_overview_and_finding_label_flow(client, db_session):
    developer = _create_user(
        db_session,
        email="result-flow-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "result-flow-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "result-flow-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"README.md": "result-flow\n"}
            ),
        },
    )
    assert version_resp.status_code == 201
    version_id = version_resp.json()["data"]["id"]

    scan_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": project_id, "version_id": version_id},
    )
    assert scan_resp.status_code == 202
    job_id = scan_resp.json()["data"]["job_id"]

    overview_resp = client.get(
        f"/api/v1/projects/{project_id}/results",
        headers=_auth_header(tokens["access_token"]),
        params={"version_id": version_id, "job_id": job_id},
    )
    assert overview_resp.status_code == 200
    overview = overview_resp.json()["data"]
    assert overview["total_findings"] >= 1
    assert "HIGH" in overview["severity_dist"]

    findings_resp = client.get(
        "/api/v1/findings",
        headers=_auth_header(tokens["access_token"]),
        params={"project_id": project_id, "sort_by": "severity", "sort_order": "desc"},
    )
    assert findings_resp.status_code == 200
    finding_id = findings_resp.json()["data"]["items"][0]["id"]

    label_resp = client.post(
        f"/api/v1/findings/{finding_id}/labels",
        headers=_auth_header(tokens["access_token"]),
        json={"status": "TP", "comment": "reviewed"},
    )
    assert label_resp.status_code == 200
    assert label_resp.json()["data"]["finding"]["status"] == "TP"

    labels = db_session.scalars(
        select(FindingLabel).where(FindingLabel.finding_id == uuid.UUID(finding_id))
    ).all()
    assert any(item.status == "TP" for item in labels)

    path_resp = client.get(
        f"/api/v1/findings/{finding_id}/paths",
        headers=_auth_header(tokens["access_token"]),
    )
    assert path_resp.status_code == 409
    assert path_resp.json()["error"]["code"] == "PATH_NOT_AVAILABLE"


def test_scan_results_list_is_project_scoped(client, db_session):
    user = _create_user(
        db_session,
        email="scan-result-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    other = _create_user(
        db_session,
        email="scan-result-other@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    user_tokens = _login(client, email=user.email, password="Password123!")
    other_tokens = _login(client, email=other.email, password="Password123!")

    project = _create_project(db_session, name="scan-result-project")
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project.id,
        role=ProjectRole.OWNER.value,
    )
    version = _create_version(db_session, project_id=project.id, name="scan-result-v1")

    scan_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(user_tokens["access_token"]),
        json={"project_id": str(project.id), "version_id": str(version.id)},
    )
    assert scan_resp.status_code == 202
    scan_job_id = scan_resp.json()["data"]["job_id"]

    other_project = _create_project(db_session, name="scan-result-other-project")
    _add_member(
        db_session,
        user_id=other.id,
        project_id=other_project.id,
        role=ProjectRole.OWNER.value,
    )
    other_version = _create_version(
        db_session, project_id=other_project.id, name="scan-result-other-v1"
    )

    other_scan_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(other_tokens["access_token"]),
        json={"project_id": str(other_project.id), "version_id": str(other_version.id)},
    )
    assert other_scan_resp.status_code == 202

    list_resp = client.get(
        "/api/v1/scan-results",
        headers=_auth_header(user_tokens["access_token"]),
    )
    assert list_resp.status_code == 200, list_resp.text
    payload = list_resp.json()["data"]
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["scan_job_id"] == scan_job_id
    assert row["project_id"] == str(project.id)
    assert row["project_name"] == "scan-result-project"
    assert row["version_id"] == str(version.id)
    assert row["version_name"] == "scan-result-v1"
    assert row["job_status"] == "SUCCEEDED"
    assert isinstance(row["total_findings"], int)
    assert row["ai_enabled"] is False
    assert row["ai_latest_status"] is None


def test_findings_list_rejects_mismatched_project_and_job_scope(client, db_session):
    developer = _create_user(
        db_session,
        email="finding-scope-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_one = _create_project(db_session, name="scope-project-one")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project_one.id,
        role=ProjectRole.OWNER.value,
    )
    _create_version(db_session, project_id=project_one.id, name="scope-v1")

    project_two = _create_project(db_session, name="scope-project-two")
    _add_member(
        db_session,
        user_id=developer.id,
        project_id=project_two.id,
        role=ProjectRole.OWNER.value,
    )
    version_two = _create_version(
        db_session, project_id=project_two.id, name="scope-v2"
    )

    scan_two_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": str(project_two.id), "version_id": str(version_two.id)},
    )
    assert scan_two_resp.status_code == 202
    scan_two_job_id = scan_two_resp.json()["data"]["job_id"]

    findings_resp = client.get(
        "/api/v1/findings",
        headers=_auth_header(tokens["access_token"]),
        params={"project_id": str(project_one.id), "job_id": scan_two_job_id},
    )
    assert findings_resp.status_code == 422, findings_resp.text
    assert findings_resp.json()["error"]["message"] == "job_id 不属于当前项目"


def test_job_logs_download_artifacts_and_version_download(
    client, db_session, tmp_path: Path
):
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    old_log_root = settings.scan_log_root
    old_scan_workspace_root = settings.scan_workspace_root

    settings.snapshot_storage_root = str(tmp_path / "snapshots")
    settings.scan_log_root = str(tmp_path / "job-logs")
    settings.scan_workspace_root = str(tmp_path / "scan-workspaces")

    try:
        developer = _create_user(
            db_session,
            email="artifact-dev@example.com",
            password="Password123!",
            role=SystemRole.USER.value,
        )
        tokens = _login(client, email=developer.email, password="Password123!")

        project_resp = client.post(
            "/api/v1/projects",
            headers=_auth_header(tokens["access_token"]),
            json={"name": "artifact-project"},
        )
        assert project_resp.status_code == 201
        project_id = project_resp.json()["data"]["id"]

        version_resp = client.post(
            f"/api/v1/projects/{project_id}/versions",
            headers=_auth_header(tokens["access_token"]),
            json={
                "name": "artifact-v1",
                "source": "UPLOAD",
                "snapshot_object_key": _seed_snapshot_object_key(
                    {"README.md": "artifact\n"}
                ),
            },
        )
        assert version_resp.status_code == 201
        version_id = version_resp.json()["data"]["id"]

        archive = Path(settings.snapshot_storage_root) / version_id / "snapshot.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"fake-snapshot")

        scan_resp = client.post(
            "/api/v1/scan-jobs",
            headers=_auth_header(tokens["access_token"]),
            json={"project_id": project_id, "version_id": version_id},
        )
        assert scan_resp.status_code == 202
        job_id = scan_resp.json()["data"]["job_id"]

        stage_log_resp = client.get(
            f"/api/v1/jobs/{job_id}/logs/download",
            headers=_auth_header(tokens["access_token"]),
            params={"stage": "Prepare"},
        )
        assert stage_log_resp.status_code == 200
        assert "text/plain" in stage_log_resp.headers.get("content-type", "")

        all_logs_resp = client.get(
            f"/api/v1/jobs/{job_id}/logs/download",
            headers=_auth_header(tokens["access_token"]),
        )
        assert all_logs_resp.status_code == 200
        assert "application/zip" in all_logs_resp.headers.get("content-type", "")

        artifacts_resp = client.get(
            f"/api/v1/jobs/{job_id}/artifacts",
            headers=_auth_header(tokens["access_token"]),
        )
        assert artifacts_resp.status_code == 200
        items = artifacts_resp.json()["data"]["items"]
        assert items

        archive_items = [item for item in items if item["artifact_type"] == "ARCHIVE"]
        assert archive_items

        snapshot_items = [item for item in items if item["artifact_type"] == "SNAPSHOT"]
        assert snapshot_items

        result_archive_resp = client.get(
            f"/api/v1/jobs/{job_id}/artifacts/{archive_items[0]['artifact_id']}/download",
            headers=_auth_header(tokens["access_token"]),
        )
        assert result_archive_resp.status_code == 200
        archive_payload = json.loads(result_archive_resp.text)
        assert archive_payload["job_id"] == job_id
        assert archive_payload["status"] == JobStatus.SUCCEEDED.value
        assert isinstance(archive_payload["result_summary"], dict)

        artifact_download_resp = client.get(
            f"/api/v1/jobs/{job_id}/artifacts/{snapshot_items[0]['artifact_id']}/download",
            headers=_auth_header(tokens["access_token"]),
        )
        assert artifact_download_resp.status_code == 200

        version_download_resp = client.get(
            f"/api/v1/versions/{version_id}/download",
            headers=_auth_header(tokens["access_token"]),
        )
        assert version_download_resp.status_code == 200
        assert "application/gzip" in version_download_resp.headers.get(
            "content-type", ""
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        settings.scan_log_root = old_log_root
        settings.scan_workspace_root = old_scan_workspace_root
