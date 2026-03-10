from __future__ import annotations

import io
import shutil
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import SystemRole, User
from app.security.password import hash_password


pytestmark = pytest.mark.usefixtures("rule_file_settings")


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


def _create_rule(client, access_token: str, *, rule_key: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/rules",
        headers=_auth_header(access_token),
        json={
            "rule_key": rule_key,
            "name": f"{rule_key}-name",
            "vuln_type": "XSS",
            "default_severity": "HIGH",
            "language_scope": "java",
            "description": "demo rule",
            "content": {
                "query": "MATCH (n) RETURN n LIMIT 1",
                "timeout_ms": 5000,
            },
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def _publish_rule(client, access_token: str, *, rule_key: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/rules/{rule_key}/publish",
        headers=_auth_header(access_token),
    )
    assert response.status_code == 200
    return response.json()["data"]


def _wait_selftest_terminal(
    client, access_token: str, *, selftest_job_id: str, timeout_seconds: float = 8.0
):
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() <= deadline:
        response = client.get(
            f"/api/v1/rules/selftest/{selftest_job_id}",
            headers=_auth_header(access_token),
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        last_payload = payload
        if payload["status"] in {"SUCCEEDED", "FAILED", "TIMEOUT", "CANCELED"}:
            return payload
        time.sleep(0.05)

    assert last_payload is not None
    return last_payload


def _create_zip_payload(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buf.getvalue()


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
def selftest_log_settings(tmp_path):
    settings = get_settings()
    old_selftest_log_root = settings.selftest_log_root
    selftest_log_root = tmp_path / "selftest-logs"
    settings.selftest_log_root = str(selftest_log_root)
    try:
        yield
    finally:
        settings.selftest_log_root = old_selftest_log_root
        shutil.rmtree(selftest_log_root, ignore_errors=True)


@pytest.fixture()
def rule_file_settings(tmp_path):
    settings = get_settings()
    old_rules_dir = settings.scan_external_rules_dir
    old_rule_sets_dir = settings.scan_external_rule_sets_dir
    rules_dir = tmp_path / "rules"
    rule_sets_dir = tmp_path / "rule-sets"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_sets_dir.mkdir(parents=True, exist_ok=True)
    settings.scan_external_rules_dir = str(rules_dir)
    settings.scan_external_rule_sets_dir = str(rule_sets_dir)
    try:
        yield
    finally:
        settings.scan_external_rules_dir = old_rules_dir
        settings.scan_external_rule_sets_dir = old_rule_sets_dir
        shutil.rmtree(rules_dir, ignore_errors=True)
        shutil.rmtree(rule_sets_dir, ignore_errors=True)


def test_rule_lifecycle_create_draft_publish_and_rollback(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    created = _create_rule(client, tokens["access_token"], rule_key="demo.rule.xss")
    assert created["rule_key"] == "demo.rule.xss"
    assert created["active_version"] is None

    versions_resp = client.get(
        "/api/v1/rules/demo.rule.xss/versions",
        headers=_auth_header(tokens["access_token"]),
    )
    assert versions_resp.status_code == 200
    assert versions_resp.json()["data"]["total"] == 1
    assert versions_resp.json()["data"]["items"][0]["status"] == "DRAFT"
    assert versions_resp.json()["data"]["items"][0]["version"] == 1

    publish_v1 = _publish_rule(client, tokens["access_token"], rule_key="demo.rule.xss")
    assert publish_v1["rule"]["active_version"] == 1

    patch_resp = client.patch(
        "/api/v1/rules/demo.rule.xss/draft",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "demo-rule-xss-v2",
            "content": {
                "query": "MATCH (n) RETURN n LIMIT 2",
                "timeout_ms": 8000,
            },
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["draft_version"]["version"] == 2

    publish_v2 = _publish_rule(client, tokens["access_token"], rule_key="demo.rule.xss")
    assert publish_v2["rule"]["active_version"] == 2

    rollback_resp = client.post(
        "/api/v1/rules/demo.rule.xss/rollback",
        headers=_auth_header(tokens["access_token"]),
        json={"version": 1},
    )
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["data"]["active_version"] == 1

    toggle_resp = client.post(
        "/api/v1/rules/demo.rule.xss/toggle",
        headers=_auth_header(tokens["access_token"]),
        json={"enabled": False},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["data"]["enabled"] is False

    list_resp = client.get(
        "/api/v1/rules",
        headers=_auth_header(tokens["access_token"]),
        params={"enabled": False},
    )
    assert list_resp.status_code == 200
    assert any(
        item["rule_key"] == "demo.rule.xss"
        for item in list_resp.json()["data"]["items"]
    )


def test_rule_list_supports_keyword_search(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-search-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.search.alpha")
    _create_rule(client, tokens["access_token"], rule_key="demo.search.beta")

    list_resp = client.get(
        "/api/v1/rules",
        headers=_auth_header(tokens["access_token"]),
        params={"search": "alpha"},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 1
    assert list_resp.json()["data"]["items"][0]["rule_key"] == "demo.search.alpha"


def test_rule_write_requires_admin_scope(client, db_session):
    user = _create_user(
        db_session,
        email="rule-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=user.email, password="Password123!")

    denied_resp = client.post(
        "/api/v1/rules",
        headers=_auth_header(tokens["access_token"]),
        json={
            "rule_key": "dev.rule.create",
            "name": "dev rule",
            "vuln_type": "XSS",
            "default_severity": "MED",
            "language_scope": "java",
            "content": {"query": "MATCH (n) RETURN n LIMIT 1"},
        },
    )
    assert denied_resp.status_code == 403


def test_rule_list_ignores_empty_version_directories(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-empty-version-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    rules_dir = Path(get_settings().scan_external_rules_dir)
    orphan_dir = rules_dir / ".versions" / "orphan.rule"
    orphan_dir.mkdir(parents=True, exist_ok=True)

    list_resp = client.get(
        "/api/v1/rules",
        headers=_auth_header(tokens["access_token"]),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 0

    detail_resp = client.get(
        "/api/v1/rules/orphan.rule",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_resp.status_code == 404
    assert detail_resp.json()["error"]["code"] == "NOT_FOUND"


def test_rule_set_create_and_bind_published_rules(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-set-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.ruleset.one")
    _publish_rule(client, tokens["access_token"], rule_key="demo.ruleset.one")
    _create_rule(client, tokens["access_token"], rule_key="demo.ruleset.two")
    _publish_rule(client, tokens["access_token"], rule_key="demo.ruleset.two")

    create_set_resp = client.post(
        "/api/v1/rule-sets",
        headers=_auth_header(tokens["access_token"]),
        json={
            "key": "default-java-rules",
            "name": "default-java-rules",
            "description": "default set",
        },
    )
    assert create_set_resp.status_code == 201
    rule_set_id = create_set_resp.json()["data"]["id"]
    assert create_set_resp.json()["data"]["key"] == "default-java-rules"

    bind_resp = client.post(
        f"/api/v1/rule-sets/{rule_set_id}/rules",
        headers=_auth_header(tokens["access_token"]),
        json={"rule_keys": ["demo.ruleset.one", "demo.ruleset.two"]},
    )
    assert bind_resp.status_code == 200
    assert len(bind_resp.json()["data"]["items"]) == 2

    detail_resp = client.get(
        f"/api/v1/rule-sets/{rule_set_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["key"] == "default-java-rules"
    assert len(detail_resp.json()["data"]["items"]) == 2

    list_resp = client.get(
        "/api/v1/rule-sets", headers=_auth_header(tokens["access_token"])
    )
    assert list_resp.status_code == 200
    target = next(
        item for item in list_resp.json()["data"]["items"] if item["id"] == rule_set_id
    )
    assert target["rule_count"] == 2


def test_rule_publish_requires_valid_query_content(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-validate-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    create_resp = client.post(
        "/api/v1/rules",
        headers=_auth_header(tokens["access_token"]),
        json={
            "rule_key": "demo.rule.invalid.content",
            "name": "invalid-content-rule",
            "vuln_type": "XSS",
            "default_severity": "MED",
            "language_scope": "java",
            "description": "missing timeout",
            "content": {"query": "MATCH (n) RETURN n LIMIT 1"},
        },
    )
    assert create_resp.status_code == 201

    publish_resp = client.post(
        "/api/v1/rules/demo.rule.invalid.content/publish",
        headers=_auth_header(tokens["access_token"]),
    )
    assert publish_resp.status_code == 422
    assert publish_resp.json()["error"]["code"] == "RULE_VALIDATION_FAILED"


def test_rule_set_bind_rejects_unknown_rule(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-dup-bind-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.bind.known.rule")
    _publish_rule(client, tokens["access_token"], rule_key="demo.bind.known.rule")

    create_set_resp = client.post(
        "/api/v1/rule-sets",
        headers=_auth_header(tokens["access_token"]),
        json={
            "key": "dup-bind-rules",
            "name": "dup-bind-rules",
            "description": "dup bind",
        },
    )
    assert create_set_resp.status_code == 201
    rule_set_id = create_set_resp.json()["data"]["id"]

    bind_resp = client.post(
        f"/api/v1/rule-sets/{rule_set_id}/rules",
        headers=_auth_header(tokens["access_token"]),
        json={"rule_keys": ["demo.bind.known.rule", "demo.bind.missing.rule"]},
    )
    assert bind_resp.status_code == 422
    assert bind_resp.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_rule_selftest_job_async_with_version_target(
    client, db_session, selftest_log_settings
):
    admin = _create_user(
        db_session,
        email="rule-selftest-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.selftest.rule")
    _publish_rule(client, tokens["access_token"], rule_key="demo.selftest.rule")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "rule-selftest-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    snapshot_object_key = _seed_snapshot_object_key({"README.md": "selftest\n"})
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "rule-selftest-v1",
            "source": "UPLOAD",
            "snapshot_object_key": snapshot_object_key,
        },
    )
    assert version_resp.status_code == 201
    version_id = version_resp.json()["data"]["id"]

    create_resp = client.post(
        "/api/v1/rules/selftest",
        headers=_auth_header(tokens["access_token"]),
        json={"rule_key": "demo.selftest.rule", "version_id": version_id},
    )
    assert create_resp.status_code == 202
    selftest_job_id = create_resp.json()["data"]["selftest_job_id"]

    payload = _wait_selftest_terminal(
        client, tokens["access_token"], selftest_job_id=selftest_job_id
    )
    assert payload["status"] == "SUCCEEDED"
    assert payload["result_summary"]["rule_key"] == "demo.selftest.rule"

    logs_resp = client.get(
        f"/api/v1/rules/selftest/{selftest_job_id}/logs",
        headers=_auth_header(tokens["access_token"]),
    )
    assert logs_resp.status_code == 200
    assert any(item["stage"] == "Prepare" for item in logs_resp.json()["data"]["items"])

    stage_download_resp = client.get(
        f"/api/v1/rules/selftest/{selftest_job_id}/logs/download",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": "Prepare"},
    )
    assert stage_download_resp.status_code == 200
    assert "text/plain" in stage_download_resp.headers.get("content-type", "")

    all_logs_download_resp = client.get(
        f"/api/v1/rules/selftest/{selftest_job_id}/logs/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert all_logs_download_resp.status_code == 200
    assert "application/zip" in all_logs_download_resp.headers.get("content-type", "")


def test_rule_selftest_job_async_with_upload_target(
    client, db_session, selftest_log_settings
):
    admin = _create_user(
        db_session,
        email="rule-selftest-upload-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.selftest.upload.rule")
    _publish_rule(client, tokens["access_token"], rule_key="demo.selftest.upload.rule")

    zip_payload = _create_zip_payload({"src/App.java": "class App {}\n"})
    create_resp = client.post(
        "/api/v1/rules/selftest/upload",
        headers=_auth_header(tokens["access_token"]),
        files={"file": ("target.zip", zip_payload, "application/zip")},
        data={"rule_key": "demo.selftest.upload.rule"},
    )
    assert create_resp.status_code == 202
    selftest_job_id = create_resp.json()["data"]["selftest_job_id"]

    payload = _wait_selftest_terminal(
        client, tokens["access_token"], selftest_job_id=selftest_job_id
    )
    assert payload["status"] == "SUCCEEDED"
    assert payload["result_summary"]["target"]["target_type"] == "UPLOAD"


def test_rule_stats_are_aggregated_async_after_scan(client, db_session):
    admin = _create_user(
        db_session,
        email="rule-stats-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    _create_rule(client, tokens["access_token"], rule_key="demo.stats.rule")
    _publish_rule(client, tokens["access_token"], rule_key="demo.stats.rule")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "rule-stats-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    snapshot_object_key = _seed_snapshot_object_key({"README.md": "stats\n"})
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "rule-stats-v1",
            "source": "UPLOAD",
            "snapshot_object_key": snapshot_object_key,
        },
    )
    assert version_resp.status_code == 201
    version_id = version_resp.json()["data"]["id"]

    scan_resp = client.post(
        "/api/v1/scan-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "project_id": project_id,
            "version_id": version_id,
            "rule_keys": ["demo.stats.rule"],
        },
    )
    assert scan_resp.status_code == 202

    deadline = time.time() + 8.0
    latest_items = []
    while time.time() <= deadline:
        stats_resp = client.get(
            "/api/v1/rule-stats",
            headers=_auth_header(tokens["access_token"]),
            params={"rule_key": "demo.stats.rule"},
        )
        assert stats_resp.status_code == 200
        latest_items = stats_resp.json()["data"]["items"]
        if latest_items:
            break
        time.sleep(0.05)

    assert latest_items, "expected aggregated rule stats for demo.stats.rule"
    assert latest_items[0]["rule_key"] == "demo.stats.rule"
    assert latest_items[0]["hits"] >= 1
