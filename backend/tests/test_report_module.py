from __future__ import annotations

import io
import uuid
from pathlib import Path
from zipfile import ZipFile

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


def test_create_selected_finding_report_and_download_single_file(
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
            "generation_mode": "FINDING_SET",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_ids": [str(finding.id)],
            "options": {
                "format": "MARKDOWN",
                "include_code_snippets": True,
                "include_ai_sections": False,
            },
        },
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    assert payload["expected_report_count"] == 1
    assert payload["bundle_expected"] is False

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
    report_id = reports_payload["items"][0]["id"]
    assert reports_payload["items"][0]["finding_id"] == str(finding.id)

    artifacts_resp = client.get(
        f"/api/v1/jobs/{report_job_id}/artifacts",
        headers=_auth_header(tokens["access_token"]),
    )
    assert artifacts_resp.status_code == 200
    artifact_names = {
        item["display_name"] for item in artifacts_resp.json()["data"]["items"]
    }
    assert "manifest.json" in artifact_names
    assert any(
        name.startswith("generated/") and name.endswith(".md")
        for name in artifact_names
    )

    download_resp = client.get(
        f"/api/v1/reports/{report_id}/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert download_resp.status_code == 200
    text = download_resp.content.decode("utf-8")
    assert "# Finding Report" in text
    assert str(finding.id) in text
    assert "SQL Injection" in text


def test_create_job_all_report_generates_bundle_artifact(
    client, db_session, report_storage_settings
):
    user = _create_user(
        db_session,
        email="bundle-user@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="bundle-project")
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
    finding_a = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=scan_job.id,
        rule_key="any_mybatis_sqli",
        vuln_type="SQLI",
        suffix="Order",
        line_start=7,
    )
    finding_b = _create_finding(
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
        content=(
            "package com.demo;\n\n"
            "import org.springframework.web.bind.annotation.GetMapping;\n\n"
            "public class OrderController {\n"
            '  @GetMapping("/orders")\n'
            "  public String listOrders(String sort) {\n"
            '    return "orders" + sort;\n'
            "  }\n"
            "}\n"
        ),
    )
    _write_snapshot_source(
        version.id,
        relative_path="src/main/java/com/demo/UploadController.java",
        content=(
            "package com.demo;\n\n"
            "import org.springframework.web.bind.annotation.PostMapping;\n\n"
            "public class UploadController {\n"
            '  @PostMapping("/upload")\n'
            "  public String upload(String name) {\n"
            "    return name;\n"
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
            "generation_mode": "JOB_ALL",
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
    assert payload["expected_report_count"] == 2
    assert payload["bundle_expected"] is True

    report_job_id = payload["report_job_id"]
    artifacts_resp = client.get(
        f"/api/v1/jobs/{report_job_id}/artifacts",
        headers=_auth_header(tokens["access_token"]),
    )
    assert artifacts_resp.status_code == 200
    artifacts = artifacts_resp.json()["data"]["items"]
    bundle_item = next(item for item in artifacts if item["artifact_type"] == "BUNDLE")
    manifest_item = next(
        item for item in artifacts if item["artifact_type"] == "MANIFEST"
    )
    assert manifest_item["display_name"] == "manifest.json"

    bundle_resp = client.get(
        f"/api/v1/jobs/{report_job_id}/artifacts/{bundle_item['artifact_id']}/download",
        headers=_auth_header(tokens["access_token"]),
    )
    assert bundle_resp.status_code == 200
    with ZipFile(io.BytesIO(bundle_resp.content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert (
            len(
                [
                    name
                    for name in names
                    if name.startswith("generated/") and name.endswith(".md")
                ]
            )
            == 2
        )

    reports = db_session.scalars(
        select(Report).where(Report.report_job_id == uuid.UUID(report_job_id))
    ).all()
    assert {item.finding_id for item in reports} == {finding_a.id, finding_b.id}


def test_create_selected_report_rejects_cross_job_findings(
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
            "generation_mode": "FINDING_SET",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job_a.id),
            "finding_ids": [str(finding.id)],
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
            "generation_mode": "FINDING_SET",
            "project_id": str(project.id),
            "version_id": str(version.id),
            "job_id": str(scan_job.id),
            "finding_ids": [str(finding.id)],
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
