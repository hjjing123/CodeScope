from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import AppError
from app.models import (
    Finding,
    Job,
    Project,
    ProjectRole,
    Report,
    ReportType,
    SystemLog,
    SystemLogKind,
    SystemRole,
    User,
    UserProjectRole,
    Version,
    VersionSource,
    utc_now,
)
from app.security.password import hash_password
from app.services.audit_service import append_audit_log
from app.services.authorization_service import (
    ensure_resource_action,
    resolve_project_id,
)
from app.services.log_center_service import resolve_audit_action_meta


def _create_user(
    db,
    *,
    email: str,
    password: str,
    role: str,
    display_name: str = "tester",
    must_change_password: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_project(db, *, name: str) -> Project:
    project = Project(name=name, description="test project")
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


def _create_job(db, *, project_id: uuid.UUID, version_id: uuid.UUID) -> Job:
    job = Job(project_id=project_id, version_id=version_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _create_finding(
    db, *, project_id: uuid.UUID, version_id: uuid.UUID, job_id: uuid.UUID
) -> Finding:
    finding = Finding(
        project_id=project_id,
        version_id=version_id,
        job_id=job_id,
        rule_key="demo.rule",
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def _create_report(
    db, *, project_id: uuid.UUID, version_id: uuid.UUID, job_id: uuid.UUID
) -> Report:
    report = Report(
        project_id=project_id,
        version_id=version_id,
        job_id=job_id,
        report_type=ReportType.SCAN.value,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _add_member(
    db, *, user_id: uuid.UUID, project_id: uuid.UUID, project_role: str
) -> UserProjectRole:
    member = UserProjectRole(
        user_id=user_id, project_id=project_id, project_role=project_role
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _login(client, *, email: str, password: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_login_and_me_success(client, db_session):
    user = _create_user(
        db_session,
        email="dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
        display_name="dev",
    )

    tokens = _login(client, email=user.email, password="Password123!")
    me_resp = client.get(
        "/api/v1/auth/me", headers=_auth_header(tokens["access_token"])
    )

    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "dev@example.com"
    assert me_resp.json()["data"]["role"] == SystemRole.USER.value


def test_revoke_invalidates_existing_access_token(client, db_session):
    user = _create_user(
        db_session,
        email="rev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=user.email, password="Password123!")

    revoke_resp = client.post(
        "/api/v1/auth/revoke", json={"refresh_token": tokens["refresh_token"]}
    )
    assert revoke_resp.status_code == 200

    me_resp = client.get(
        "/api/v1/auth/me", headers=_auth_header(tokens["access_token"])
    )
    assert me_resp.status_code == 401
    assert me_resp.json()["error"]["code"] == "TOKEN_REVOKED"


def test_first_login_password_change_required_flow(client, db_session):
    user = _create_user(
        db_session,
        email="bootstrap-admin@example.com",
        password="ChangeMe123!",
        role=SystemRole.ADMIN.value,
        must_change_password=True,
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ChangeMe123!"},
    )
    assert login_resp.status_code == 403
    assert login_resp.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    reset_resp = client.post(
        "/api/v1/auth/password/first-reset",
        json={
            "email": user.email,
            "current_password": "ChangeMe123!",
            "new_password": "NewPassword123!",
        },
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["data"]["password_reset"] is True

    tokens = _login(client, email=user.email, password="NewPassword123!")
    me_resp = client.get(
        "/api/v1/auth/me", headers=_auth_header(tokens["access_token"])
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["must_change_password"] is False


def test_login_and_me_support_non_email_admin_identifier(client, db_session):
    admin = _create_user(
        db_session,
        email="admin",
        password="Password123!",
        role=SystemRole.ADMIN.value,
        display_name="Bootstrap Admin",
    )

    tokens = _login(client, email=admin.email, password="Password123!")
    me_resp = client.get(
        "/api/v1/auth/me", headers=_auth_header(tokens["access_token"])
    )

    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "admin"
    assert me_resp.json()["data"]["role"] == SystemRole.ADMIN.value


def test_platform_admin_endpoint_requires_admin(client, db_session):
    admin = _create_user(
        db_session,
        email="admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    dev = _create_user(
        db_session,
        email="dev2@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )

    dev_tokens = _login(client, email=dev.email, password="Password123!")
    denied_resp = client.get(
        "/api/v1/users", headers=_auth_header(dev_tokens["access_token"])
    )
    assert denied_resp.status_code == 403
    assert denied_resp.json()["error"]["code"] == "INSUFFICIENT_SCOPE"

    admin_tokens = _login(client, email=admin.email, password="Password123!")
    ok_resp = client.get(
        "/api/v1/users", headers=_auth_header(admin_tokens["access_token"])
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["total"] >= 2


def test_admin_can_delete_normal_user(client, db_session):
    admin = _create_user(
        db_session,
        email="delete-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    target = _create_user(
        db_session,
        email="delete-target@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )

    tokens = _login(client, email=admin.email, password="Password123!")
    resp = client.delete(
        f"/api/v1/users/{target.id}",
        headers=_auth_header(tokens["access_token"]),
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["removed"] is True
    assert db_session.get(User, target.id) is None

    logs = db_session.scalars(
        select(SystemLog).where(
            SystemLog.log_kind == SystemLogKind.OPERATION.value,
            SystemLog.action == "user.delete",
            SystemLog.operator_user_id == admin.id,
            SystemLog.resource_id == str(target.id),
        )
    ).all()
    assert len(logs) == 1


def test_delete_user_endpoint_requires_admin(client, db_session):
    admin = _create_user(
        db_session,
        email="delete-admin-only@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    dev = _create_user(
        db_session,
        email="delete-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    target = _create_user(
        db_session,
        email="delete-denied-target@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )

    dev_tokens = _login(client, email=dev.email, password="Password123!")
    denied_resp = client.delete(
        f"/api/v1/users/{target.id}",
        headers=_auth_header(dev_tokens["access_token"]),
    )

    assert denied_resp.status_code == 403
    assert denied_resp.json()["error"]["code"] == "INSUFFICIENT_SCOPE"
    assert db_session.get(User, target.id) is not None
    assert db_session.get(User, admin.id) is not None


def test_admin_cannot_delete_self(client, db_session):
    admin = _create_user(
        db_session,
        email="delete-self-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )

    tokens = _login(client, email=admin.email, password="Password123!")
    resp = client.delete(
        f"/api/v1/users/{admin.id}",
        headers=_auth_header(tokens["access_token"]),
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SELF_DELETE_FORBIDDEN"
    assert db_session.get(User, admin.id) is not None


def test_permissions_endpoint_platform_scope_for_admin(client, db_session):
    admin = _create_user(
        db_session,
        email="admin-perm@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    resp = client.get(
        "/api/v1/auth/permissions", headers=_auth_header(tokens["access_token"])
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["scope_type"] == "platform"
    assert "system:config" in resp.json()["data"]["actions"]


def test_permissions_endpoint_project_scope_for_maintainer(client, db_session):
    dev = _create_user(
        db_session,
        email="maintainer-perm@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="perm-project")
    _add_member(
        db_session,
        user_id=dev.id,
        project_id=project.id,
        project_role=ProjectRole.MAINTAINER.value,
    )

    tokens = _login(client, email=dev.email, password="Password123!")
    resp = client.get(
        f"/api/v1/auth/permissions?project_id={project.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["scope_type"] == "project"
    assert resp.json()["data"]["project_role"] == ProjectRole.MAINTAINER.value
    assert "project:write" in resp.json()["data"]["actions"]
    assert "project:delete" not in resp.json()["data"]["actions"]


def test_permissions_endpoint_project_scope_requires_membership(client, db_session):
    dev = _create_user(
        db_session,
        email="nomember-perm@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="perm-no-member")

    tokens = _login(client, email=dev.email, password="Password123!")
    resp = client.get(
        f"/api/v1/auth/permissions?project_id={project.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"


def test_cross_project_member_access_is_blocked(client, db_session):
    dev = _create_user(
        db_session,
        email="cross@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project_a = _create_project(db_session, name="A")
    project_b = _create_project(db_session, name="B")
    _add_member(
        db_session,
        user_id=dev.id,
        project_id=project_a.id,
        project_role=ProjectRole.MAINTAINER.value,
    )

    tokens = _login(client, email=dev.email, password="Password123!")
    resp = client.get(
        f"/api/v1/projects/{project_b.id}/members",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"


def test_indirect_project_resource_access_allows_same_project(client, db_session):
    owner = _create_user(
        db_session,
        email="owner-indirect@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    reader = _create_user(
        db_session,
        email="reader-indirect@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    target = _create_user(
        db_session,
        email="target-indirect@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="indirect-project")
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    _add_member(
        db_session,
        user_id=reader.id,
        project_id=project.id,
        project_role=ProjectRole.READER.value,
    )
    target_member = _add_member(
        db_session,
        user_id=target.id,
        project_id=project.id,
        project_role=ProjectRole.READER.value,
    )

    tokens = _login(client, email=reader.email, password="Password123!")
    resp = client.get(
        f"/api/v1/project-members/{target_member.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["project_id"] == str(project.id)


def test_indirect_project_resource_access_blocks_cross_project(client, db_session):
    dev = _create_user(
        db_session,
        email="cross-indirect@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    other = _create_user(
        db_session,
        email="cross-indirect-other@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project_a = _create_project(db_session, name="indirect-A")
    project_b = _create_project(db_session, name="indirect-B")
    _add_member(
        db_session,
        user_id=dev.id,
        project_id=project_a.id,
        project_role=ProjectRole.READER.value,
    )
    member_b = _add_member(
        db_session,
        user_id=other.id,
        project_id=project_b.id,
        project_role=ProjectRole.READER.value,
    )

    tokens = _login(client, email=dev.email, password="Password123!")
    resp = client.get(
        f"/api/v1/project-members/{member_b.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PROJECT_MEMBERSHIP_REQUIRED"


def test_resolve_project_id_for_version_job_finding_report(db_session):
    project = _create_project(db_session, name="resolver-project")
    version = _create_version(db_session, project_id=project.id)
    job = _create_job(db_session, project_id=project.id, version_id=version.id)
    finding = _create_finding(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=job.id,
    )
    report = _create_report(
        db_session,
        project_id=project.id,
        version_id=version.id,
        job_id=job.id,
    )

    assert (
        resolve_project_id(
            db=db_session, resource_type="VERSION", resource_id=version.id
        )
        == project.id
    )
    assert (
        resolve_project_id(db=db_session, resource_type="JOB", resource_id=job.id)
        == project.id
    )
    assert (
        resolve_project_id(
            db=db_session, resource_type="FINDING", resource_id=finding.id
        )
        == project.id
    )
    assert (
        resolve_project_id(db=db_session, resource_type="REPORT", resource_id=report.id)
        == project.id
    )


def test_ensure_resource_action_blocks_cross_project_for_job(db_session):
    user = _create_user(
        db_session,
        email="resolver-cross@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project_a = _create_project(db_session, name="resolver-A")
    project_b = _create_project(db_session, name="resolver-B")
    _add_member(
        db_session,
        user_id=user.id,
        project_id=project_a.id,
        project_role=ProjectRole.READER.value,
    )

    version_b = _create_version(db_session, project_id=project_b.id, name="vB")
    job_b = _create_job(db_session, project_id=project_b.id, version_id=version_b.id)

    with pytest.raises(AppError) as exc_info:
        ensure_resource_action(
            db=db_session,
            user_id=user.id,
            role=user.role,
            action="job:read",
            resource_type="JOB",
            resource_id=job_b.id,
        )

    assert exc_info.value.code == "PROJECT_MEMBERSHIP_REQUIRED"


def test_resolve_project_id_rejects_unsupported_resource_type(db_session):
    with pytest.raises(AppError) as exc_info:
        resolve_project_id(
            db=db_session, resource_type="UNKNOWN", resource_id=uuid.uuid4()
        )

    assert exc_info.value.code == "RESOURCE_TYPE_UNSUPPORTED"


def test_last_owner_protected_on_delete(client, db_session):
    owner = _create_user(
        db_session,
        email="owner@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="owner-project")
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )

    tokens = _login(client, email=owner.email, password="Password123!")
    resp = client.delete(
        f"/api/v1/projects/{project.id}/members/{owner.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LAST_OWNER_PROTECTED"


def test_users_create_endpoint_removed(client, db_session):
    admin = _create_user(
        db_session,
        email="no-create-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    create_resp = client.post(
        "/api/v1/users",
        headers=_auth_header(tokens["access_token"]),
        json={
            "email": "new-user-should-fail@example.com",
            "password": "Password123!",
            "display_name": "new-user",
            "role": SystemRole.USER.value,
        },
    )
    assert create_resp.status_code == 405


def test_register_assigns_user_role_by_default(client):
    user_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register-default-user@example.com",
            "password": "Password123!",
            "display_name": "register-default-user",
        },
    )
    assert user_resp.status_code == 201
    assert user_resp.json()["data"]["role"] == SystemRole.USER.value

    user_tokens = _login(
        client, email="register-default-user@example.com", password="Password123!"
    )
    user_me = client.get(
        "/api/v1/auth/me", headers=_auth_header(user_tokens["access_token"])
    )
    assert user_me.status_code == 200
    assert user_me.json()["data"]["role"] == SystemRole.USER.value


def test_register_rejects_admin_role_and_does_not_persist(client, db_session):
    before_user = db_session.scalar(
        select(User).where(User.email == "register-admin-reject@example.com")
    )
    assert before_user is None

    admin_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register-admin-reject@example.com",
            "password": "Password123!",
            "display_name": "register-admin-reject",
            "role": SystemRole.ADMIN.value,
        },
    )
    assert admin_resp.status_code == 422
    assert admin_resp.json()["error"]["code"] == "INVALID_ARGUMENT"

    after_user = db_session.scalar(
        select(User).where(User.email == "register-admin-reject@example.com")
    )
    assert after_user is None

    logs = db_session.scalars(
        select(SystemLog).where(
            SystemLog.log_kind == SystemLogKind.OPERATION.value,
            SystemLog.action == "auth.register",
        )
    ).all()
    assert len(logs) == 0


def test_register_rejects_unknown_role(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register-unknown-should-fail@example.com",
            "password": "Password123!",
            "display_name": "register-unknown",
            "role": "LegacyRole",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_register_writes_audit_log(client, db_session):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "audit-register@example.com",
            "password": "Password123!",
            "display_name": "audit-register",
            "role": SystemRole.USER.value,
        },
    )
    assert resp.status_code == 201

    user_id = resp.json()["data"]["id"]
    logs = db_session.scalars(
        select(SystemLog).where(
            SystemLog.log_kind == SystemLogKind.OPERATION.value,
            SystemLog.action == "auth.register",
            SystemLog.operator_user_id == uuid.UUID(user_id),
        )
    ).all()
    assert len(logs) == 1


def test_maintainer_can_manage_members(client, db_session):
    owner = _create_user(
        db_session,
        email="owner2@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    maintainer = _create_user(
        db_session,
        email="maintainer@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    target = _create_user(
        db_session,
        email="target@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="maintainer-project")
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    _add_member(
        db_session,
        user_id=maintainer.id,
        project_id=project.id,
        project_role=ProjectRole.MAINTAINER.value,
    )

    tokens = _login(client, email=maintainer.email, password="Password123!")
    add_resp = client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=_auth_header(tokens["access_token"]),
        json={"user_id": str(target.id), "project_role": ProjectRole.READER.value},
    )
    assert add_resp.status_code == 201


def test_reader_cannot_manage_members(client, db_session):
    owner = _create_user(
        db_session,
        email="owner3@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    reader = _create_user(
        db_session,
        email="reader@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    target = _create_user(
        db_session,
        email="target2@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="reader-project")
    _add_member(
        db_session,
        user_id=owner.id,
        project_id=project.id,
        project_role=ProjectRole.OWNER.value,
    )
    _add_member(
        db_session,
        user_id=reader.id,
        project_id=project.id,
        project_role=ProjectRole.READER.value,
    )

    tokens = _login(client, email=reader.email, password="Password123!")
    add_resp = client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=_auth_header(tokens["access_token"]),
        json={"user_id": str(target.id), "project_role": ProjectRole.READER.value},
    )
    assert add_resp.status_code == 403
    assert add_resp.json()["error"]["code"] == "FORBIDDEN"


def test_owner_can_delete_own_project(client, db_session):
    owner = _create_user(
        db_session,
        email="owner-delete@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    owner_tokens = _login(client, email=owner.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"name": "owner-delete-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    delete_resp = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    get_resp = client.get(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert get_resp.status_code == 404


def test_maintainer_cannot_delete_project(client, db_session):
    owner = _create_user(
        db_session,
        email="owner-keep@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    maintainer = _create_user(
        db_session,
        email="maintainer-no-delete@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    owner_tokens = _login(client, email=owner.email, password="Password123!")
    maintainer_tokens = _login(client, email=maintainer.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"name": "maintainer-no-delete-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    add_member_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=_auth_header(owner_tokens["access_token"]),
        json={
            "user_id": str(maintainer.id),
            "project_role": ProjectRole.MAINTAINER.value,
        },
    )
    assert add_member_resp.status_code == 201

    delete_resp = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(maintainer_tokens["access_token"]),
    )
    assert delete_resp.status_code == 403
    assert delete_resp.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_delete_any_project(client, db_session):
    owner = _create_user(
        db_session,
        email="owner-for-admin-delete@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    admin = _create_user(
        db_session,
        email="admin-delete@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    owner_tokens = _login(client, email=owner.email, password="Password123!")
    admin_tokens = _login(client, email=admin.email, password="Password123!")

    project_resp = client.post(
        "/api/v1/projects",
        headers=_auth_header(owner_tokens["access_token"]),
        json={"name": "admin-delete-project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["data"]["id"]

    delete_resp = client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(admin_tokens["access_token"]),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    owner_get_resp = client.get(
        f"/api/v1/projects/{project_id}",
        headers=_auth_header(owner_tokens["access_token"]),
    )
    assert owner_get_resp.status_code == 404


def test_audit_logs_endpoint_scopes_regular_user_to_own_entries(client, db_session):
    admin = _create_user(
        db_session,
        email="audit-list-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    developer = _create_user(
        db_session,
        email="audit-list-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    other_user = _create_user(
        db_session,
        email="audit-list-other@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    request_id = "req-audit-scope"

    db_session.add_all(
        [
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id=request_id,
                operator_user_id=developer.id,
                action="finding.label",
                action_zh="标记漏洞",
                action_group="finding",
                resource_type="FINDING",
                resource_id="finding-own",
                result="SUCCEEDED",
                summary_zh="标记漏洞",
                detail_json={"context": {"scope": "self"}},
                occurred_at=utc_now(),
            ),
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id=request_id,
                operator_user_id=other_user.id,
                action="finding.label",
                action_zh="标记漏洞",
                action_group="finding",
                resource_type="FINDING",
                resource_id="finding-other",
                result="SUCCEEDED",
                summary_zh="标记漏洞",
                detail_json={"context": {"scope": "other"}},
                occurred_at=utc_now(),
            ),
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id=request_id,
                operator_user_id=None,
                action="system.cleanup",
                action_zh="系统清理",
                action_group="system",
                resource_type="SYSTEM",
                resource_id="cleanup-job",
                result="SUCCEEDED",
                summary_zh="系统清理",
                detail_json={"context": {"scope": "system"}},
                occurred_at=utc_now(),
            ),
        ]
    )
    db_session.commit()

    dev_tokens = _login(client, email=developer.email, password="Password123!")
    scoped_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(dev_tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()["data"]
    assert scoped_data["total"] == 1
    assert len(scoped_data["items"]) == 1
    assert scoped_data["items"][0]["operator_user_id"] == str(developer.id)
    assert scoped_data["items"][0]["resource_id"] == "finding-own"

    admin_tokens = _login(client, email=admin.email, password="Password123!")
    logs_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(admin_tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert logs_resp.status_code == 200
    assert logs_resp.json()["data"]["total"] == 3


def test_runtime_logs_endpoint_admin_only(client, db_session):
    admin = _create_user(
        db_session,
        email="runtime-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    developer = _create_user(
        db_session,
        email="runtime-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )

    dev_tokens = _login(client, email=developer.email, password="Password123!")
    denied_runtime = client.get(
        "/api/v1/runtime-logs", headers=_auth_header(dev_tokens["access_token"])
    )
    assert denied_runtime.status_code == 403
    assert denied_runtime.json()["error"]["code"] == "INSUFFICIENT_SCOPE"

    admin_tokens = _login(client, email=admin.email, password="Password123!")
    register_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "runtime-created@example.com",
            "password": "Password123!",
            "display_name": "runtime-created",
            "role": SystemRole.USER.value,
        },
    )
    assert register_resp.status_code == 201
    request_id = register_resp.json()["request_id"]

    db_session.add(
        SystemLog(
            log_kind=SystemLogKind.RUNTIME.value,
            level="INFO",
            service="api",
            module="test",
            event="test.runtime.seeded",
            message="seed runtime log for endpoint tests",
            request_id=request_id,
            detail_json={"source": "test"},
        )
    )
    db_session.commit()

    runtime_resp = client.get(
        "/api/v1/runtime-logs",
        headers=_auth_header(admin_tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert runtime_resp.status_code == 200
    assert runtime_resp.json()["data"]["total"] >= 1


def test_log_endpoints_tolerate_non_object_detail_json(client, db_session):
    admin = _create_user(
        db_session,
        email="log-malformed-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")
    request_id = "req-log-malformed"

    db_session.add_all(
        [
            SystemLog(
                log_kind=SystemLogKind.RUNTIME.value,
                level="INFO",
                service="api",
                module="test",
                event="runtime.malformed.detail",
                message="runtime malformed detail",
                request_id=request_id,
                detail_json=["not-object"],
            ),
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id=request_id,
                operator_user_id=admin.id,
                action="auth.register",
                action_zh="注册用户",
                action_group="auth",
                resource_type="USER",
                resource_id=str(admin.id),
                result="SUCCEEDED",
                summary_zh="注册用户",
                is_high_value=True,
                detail_json=["not-object"],
            ),
        ]
    )
    db_session.commit()

    runtime_resp = client.get(
        "/api/v1/runtime-logs",
        headers=_auth_header(tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert runtime_resp.status_code == 200
    runtime_items = runtime_resp.json()["data"]["items"]
    assert len(runtime_items) >= 1
    assert runtime_items[0]["detail_json"] == {}

    audit_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["data"]["items"]
    assert len(audit_items) >= 1
    assert audit_items[0]["detail_json"] == {}


def test_audit_logs_support_keyword_group_and_zh_fields(client, db_session):
    admin = _create_user(
        db_session,
        email="audit-zh-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    append_audit_log(
        db_session,
        request_id="req-audit-zh-1",
        operator_user_id=admin.id,
        action="version.create",
        resource_type="VERSION",
        resource_id="version-a",
        detail_json={
            "source": "UPLOAD",
            "snapshot_object_key": "snapshots/version-a/snapshot.tar.gz",
        },
    )
    append_audit_log(
        db_session,
        request_id="req-audit-zh-2",
        operator_user_id=admin.id,
        action="rule.toggle",
        resource_type="RULE",
        resource_id="rule.demo",
        detail_json={"enabled": False, "rule_key": "rule.demo"},
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={
            "action_group": "version",
            "keyword": "代码快照",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["action"] == "version.create"
    assert item["action_zh"] == "创建代码快照"
    assert item["action_group"] == "version"
    assert "创建代码快照" in item["summary_zh"]
    assert set(item["detail_json"].keys()) == {"context", "change", "outcome"}
    assert "project_id" not in item
    assert "error_code" not in item
    assert "is_high_value" not in item


def test_audit_logs_ignore_removed_filters_and_hide_removed_fields(client, db_session):
    admin = _create_user(
        db_session,
        email="audit-contract-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")
    project_a = _create_project(db_session, name="audit-contract-a")
    project_b = _create_project(db_session, name="audit-contract-b")

    db_session.add_all(
        [
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id="req-audit-contract-a",
                operator_user_id=admin.id,
                action="project.update",
                action_zh="Project updated",
                action_group="project",
                resource_type="PROJECT",
                resource_id="project-a",
                project_id=project_a.id,
                result="SUCCEEDED",
                error_code="LEGACY_A",
                summary_zh="Project updated",
                is_high_value=True,
                detail_json={"context": {"source": "legacy-a"}},
                occurred_at=utc_now(),
            ),
            SystemLog(
                log_kind=SystemLogKind.OPERATION.value,
                request_id="req-audit-contract-b",
                operator_user_id=admin.id,
                action="version.create",
                action_zh="Version created",
                action_group="version",
                resource_type="VERSION",
                resource_id="version-b",
                project_id=project_b.id,
                result="SUCCEEDED",
                error_code="LEGACY_B",
                summary_zh="Version created",
                is_high_value=False,
                detail_json={"context": {"source": "legacy-b"}},
                occurred_at=utc_now(),
            ),
        ]
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={
            "project_id": str(project_a.id),
            "action": "project.update",
            "error_code": "LEGACY_A",
            "high_value_only": "true",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    for item in data["items"]:
        assert "project_id" not in item
        assert "error_code" not in item
        assert "is_high_value" not in item


def test_audit_action_zh_fallback_from_action_mapping(client, db_session):
    admin = _create_user(
        db_session,
        email="audit-fallback-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")
    request_id = "req-audit-fallback-action-zh"
    db_session.add(
        SystemLog(
            log_kind=SystemLogKind.OPERATION.value,
            request_id=request_id,
            operator_user_id=admin.id,
            action="import.dispatch.failed",
            action_zh="import.dispatch.failed",
            action_group="import",
            resource_type="VERSION",
            resource_id="v-1",
            result="FAILED",
            summary_zh="导入派发失败",
            is_high_value=True,
            detail_json={"context": {"source": "legacy"}},
            occurred_at=utc_now(),
        )
    )
    db_session.commit()

    audit_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["data"]["items"]
    assert len(audit_items) == 1
    assert audit_items[0]["action"] == "import.dispatch.failed"
    assert audit_items[0]["action_zh"] == "导入派发失败"


@pytest.mark.parametrize(
    ("action", "expected_action_zh", "expected_action_group"),
    [
        ("ai.chat.session.created", "创建通用 AI 会话", "ai"),
        ("ai.chat.session.deleted", "删除 AI 会话", "ai"),
        ("ai.chat.session.selection.updated", "更新 AI 会话模型选择", "ai"),
        ("ai.chat.message.sent", "发送 AI 对话消息", "ai"),
        ("ai.chat.message.failed", "AI 对话消息失败", "ai"),
        ("ai.job.dispatch.failed", "AI 任务派发失败", "ai"),
        ("ai.job.completed", "AI 任务完成", "ai"),
        ("ai.job.failed", "AI 任务失败", "ai"),
        ("finding.ai.chat.session.created", "创建漏洞 AI 会话", "finding"),
        ("finding.ai.retry.triggered", "触发漏洞 AI 研判重试", "finding"),
        ("user.ai.provider.created", "创建个人 AI 提供方", "user"),
        ("user.ai.provider.updated", "更新个人 AI 提供方", "user"),
        ("user.ai.provider.deleted", "删除个人 AI 提供方", "user"),
        ("user.ai.provider.tested", "测试个人 AI 提供方", "user"),
        ("user.ai.provider.draft_tested", "测试个人 AI 提供方草稿", "user"),
        ("system.ai.ollama.updated", "更新系统 Ollama 配置", "system"),
        ("system.ai.ollama.tested", "测试系统 Ollama 配置", "system"),
        ("system.ai.ollama.model.pull.triggered", "触发 Ollama 模型拉取", "system"),
        ("system.ai.ollama.model.pull.succeeded", "Ollama 模型拉取成功", "system"),
        ("system.ai.ollama.model.pull.failed", "Ollama 模型拉取失败", "system"),
        ("system.ai.ollama.model.deleted", "删除 Ollama 模型", "system"),
    ],
)
def test_ai_audit_action_meta_resolves_translations(
    action, expected_action_zh, expected_action_group
):
    meta = resolve_audit_action_meta(action)

    assert meta.action_zh == expected_action_zh
    assert meta.action_group == expected_action_group


def test_audit_summary_zh_fallback_for_legacy_ai_actions(client, db_session):
    admin = _create_user(
        db_session,
        email="audit-ai-summary-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")
    request_id = "req-audit-ai-summary-fallback"
    db_session.add(
        SystemLog(
            log_kind=SystemLogKind.OPERATION.value,
            request_id=request_id,
            operator_user_id=admin.id,
            action="ai.chat.session.created",
            action_zh="ai.chat.session.created",
            action_group="ai",
            resource_type="AI_CHAT_SESSION",
            resource_id="session-legacy",
            result="SUCCEEDED",
            summary_zh="ai.chat.session.created",
            is_high_value=True,
            detail_json={"context": {"session_mode": "general"}},
            occurred_at=utc_now(),
        )
    )
    db_session.commit()

    audit_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={"request_id": request_id},
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["data"]["items"]
    assert len(audit_items) == 1
    assert audit_items[0]["action"] == "ai.chat.session.created"
    assert audit_items[0]["action_zh"] == "创建通用 AI 会话"
    assert audit_items[0]["summary_zh"] == "创建通用 AI 会话"
    assert audit_items[0]["action_group"] == "ai"


def test_runtime_http_logging_uses_high_value_strategy(client, db_session):
    settings = get_settings()
    original_sample = settings.runtime_http_log_sample_rate
    original_record_success = settings.runtime_http_log_record_success
    original_slow_threshold = settings.runtime_http_log_slow_threshold_ms
    settings.runtime_http_log_sample_rate = 0.0
    settings.runtime_http_log_record_success = False
    settings.runtime_http_log_slow_threshold_ms = 10_000
    try:
        health_resp = client.get("/healthz")
        assert health_resp.status_code == 200

        missing_resp = client.get("/api/v1/not-found-demo")
        assert missing_resp.status_code == 404
    finally:
        settings.runtime_http_log_sample_rate = original_sample
        settings.runtime_http_log_record_success = original_record_success
        settings.runtime_http_log_slow_threshold_ms = original_slow_threshold

    success_logs = db_session.scalars(
        select(SystemLog).where(
            SystemLog.log_kind == SystemLogKind.RUNTIME.value,
            SystemLog.message == "GET /healthz -> 200",
        )
    ).all()
    assert success_logs == []

    failed_logs = db_session.scalars(
        select(SystemLog).where(
            SystemLog.log_kind == SystemLogKind.RUNTIME.value,
            SystemLog.message == "GET /api/v1/not-found-demo -> 404",
        )
    ).all()
    assert len(failed_logs) == 1
    assert failed_logs[0].is_high_value is True
    assert failed_logs[0].detail_json.get("capture_reason") == "error"


def test_log_center_delete_endpoints_without_audit(client, db_session):
    admin = _create_user(
        db_session,
        email="log-delete-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    target_single = SystemLog(
        log_kind=SystemLogKind.RUNTIME.value,
        request_id="req-log-delete-single",
        level="INFO",
        service="api",
        module="test",
        event="runtime.single",
        message="single-delete",
        is_high_value=False,
        detail_json={"context": {"source": "test"}},
        occurred_at=utc_now(),
    )
    target_batch_a = SystemLog(
        log_kind=SystemLogKind.OPERATION.value,
        request_id="req-log-delete-batch",
        action="project.update",
        action_zh="更新项目",
        action_group="project",
        summary_zh="更新项目",
        is_high_value=True,
        resource_type="PROJECT",
        resource_id="p-1",
        result="SUCCEEDED",
        detail_json={"context": {"source": "batch"}},
        occurred_at=utc_now(),
    )
    target_batch_b = SystemLog(
        log_kind=SystemLogKind.RUNTIME.value,
        request_id="req-log-delete-batch",
        level="ERROR",
        service="worker",
        module="worker.tasks",
        event="worker.task.failed",
        message="batch-delete",
        is_high_value=True,
        detail_json={"context": {"source": "batch"}},
        occurred_at=utc_now(),
    )
    db_session.add_all([target_single, target_batch_a, target_batch_b])
    db_session.commit()

    single_resp = client.delete(
        f"/api/v1/log-center/logs/{target_single.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert single_resp.status_code == 200
    assert single_resp.json()["data"]["deleted"] is True

    detail_after_delete = client.get(
        f"/api/v1/runtime-logs/{target_single.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert detail_after_delete.status_code == 404

    batch_resp = client.post(
        "/api/v1/log-center/logs/batch-delete",
        headers=_auth_header(tokens["access_token"]),
        json={"request_id": "req-log-delete-batch"},
    )
    assert batch_resp.status_code == 200
    assert batch_resp.json()["data"]["deleted_count"] == 2

    remain = db_session.scalars(
        select(SystemLog).where(SystemLog.request_id == "req-log-delete-batch")
    ).all()
    assert remain == []

    audit_resp = client.get(
        "/api/v1/audit-logs",
        headers=_auth_header(tokens["access_token"]),
        params={"action_group": "log", "keyword": "log.delete"},
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json()["data"]["total"] == 0


def test_log_center_delete_endpoints_remain_admin_only_for_regular_user(
    client, db_session
):
    developer = _create_user(
        db_session,
        email="log-delete-dev@example.com",
        password="Password123!",
        role=SystemRole.USER.value,
    )
    tokens = _login(client, email=developer.email, password="Password123!")

    target_log = SystemLog(
        log_kind=SystemLogKind.OPERATION.value,
        request_id="req-log-delete-user-denied",
        operator_user_id=developer.id,
        action="finding.label",
        action_zh="标记漏洞",
        action_group="finding",
        resource_type="FINDING",
        resource_id="finding-user-denied",
        result="SUCCEEDED",
        summary_zh="标记漏洞",
        detail_json={"context": {"source": "test"}},
        occurred_at=utc_now(),
    )
    db_session.add(target_log)
    db_session.commit()

    single_resp = client.delete(
        f"/api/v1/log-center/logs/{target_log.id}",
        headers=_auth_header(tokens["access_token"]),
    )
    assert single_resp.status_code == 403
    assert single_resp.json()["error"]["code"] == "INSUFFICIENT_SCOPE"

    batch_resp = client.post(
        "/api/v1/log-center/logs/batch-delete",
        headers=_auth_header(tokens["access_token"]),
        json={"request_id": "req-log-delete-user-denied"},
    )
    assert batch_resp.status_code == 403
    assert batch_resp.json()["error"]["code"] == "INSUFFICIENT_SCOPE"


def test_log_center_batch_delete_rejects_removed_filter_only_payloads(client, db_session):
    admin = _create_user(
        db_session,
        email="log-delete-filter-admin@example.com",
        password="Password123!",
        role=SystemRole.ADMIN.value,
    )
    tokens = _login(client, email=admin.email, password="Password123!")

    resp = client.post(
        "/api/v1/log-center/logs/batch-delete",
        headers=_auth_header(tokens["access_token"]),
        json={"project_id": str(uuid.uuid4()), "high_value_only": True},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "INVALID_ARGUMENT"
