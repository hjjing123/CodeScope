from __future__ import annotations

import json
import os
import subprocess
import tarfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    FindingLabel,
    Job,
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
    assert response.status_code == 200
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
        "scan_external_rules_allowlist_file",
        "scan_external_rules_max_count",
        "scan_external_neo4j_uri",
        "scan_external_neo4j_user",
        "scan_external_neo4j_password",
        "scan_external_neo4j_database",
        "scan_external_neo4j_connect_retry",
        "scan_external_neo4j_connect_wait_seconds",
        "scan_external_import_docker_image",
        "scan_external_import_data_mount",
        "scan_external_import_database",
        "scan_external_import_id_type",
        "scan_external_import_array_delimiter",
        "scan_external_import_clean_db",
        "scan_external_import_multiline_fields",
        "scan_external_import_multiline_fields_format",
        "scan_external_import_preflight",
        "scan_external_neo4j_runtime_restart_mode",
        "scan_external_neo4j_runtime_container_name",
        "scan_external_neo4j_runtime_restart_wait_seconds",
        "scan_external_stage_joern_command",
        "scan_external_stage_import_command",
        "scan_external_stage_post_labels_command",
        "scan_external_stage_rules_command",
        "scan_external_stage_joern_timeout_seconds",
        "scan_external_stage_import_timeout_seconds",
        "scan_external_stage_post_labels_timeout_seconds",
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

    joern_home = tmp_path / "joern-cli"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern.bat"
    joern_bin.write_text("@echo off\n", encoding="utf-8")
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
    settings.scan_external_rules_allowlist_file = ""
    settings.scan_external_rules_max_count = 0
    settings.scan_external_neo4j_uri = "bolt://127.0.0.1:7687"
    settings.scan_external_neo4j_user = "neo4j"
    settings.scan_external_neo4j_password = ""
    settings.scan_external_neo4j_database = "neo4j"
    settings.scan_external_neo4j_connect_retry = 1
    settings.scan_external_neo4j_connect_wait_seconds = 1
    settings.scan_external_import_docker_image = "neo4j:5.26"
    settings.scan_external_import_data_mount = "data"
    settings.scan_external_import_database = "neo4j"
    settings.scan_external_import_id_type = "string"
    settings.scan_external_import_array_delimiter = "\\001"
    settings.scan_external_import_clean_db = False
    settings.scan_external_import_multiline_fields = True
    settings.scan_external_import_multiline_fields_format = ""
    settings.scan_external_import_preflight = False
    settings.scan_external_neo4j_runtime_restart_mode = "none"
    settings.scan_external_neo4j_runtime_container_name = "neo4j"
    settings.scan_external_neo4j_runtime_restart_wait_seconds = 0
    settings.scan_external_stage_joern_command = "stage-joern-{job_id}"
    settings.scan_external_stage_import_command = "stage-import-{job_id}"
    settings.scan_external_stage_post_labels_command = "stage-post-labels-{job_id}"
    settings.scan_external_stage_rules_command = "stage-rules-{job_id}"
    settings.scan_external_stage_joern_timeout_seconds = 30
    settings.scan_external_stage_import_timeout_seconds = 30
    settings.scan_external_stage_post_labels_timeout_seconds = 30
    settings.scan_external_stage_rules_timeout_seconds = 30

    try:
        yield {"settings": settings, "reports_dir": reports_dir}
    finally:
        for key, value in old_values.items():
            setattr(settings, key, value)


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


def test_scan_job_create_and_get_succeeds(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-dev@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
            "scan_mode": "FULL",
            "rule_set_ids": ["any_any_xss.cypher", "any_any_urlredirect.cypher"],
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


def test_scan_job_idempotency_replay(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-idem@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FAST"},
    )
    assert first_resp.status_code == 202
    first_job_id = first_resp.json()["data"]["job_id"]
    assert first_resp.json()["data"]["idempotent_replay"] is False

    second_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FAST"},
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["data"]["idempotent_replay"] is True
    assert second_resp.json()["data"]["job_id"] == first_job_id


def test_scan_job_idempotency_conflict(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-idem-conflict@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FAST"},
    )
    assert first_resp.status_code == 202

    second_resp = client.post(
        "/api/v1/scan-jobs",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
    )
    assert second_resp.status_code == 409
    assert second_resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_scan_job_requires_project_membership(client, db_session):
    owner = _create_user(
        db_session,
        email="scan-owner@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
    )
    outsider = _create_user(
        db_session,
        email="scan-outsider@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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
        role=SystemRole.DEVELOPER.value,
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
        payload={"request_id": "req_cancel", "scan_mode": "FULL", "rule_set_ids": []},
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        created_by=developer.id,
        started_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

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
    assert detail_resp.json()["data"]["status"] == JobStatus.CANCELED.value


def test_scan_job_retry_failed(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-retry@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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


def test_list_jobs_non_admin_is_project_scoped(client, db_session):
    user = _create_user(
        db_session,
        email="scan-scope-user@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        payload={"request_id": "req_scope_a", "scan_mode": "FULL"},
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
        payload={"request_id": "req_scope_b", "scan_mode": "FULL"},
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


def test_scan_job_logs_endpoint_returns_stage_logs(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-logs@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FAST"},
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


def test_findings_list_supports_job_id_filter(client, db_session):
    developer = _create_user(
        db_session,
        email="scan-findings@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
            "scan_mode": "FULL",
            "rule_set_ids": ["any_any_xss.cypher", "any_any_urlredirect.cypher"],
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


def test_scan_job_external_stage_orchestration_succeeds(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    external_scan_settings,
):
    from app.services.scan_external import orchestrator as orchestrator_module

    reports_dir: Path = external_scan_settings["reports_dir"]

    commands: list[str] = []

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

    developer = _create_user(
        db_session,
        email="scan-external-success@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value, payload
    assert payload["result_summary"]["engine_mode"] == "external"
    assert payload["result_summary"]["hit_rules"] == 1
    assert len(payload["result_summary"]["external_stages"]) == 4
    assert all(
        item["status"] == "succeeded"
        for item in payload["result_summary"]["external_stages"]
    )
    assert len(commands) == 4


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
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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
    settings.scan_external_stage_rules_command = "builtin:rules"

    executed: list[str] = []

    def _fake_builtin_stage(
        *, builtin_key, job, settings, context, append_log, timeout_seconds
    ):
        executed.append(str(builtin_key))
        if builtin_key == "rules":
            _write_round_report(context.reports_dir)
        return f"{builtin_key} ok", ""

    monkeypatch.setattr(orchestrator_module, "run_builtin_stage", _fake_builtin_stage)

    developer = _create_user(
        db_session,
        email="scan-external-builtin@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["data"]["job_id"]

    detail_resp = client.get(
        f"/api/v1/jobs/{job_id}", headers=_auth_header(tokens["access_token"])
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert executed == ["joern", "neo4j_import", "post_labels", "rules"]


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
    settings.scan_external_stage_rules_command = "builtin:rules"
    settings.scan_external_rules_allowlist_file = ""

    executed_rules: list[str] = []

    def _fake_execute_cypher_file(**kwargs):
        executed_rules.append(Path(kwargs["cypher_file"]).name)
        return CypherExecutionSummary(statement_count=1, total_rows=1, row_counts=[1])

    monkeypatch.setattr(
        builtin_module, "execute_cypher_file", _fake_execute_cypher_file
    )

    developer = _create_user(
        db_session,
        email="scan-external-rule-filter@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
            "scan_mode": "FULL",
            "rule_set_ids": ["rule_b.cypher"],
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
    reports_dir: Path = external_scan_settings["reports_dir"]

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
    smoke_allowlist = reports_dir.parent / "smoke_allowlist.txt"
    smoke_allowlist.write_text("any_any_xss.cypher\n", encoding="utf-8")

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_external_stage_joern_command = ""
    settings.scan_external_stage_import_command = ""
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_rules_command = "builtin:rules"
    settings.scan_external_post_labels_cypher = str(
        backend_root / "assets" / "scan" / "query" / "post_labels.cypher"
    )
    settings.scan_external_rules_dir = str(backend_root / "assets" / "scan" / "rules")
    settings.scan_external_rules_allowlist_file = str(smoke_allowlist)
    settings.scan_external_neo4j_uri = neo4j_uri
    settings.scan_external_neo4j_user = neo4j_user
    settings.scan_external_neo4j_password = neo4j_password
    settings.scan_external_neo4j_database = neo4j_database

    developer = _create_user(
        db_session,
        email="scan-external-live-smoke@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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
    joern_bin = joern_home / "joern.bat"
    export_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    post_labels = backend_root / "assets" / "scan" / "query" / "post_labels.cypher"
    rules_dir = backend_root / "assets" / "scan" / "rules"

    if not joern_bin.exists():
        pytest.skip(f"joern binary missing for full smoke: {joern_bin}")

    smoke_allowlist = (
        external_scan_settings["reports_dir"].parent / "smoke_full_allowlist.txt"
    )
    smoke_allowlist.write_text("any_any_xss.cypher\n", encoding="utf-8")

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_rules_command = "builtin:rules"

    settings.scan_external_joern_home = str(joern_home)
    settings.scan_external_joern_bin = str(joern_bin)
    settings.scan_external_joern_export_script = str(export_script)

    settings.scan_external_post_labels_cypher = str(post_labels)
    settings.scan_external_rules_dir = str(rules_dir)
    settings.scan_external_rules_allowlist_file = str(smoke_allowlist)
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
        "neo4j",
    )
    settings.scan_external_neo4j_runtime_restart_wait_seconds = 8

    developer = _create_user(
        db_session,
        email="scan-external-live-full-smoke@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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
    assert len(stages) == 4
    assert [item["stage"] for item in stages] == [
        "joern",
        "neo4j_import",
        "post_labels",
        "rules",
    ]


def test_results_overview_and_finding_label_flow(client, db_session):
    developer = _create_user(
        db_session,
        email="result-flow-dev@example.com",
        password="Password123!",
        role=SystemRole.DEVELOPER.value,
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
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
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

    fixed_resp = client.post(
        f"/api/v1/findings/{finding_id}/mark-fixed",
        headers=_auth_header(tokens["access_token"]),
        json={"comment": "fixed manually"},
    )
    assert fixed_resp.status_code == 200
    assert fixed_resp.json()["data"]["finding"]["status"] == "FIXED"

    labels = db_session.scalars(
        select(FindingLabel).where(FindingLabel.finding_id == uuid.UUID(finding_id))
    ).all()
    assert any(item.status == "TP" for item in labels)
    assert any(item.status == "FIXED" for item in labels)

    path_resp = client.get(
        f"/api/v1/findings/{finding_id}/paths",
        headers=_auth_header(tokens["access_token"]),
    )
    assert path_resp.status_code == 409
    assert path_resp.json()["error"]["code"] == "PATH_NOT_AVAILABLE"


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
            role=SystemRole.DEVELOPER.value,
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
            json={
                "project_id": project_id,
                "version_id": version_id,
                "scan_mode": "FULL",
            },
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

        snapshot_items = [item for item in items if item["artifact_type"] == "SNAPSHOT"]
        assert snapshot_items

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
