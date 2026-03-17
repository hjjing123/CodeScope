from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ImportJob, ProjectRole, SystemRole, User
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
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture()
def storage_settings(tmp_path: Path):
    settings = get_settings()
    old_storage_root = settings.storage_root
    old_workspace_root = settings.import_workspace_root
    old_snapshot_root = settings.snapshot_storage_root
    old_import_log_root = settings.import_log_root

    storage_root = tmp_path / "storage"
    settings.storage_root = str(storage_root)
    settings.import_workspace_root = str(storage_root / "workspaces" / "imports")
    settings.snapshot_storage_root = str(storage_root / "snapshots")
    settings.import_log_root = str(storage_root / "import-logs")

    try:
        yield
    finally:
        settings.storage_root = old_storage_root
        settings.import_workspace_root = old_workspace_root
        settings.snapshot_storage_root = old_snapshot_root
        settings.import_log_root = old_import_log_root
        shutil.rmtree(storage_root, ignore_errors=True)


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


def _init_local_git_repo(repo_path: Path) -> None:
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo_path)], check=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.email", "tester@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.name", "Test User"], check=True
    )

    (repo_path / "README.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)


def _add_git_commit(
    repo_path: Path, *, filename: str, content: str, message: str
) -> None:
    (repo_path / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", message], check=True)


def _wait_import_job_terminal(
    client,
    *,
    access_token: str,
    job_id: str,
    timeout_seconds: float = 8.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_response: dict[str, object] | None = None
    while time.time() <= deadline:
        response = client.get(
            f"/api/v1/import-jobs/{job_id}",
            headers=_auth_header(access_token),
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        last_response = payload
        if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELED", "TIMEOUT"}:
            return payload
        time.sleep(0.05)

    assert last_response is not None
    return last_response


def test_project_and_version_flow(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="proj-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    admin = _create_user(
        db_session,
        email="proj-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )

    dev_tokens = _login(client, email=developer.email, password="Password123!")
    create_project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(dev_tokens["access_token"]),
        json={"name": "demo-project", "description": "demo"},
    )
    assert create_project_resp.status_code == 201
    project_id = create_project_resp.json()["data"]["id"]
    assert "baseline_version_id" not in create_project_resp.json()["data"]
    assert (
        create_project_resp.json()["data"]["my_project_role"] == ProjectRole.OWNER.value
    )

    snapshot_object_key = _seed_snapshot_object_key({"README.md": "demo\n"})
    create_version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(dev_tokens["access_token"]),
        json={
            "name": "manual-v1",
            "source": "UPLOAD",
            "snapshot_object_key": snapshot_object_key,
        },
    )
    assert create_version_resp.status_code == 201
    version_id = create_version_resp.json()["data"]["id"]
    assert "baseline_of_version_id" not in create_version_resp.json()["data"]
    assert "is_baseline" not in create_version_resp.json()["data"]

    project_after_version_resp = client.get(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(dev_tokens["access_token"]),
    )
    assert project_after_version_resp.status_code == 200
    assert project_after_version_resp.json()["data"]["status"] == "SCANNABLE"

    list_versions_resp = client.get(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(dev_tokens["access_token"]),
    )
    assert list_versions_resp.status_code == 200
    assert "baseline_version_id" not in list_versions_resp.json()["data"]
    assert "is_baseline" not in list_versions_resp.json()["data"]["items"][0]

    admin_tokens = _login(client, email=admin.email, password="Password123!")
    archive_resp = client.post(
        f"/api/v1/versions/{version_id}/archive",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["archived"] is True

    project_after_archive_resp = client.get(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert project_after_archive_resp.status_code == 200
    assert project_after_archive_resp.json()["data"]["status"] == "IMPORTED"

    delete_resp = client.delete(
        f"/api/v1/versions/{version_id}",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    project_after_delete_resp = client.get(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert project_after_delete_resp.status_code == 200
    assert project_after_delete_resp.json()["data"]["status"] == "NEW"


def test_upload_import_success_and_code_browse(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="upload-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "upload-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    zip_payload = _create_zip_payload({"src/app.py": "print('hello')\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(tokens["access_token"]),
        params={"version_name": "upload-v1", "note": "first import"},
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert import_resp.status_code == 202
    import_job_id = import_resp.json()["data"]["import_job_id"]

    job_payload = _wait_import_job_terminal(
        client,
        access_token=tokens["access_token"],
        job_id=import_job_id,
    )
    assert job_payload["status"] == "SUCCEEDED"
    version_id = job_payload["version_id"]
    assert version_id is not None

    logs_resp = client.get(
        f"/api/v1/import-jobs/{import_job_id}/logs",
        headers=_auth_header(tokens["access_token"]),
    )
    assert logs_resp.status_code == 200
    assert any(
        item["stage"] == "Validate" for item in logs_resp.json()["data"]["items"]
    )

    stage_download_resp = client.get(
        f"/api/v1/import-jobs/{import_job_id}/logs/download",
        headers=_auth_header(tokens["access_token"]),
        params={"stage": "Validate"},
    )
    assert stage_download_resp.status_code == 200
    assert "text/plain" in stage_download_resp.headers.get("content-type", "")

    all_logs_download_resp = client.get(
        f"/api/v1/import-jobs/{import_job_id}/logs/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert all_logs_download_resp.status_code == 200
    assert "application/zip" in all_logs_download_resp.headers.get("content-type", "")

    tree_resp = client.get(
        f"/api/v1/versions/{version_id}/tree",
        headers=_auth_header(tokens["access_token"]),
    )
    assert tree_resp.status_code == 200
    tree_items = tree_resp.json()["data"]["items"]
    assert any(
        item["name"] == "app.py" and item["node_type"] == "file" for item in tree_items
    )
    file_path = next(
        item["path"]
        for item in tree_items
        if item["node_type"] == "file" and item["name"] == "app.py"
    )

    file_resp = client.get(
        f"/api/v1/versions/{version_id}/file",
        headers=_auth_header(tokens["access_token"]),
        params={"path": file_path},
    )
    assert file_resp.status_code == 200
    assert "print('hello')" in file_resp.json()["data"]["content"]


def test_version_file_supports_full_content_preview(
    client, db_session, storage_settings
):
    developer = _create_user(
        db_session,
        email="version-file-full@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "version-file-full-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    long_content = "\n".join(f"line-{index}" for index in range(1, 41)) + "\n"
    version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "version-file-full-v1",
            "source": "UPLOAD",
            "snapshot_object_key": _seed_snapshot_object_key(
                {"src/Main.java": long_content}
            ),
        },
    )
    assert version_resp.status_code == 201
    version_id = version_resp.json()["data"]["id"]

    file_resp = client.get(
        f"/api/v1/versions/{version_id}/file",
        headers=_auth_header(tokens["access_token"]),
        params={"path": "src/Main.java", "full": True},
    )
    assert file_resp.status_code == 200
    payload = file_resp.json()["data"]
    assert payload["truncated"] is False
    assert payload["total_lines"] == 40
    assert "line-40" in payload["content"]


def test_upload_zip_slip_marks_import_job_failed(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="zip-slip-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "zip-slip-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    zip_payload = _create_zip_payload({"../evil.py": "print('x')\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(tokens["access_token"]),
        files={"file": ("bad.zip", zip_payload, "application/zip")},
    )
    assert import_resp.status_code == 202
    import_job_id = import_resp.json()["data"]["import_job_id"]

    job_payload = _wait_import_job_terminal(
        client,
        access_token=tokens["access_token"],
        job_id=import_job_id,
    )
    assert job_payload["status"] == "FAILED"
    assert job_payload["failure_code"] == "ZIP_SLIP_DETECTED"
    assert "非法路径" in job_payload["failure_hint"]


def test_git_import_and_sync(client, db_session, storage_settings, tmp_path: Path):
    developer = _create_user(
        db_session,
        email="git-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "git-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    repo_path = tmp_path / "repo"
    _init_local_git_repo(repo_path)

    git_test_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/git/test",
        headers=_auth_header(tokens["access_token"]),
        json={"repo_url": str(repo_path), "ref_type": "branch", "ref_value": "HEAD"},
    )
    assert git_test_resp.status_code == 200
    assert git_test_resp.json()["data"]["ok"] is True

    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/git",
        headers=_auth_header(tokens["access_token"]),
        json={
            "repo_url": str(repo_path),
            "ref_type": "branch",
            "ref_value": "HEAD",
            "version_name": "git-v1",
        },
    )
    assert import_resp.status_code == 202
    import_job_id = import_resp.json()["data"]["import_job_id"]

    first_job_payload = _wait_import_job_terminal(
        client,
        access_token=tokens["access_token"],
        job_id=import_job_id,
    )
    assert first_job_payload["status"] == "SUCCEEDED"
    first_version_id = first_job_payload["version_id"]

    _add_git_commit(
        repo_path, filename="README.md", content="# demo\nnew\n", message="update"
    )

    sync_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/git/sync",
        headers=_auth_header(tokens["access_token"]),
    )
    assert sync_resp.status_code == 202
    sync_job_id = sync_resp.json()["data"]["import_job_id"]

    sync_job_payload = _wait_import_job_terminal(
        client,
        access_token=tokens["access_token"],
        job_id=sync_job_id,
    )
    assert sync_job_payload["status"] == "SUCCEEDED"
    second_version_id = sync_job_payload["version_id"]

    assert first_version_id != second_version_id

    versions_resp = client.get(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
    )
    assert versions_resp.status_code == 200
    assert versions_resp.json()["data"]["total"] >= 2


def test_import_job_requires_project_membership(client, db_session, storage_settings):
    owner = _create_user(
        db_session,
        email="import-owner@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    outsider = _create_user(
        db_session,
        email="import-outsider@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    owner_tokens = _login(client, email=owner.email, password="Password123!")
    outsider_tokens = _login(client, email=outsider.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"name": "member-check-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    zip_payload = _create_zip_payload({"README.md": "hello\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(owner_tokens["access_token"]),
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    import_job_id = import_resp.json()["data"]["import_job_id"]

    denied_resp = client.get(
        f"/api/v1/import-jobs/{import_job_id}",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert denied_resp.status_code == 403
    assert denied_resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"

    denied_logs_resp = client.get(
        f"/api/v1/import-jobs/{import_job_id}/logs",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert denied_logs_resp.status_code == 403
    assert denied_logs_resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"


def test_upload_import_idempotency_replay(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="idem-upload@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "idem-upload-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    key = "idem-upload-001"
    zip_payload = _create_zip_payload({"README.md": "hello\n"})
    first_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        params={"version_name": "idem-v1"},
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert first_resp.status_code == 202
    first_job_id = first_resp.json()["data"]["import_job_id"]
    assert first_resp.json()["data"]["idempotent_replay"] is False

    second_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        params={"version_name": "idem-v1"},
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["data"]["idempotent_replay"] is True
    assert second_resp.json()["data"]["import_job_id"] == first_job_id


def test_upload_import_idempotency_conflict(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="idem-conflict@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "idem-conflict-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    key = "idem-upload-002"
    zip_payload = _create_zip_payload({"README.md": "hello\n"})
    first_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        params={"version_name": "idem-v1"},
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert first_resp.status_code == 202

    second_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers={**_auth_header(tokens["access_token"]), "Idempotency-Key": key},
        params={"version_name": "idem-v2"},
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert second_resp.status_code == 409
    assert second_resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_deleted_project_blocks_import_and_new_version(client, db_session):
    developer = _create_user(
        db_session,
        email="deleted-block@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "deleted-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    delete_project_resp = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert delete_project_resp.status_code == 200
    assert delete_project_resp.json()["data"]["deleted"] is True

    zip_payload = _create_zip_payload({"README.md": "hello\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(tokens["access_token"]),
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert import_resp.status_code == 404
    assert import_resp.json()["error"]["code"] == "NOT_FOUND"

    create_version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "manual-v1",
            "source": "UPLOAD",
            "snapshot_object_key": "snapshots/00000000-0000-0000-0000-000000000000/snapshot.tar.gz",
        },
    )
    assert create_version_resp.status_code == 404
    assert create_version_resp.json()["error"]["code"] == "NOT_FOUND"


def test_deleted_version_is_not_accessible(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="deleted-version@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    admin = _create_user(
        db_session,
        email="deleted-version-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")
    admin_tokens = _login(client, email=admin.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "deleted-version-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    snapshot_object_key = _seed_snapshot_object_key({"README.md": "hello\n"})
    create_version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "to-delete-v1",
            "source": "UPLOAD",
            "snapshot_object_key": snapshot_object_key,
        },
    )
    assert create_version_resp.status_code == 201
    version_id = create_version_resp.json()["data"]["id"]

    delete_resp = client.delete(
        f"/api/v1/versions/{version_id}",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    get_resp = client.get(
        f"/api/v1/versions/{version_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["code"] == "NOT_FOUND"

    archive_resp = client.post(
        f"/api/v1/versions/{version_id}/archive",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert archive_resp.status_code == 404
    assert archive_resp.json()["error"]["code"] == "NOT_FOUND"

    tree_resp = client.get(
        f"/api/v1/versions/{version_id}/tree",
        headers=_auth_header(tokens["access_token"]),
    )
    assert tree_resp.status_code == 404
    assert tree_resp.json()["error"]["code"] == "NOT_FOUND"

    file_resp = client.get(
        f"/api/v1/versions/{version_id}/file",
        headers=_auth_header(tokens["access_token"]),
        params={"path": "README.md"},
    )
    assert file_resp.status_code == 404
    assert file_resp.json()["error"]["code"] == "NOT_FOUND"

    download_resp = client.get(
        f"/api/v1/versions/{version_id}/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert download_resp.status_code == 404
    assert download_resp.json()["error"]["code"] == "NOT_FOUND"


def test_version_snapshot_path_traversal_rejected(client, db_session, storage_settings):
    developer = _create_user(
        db_session,
        email="path-traversal@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "path-traversal-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    snapshot_object_key = _seed_snapshot_object_key({"README.md": "hello\n"})
    create_version_resp = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers=_auth_header(tokens["access_token"]),
        json={
            "name": "path-traversal-v1",
            "source": "UPLOAD",
            "snapshot_object_key": snapshot_object_key,
        },
    )
    assert create_version_resp.status_code == 201
    version_id = create_version_resp.json()["data"]["id"]

    for tree_path in ["../", "..\\..\\", "/etc", "C:/Windows"]:
        tree_resp = client.get(
            f"/api/v1/versions/{version_id}/tree",
            headers=_auth_header(tokens["access_token"]),
            params={"path": tree_path},
        )
        assert tree_resp.status_code == 422
        assert tree_resp.json()["error"]["code"] == "INVALID_ARGUMENT"

    for file_path in [
        "../README.md",
        "..\\README.md",
        "/etc/passwd",
        "C:/Windows/win.ini",
    ]:
        file_resp = client.get(
            f"/api/v1/versions/{version_id}/file",
            headers=_auth_header(tokens["access_token"]),
            params={"path": file_path},
        )
        assert file_resp.status_code == 422
        assert file_resp.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_update_project_rejects_unknown_status_field(client, db_session):
    developer = _create_user(
        db_session,
        email="project-update-contract@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "update-contract-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    update_resp = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(tokens["access_token"]),
        json={"status": "DELETED"},
    )
    assert update_resp.status_code == 422
    assert update_resp.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_import_dispatch_failure_returns_structured_error(
    client, db_session, storage_settings, monkeypatch
):
    from app.worker import tasks as worker_tasks

    def _raise_enqueue(*, import_job_id, db_bind=None):
        _ = (import_job_id, db_bind)
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(worker_tasks, "enqueue_import_job", _raise_enqueue)

    developer = _create_user(
        db_session,
        email="dispatch-fail@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "dispatch-fail-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    zip_payload = _create_zip_payload({"README.md": "hello\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(tokens["access_token"]),
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert import_resp.status_code == 503
    assert import_resp.json()["error"]["code"] == "IMPORT_DISPATCH_FAILED"

    import_jobs = db_session.scalars(
        select(ImportJob).where(ImportJob.project_id == uuid.UUID(project_id))
    ).all()
    assert len(import_jobs) == 1
    assert import_jobs[0].status == "FAILED"
    assert import_jobs[0].failure_code == "IMPORT_DISPATCH_FAILED"

    workspace_dir = Path(get_settings().import_workspace_root) / str(import_jobs[0].id)
    assert not workspace_dir.exists()


def test_delete_project_cleans_snapshot_and_import_artifacts(
    client, db_session, storage_settings
):
    developer = _create_user(
        db_session,
        email="delete-cleanup@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "delete-cleanup-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    zip_payload = _create_zip_payload({"src/app.py": "print('hello')\n"})
    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/upload",
        headers=_auth_header(tokens["access_token"]),
        files={"file": ("source.zip", zip_payload, "application/zip")},
    )
    assert import_resp.status_code == 202
    import_job_id = import_resp.json()["data"]["import_job_id"]

    job_payload = _wait_import_job_terminal(
        client,
        access_token=tokens["access_token"],
        job_id=import_job_id,
    )
    assert job_payload["status"] == "SUCCEEDED"
    version_id = job_payload["version_id"]
    assert version_id is not None

    import_workspace_dir = Path(get_settings().import_workspace_root) / import_job_id
    import_workspace_dir.mkdir(parents=True, exist_ok=True)
    (import_workspace_dir / "leftover.tmp").write_text("x", encoding="utf-8")

    snapshot_dir = Path(get_settings().snapshot_storage_root) / version_id
    assert snapshot_dir.exists()
    import_log_dir = Path(get_settings().import_log_root) / import_job_id
    assert import_log_dir.exists()

    delete_resp = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    assert not snapshot_dir.exists()
    assert not import_log_dir.exists()
    assert not import_workspace_dir.exists()


def test_git_credential_placeholder_returns_not_configured(
    client, db_session, storage_settings, tmp_path: Path
):
    developer = _create_user(
        db_session,
        email="credential-placeholder@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(tokens["access_token"]),
        json={"name": "credential-project"},
    )
    project_id = project_resp.json()["data"]["id"]

    repo_path = tmp_path / "credential-repo"
    _init_local_git_repo(repo_path)

    test_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/git/test",
        headers=_auth_header(tokens["access_token"]),
        json={
            "repo_url": str(repo_path),
            "ref_type": "branch",
            "ref_value": "HEAD",
            "credential_id": "cred-1",
        },
    )
    assert test_resp.status_code == 501
    assert test_resp.json()["error"]["code"] == "CREDENTIAL_PROVIDER_NOT_CONFIGURED"

    import_resp = client.post(
        f"/api/v1/projects/{project_id}/imports/git",
        headers=_auth_header(tokens["access_token"]),
        json={
            "repo_url": str(repo_path),
            "ref_type": "branch",
            "ref_value": "HEAD",
            "credential_id": "cred-1",
        },
    )
    assert import_resp.status_code == 501
    assert import_resp.json()["error"]["code"] == "CREDENTIAL_PROVIDER_NOT_CONFIGURED"
