from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    Finding,
    FindingSeverity,
    FindingStatus,
    Job,
    JobStatus,
    JobType,
    Project,
    ProjectRole,
    Report,
    SystemRole,
    User,
    UserProjectRole,
    Version,
    VersionSource,
)
from app.security.password import hash_password


@pytest.fixture()
def report_storage_settings(tmp_path: Path):
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    old_report_storage_root = settings.report_storage_root
    old_report_log_root = settings.report_log_root
    settings.snapshot_storage_root = str(tmp_path / "snapshots")
    settings.report_storage_root = str(tmp_path / "reports")
    settings.report_log_root = str(tmp_path / "report-logs")
    try:
        yield settings
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        settings.report_storage_root = old_report_storage_root
        settings.report_log_root = old_report_log_root


def _create_user(db, *, email: str, password: str, role: str) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=email.split("@", 1)[0],
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_project(db, *, name: str) -> Project:
    project = Project(name=name, description=f"{name} project")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _create_version(db, *, project_id: uuid.UUID, name: str = "v1") -> Version:
    version = Version(
        project_id=project_id, name=name, source=VersionSource.UPLOAD.value
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def _create_scan_job(
    db,
    *,
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    created_by: uuid.UUID,
    status: str = JobStatus.SUCCEEDED.value,
) -> Job:
    job = Job(
        project_id=project_id,
        version_id=version_id,
        job_type=JobType.SCAN.value,
        status=status,
        stage="Cleanup",
        payload={"request_id": "req-report-test"},
        created_by=created_by,
        result_summary={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _create_finding(
    db,
    *,
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    rule_key: str,
    vuln_type: str,
    suffix: str,
    line_start: int,
) -> Finding:
    file_path = f"src/main/java/com/demo/{suffix}Controller.java"
    finding = Finding(
        project_id=project_id,
        version_id=version_id,
        job_id=job_id,
        rule_key=rule_key,
        vuln_type=vuln_type,
        severity=FindingSeverity.HIGH.value,
        status=FindingStatus.OPEN.value,
        file_path=file_path,
        line_start=line_start,
        line_end=line_start,
        has_path=True,
        path_length=2,
        source_file=file_path,
        source_line=line_start,
        sink_file=file_path,
        sink_line=line_start + 1,
        evidence_json={"source": "unit-test", "suffix": suffix},
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def _add_member(
    db, *, user_id: uuid.UUID, project_id: uuid.UUID, project_role: str
) -> None:
    db.add(
        UserProjectRole(
            user_id=user_id,
            project_id=project_id,
            project_role=project_role,
        )
    )
    db.commit()


def _login(client, *, email: str, password: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _write_snapshot_source(
    version_id: uuid.UUID, *, relative_path: str, content: str
) -> None:
    root = Path(get_settings().snapshot_storage_root) / str(version_id) / "source"
    target = root / Path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_create_finding_report_preview_and_download_single_file(
    client, db_session, report_storage_settings
):
    user = _create_user(
        db_session,
        email="report-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="report-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=user.id,
    )
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="User",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/UserController.java",
        content=(
            "package com.demo;\n\n"
            "import org.springframework.web.bind.annotation.GetMapping;\n\n"
            "public class UserController {\n"
            '  @GetMapping("/users")\n'
            "  public String listUsers(String orderBy) {\n"
            '    String sql = "select * from users order by " + orderBy;\n'
            "    return sql;\n"
            "  }\n"
            "}\n"
        ),
    )

    tokens = _login(client, email=user.email, password="Password123!")
    response = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "report_type": "FINDING",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_id": str(finding.id),
            "options": {
                "format": "MARKDOWN",
                "include_code_snippets": True,
                "include_ai_sections": False,
            },
        },
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    assert payload["report_type"] == "FINDING"
    assert payload["finding_count"] == 1

    report_job_id = payload["report_job_id"]
    job_resp = client.get(
        f"/api/v1/jobs/{report_job_id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert job_resp.status_code == 200
    assert job_resp.json()["data"]["job_type"] == JobType.REPORT.value
    assert job_resp.json()["data"]["status"] == JobStatus.SUCCEEDED.value

    reports_resp = client.get(
        "/api/v1/reports",
        headers=_auth_header(tokens["access_token"]),
        params={"report_job_id": report_job_id},
    )
    assert reports_resp.status_code == 200
    reports_payload = reports_resp.json()["data"]
    assert reports_payload["total"] == 1
    report_item = reports_payload["items"][0]
    report_id = report_item["id"]
    assert report_item["report_type"] == "FINDING"
    assert "SQL Injection" in report_item["title"]

    content_resp = client.get(
        f"/api/v1/reports/{report_id}/content",
        headers=_auth_header(tokens["access_token"]),
    )
    assert content_resp.status_code == 200
    content_payload = content_resp.json()["data"]
    assert content_payload["report"]["title"] == report_item["title"]
    assert "## 一、结论摘要" in content_payload["content"]
    assert "## 四、修复建议" in content_payload["content"]
    assert "SQL Injection" in content_payload["content"]

    download_resp = client.get(
        f"/api/v1/reports/{report_id}/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert download_resp.status_code == 200
    text = download_resp.content.decode("utf-8")
    assert "单漏洞安全报告" in text
    assert "## 五、技术附录" in text


def test_create_scan_report_generates_single_report(
    client, db_session, report_storage_settings
):
    user = _create_user(
        db_session,
        email="scan-report-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="scan-report-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=user.id,
    )
    _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="Order",
        line_start=7,
    )
    _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_any_upload",
        vuln_type="UPLOAD",
        suffix="Upload",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/OrderController.java",
        content="public class OrderController {}\n",
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/UploadController.java",
        content="public class UploadController {}\n",
    )

    tokens = _login(client, email=user.email, password="Password123!")
    response = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "report_type": "SCAN",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "options": {
                "format": "MARKDOWN",
                "include_code_snippets": False,
                "include_ai_sections": False,
            },
        },
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    assert payload["report_type"] == "SCAN"
    assert payload["finding_count"] == 2

    report_job_id = payload["report_job_id"]
    reports_resp = client.get(
        "/api/v1/reports",
        headers=_auth_header(tokens["access_token"]),
        params={"report_job_id": report_job_id},
    )
    assert reports_resp.status_code == 200
    reports_payload = reports_resp.json()["data"]
    assert reports_payload["total"] == 1
    report_item = reports_payload["items"][0]
    assert report_item["report_type"] == "SCAN"
    assert report_item["finding_count"] == 2
    assert "扫描安全报告" in report_item["title"]

    content_resp = client.get(
        f"/api/v1/reports/{report_item['id']}/content",
        headers=_auth_header(tokens["access_token"]),
    )
    assert content_resp.status_code == 200
    content = content_resp.json()["data"]["content"]
    assert "## 三、风险总览" in content
    assert "## 六、技术附录" in content
    assert "SQL Injection" in content
    assert "Arbitrary File Upload" in content


def test_create_finding_report_rejects_cross_job_finding(
    client, db_session, report_storage_settings
):
    user = _create_user(
        db_session,
        email="scope-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="scope-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job_a = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=user.id,
    )
    scan_job_b = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=user.id,
    )
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job_b.id,
        rule_key="any_any_upload",
        vuln_type="UPLOAD",
        suffix="Cross",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/CrossController.java",
        content="public class CrossController {}\n",
    )

    tokens = _login(client, email=user.email, password="Password123!")
    response = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(tokens["access_token"]),
        json={
            "report_type": "FINDING",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job_a.id),
            "finding_id": str(finding.id),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "指定漏洞不属于当前扫描任务"


def test_report_download_requires_membership(
    client, db_session, report_storage_settings
):
    owner = _create_user(
        db_session,
        email="owner-report@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    outsider = _create_user(
        db_session,
        email="outsider-report@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="secure-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=owner.id,
    )
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="Secure",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/SecureController.java",
        content="public class SecureController {}\n",
    )

    owner_tokens = _login(client, email=owner.email, password="Password123!")
    create_resp = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "report_type": "FINDING",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_id": str(finding.id),
            "options": {
                "format": "MARKDOWN",
                "include_code_snippets": False,
                "include_ai_sections": False,
            },
        },
    )
    assert create_resp.status_code == 202
    report_job_id = create_resp.json()["data"]["report_job_id"]
    report = db_session.scalar(
        select(Report).where(Report.report_job_id == uuid.UUID(report_job_id))
    )
    assert report is not None

    outsider_tokens = _login(client, email=outsider.email, password="Password123!")
    download_resp = client.get(
        f"/api/v1/reports/{report.id}/download",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert download_resp.status_code == 403


def test_report_content_requires_membership(
    client, db_session, report_storage_settings
):
    owner = _create_user(
        db_session,
        email="owner-preview@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    outsider = _create_user(
        db_session,
        email="outsider-preview@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="preview-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=owner.id,
    )
    _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="Preview",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/PreviewController.java",
        content="public class PreviewController {}\n",
    )

    owner_tokens = _login(client, email=owner.email, password="Password123!")
    create_resp = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "report_type": "SCAN",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
        },
    )
    assert create_resp.status_code == 202
    report_job_id = create_resp.json()["data"]["report_job_id"]
    report = db_session.scalar(
        select(Report).where(Report.report_job_id == uuid.UUID(report_job_id))
    )
    assert report is not None

    outsider_tokens = _login(client, email=outsider.email, password="Password123!")
    preview_resp = client.get(
        f"/api/v1/reports/{report.id}/content",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert preview_resp.status_code == 403


def test_delete_report_removes_file_and_cleans_last_report_job_artifacts(
    client, db_session, report_storage_settings
):
    owner = _create_user(
        db_session,
        email="delete-report@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="delete-report-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=owner.id,
    )
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="Delete",
        line_start=7,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/DeleteController.java",
        content="public class DeleteController {}\n",
    )

    owner_tokens = _login(client, email=owner.email, password="Password123!")
    create_resp = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "report_type": "FINDING",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_id": str(finding.id),
            "options": {
                "format": "MARKDOWN",
                "include_code_snippets": False,
                "include_ai_sections": False,
            },
        },
    )
    assert create_resp.status_code == 202
    report_job_id = create_resp.json()["data"]["report_job_id"]
    report = db_session.scalar(
        select(Report).where(Report.report_job_id == uuid.UUID(report_job_id))
    )
    assert report is not None

    report_id = report.id
    report_job_uuid = uuid.UUID(report_job_id)
    report_root = Path(get_settings().report_storage_root) / "jobs" / report_job_id
    report_log_root = Path(get_settings().report_log_root) / report_job_id
    assert report_root.exists()
    assert report_log_root.exists()

    delete_resp = client.delete(
        f"/api/v1/reports/{report_id}",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    payload = delete_resp.json()["data"]
    assert payload["ok"] is True
    assert payload["report_id"] == str(report_id)
    assert payload["remaining_report_count"] == 0
    assert payload["deleted_report_file"] is True
    assert payload["deleted_report_job_root"] is True
    assert payload["deleted_report_job_files_count"] >= 1

    assert db_session.get(Report, report_id) is None
    report_job = db_session.get(Job, report_job_uuid)
    assert report_job is not None
    assert report_job.result_summary["report_id"] is None
    assert report_job.result_summary["report_ids"] == []
    assert report_job.result_summary["manifest_object_key"] is None
    assert not report_root.exists()
    assert not report_log_root.exists()

    get_resp = client.get(
        f"/api/v1/reports/{report_id}",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert get_resp.status_code == 404
    preview_resp = client.get(
        f"/api/v1/reports/{report_id}/content",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert preview_resp.status_code == 404
    download_resp = client.get(
        f"/api/v1/reports/{report_id}/download",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert download_resp.status_code == 404


def test_report_delete_requires_membership(client, db_session, report_storage_settings):
    owner = _create_user(
        db_session,
        email="owner-delete-report@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    outsider = _create_user(
        db_session,
        email="outsider-delete-report@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="delete-membership-project")
    version = _create_version(db_session, project_id=project.id)
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    scan_job = _create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        created_by=owner.id,
    )
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_any_upload",
        vuln_type="UPLOAD",
        suffix="ForbiddenDelete",
        line_start=9,
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/ForbiddenDeleteController.java",
        content="public class ForbiddenDeleteController {}\n",
    )

    owner_tokens = _login(client, email=owner.email, password="Password123!")
    create_resp = client.post(
        "/api/v1/report-jobs",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "report_type": "FINDING",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_id": str(finding.id),
        },
    )
    assert create_resp.status_code == 202
    report_job_id = create_resp.json()["data"]["report_job_id"]
    report = db_session.scalar(
        select(Report).where(Report.report_job_id == uuid.UUID(report_job_id))
    )
    assert report is not None

    outsider_tokens = _login(client, email=outsider.email, password="Password123!")
    delete_resp = client.delete(
        f"/api/v1/reports/{report.id}",
        headers=_auth_header(outsider_tokens["access_token"]),
    )
    assert delete_resp.status_code == 403
    assert db_session.get(Report, report.id) is not None
