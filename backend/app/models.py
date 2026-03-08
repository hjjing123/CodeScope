from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SystemRole(StrEnum):
    ADMIN = "Admin"
    USER = "User"


class ProjectRole(StrEnum):
    OWNER = "Owner"
    MAINTAINER = "Maintainer"
    READER = "Reader"


class ProjectStatus(StrEnum):
    NEW = "NEW"
    IMPORTED = "IMPORTED"
    SCANNABLE = "SCANNABLE"


class VersionSource(StrEnum):
    UPLOAD = "UPLOAD"
    GIT = "GIT"
    PATCHED = "PATCHED"


class VersionStatus(StrEnum):
    READY = "READY"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class JobType(StrEnum):
    IMPORT = "IMPORT"
    SCAN = "SCAN"
    PATCH = "PATCH"
    ENV = "ENV"
    REPORT = "REPORT"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    TIMEOUT = "TIMEOUT"


class JobStage(StrEnum):
    PREPARE = "Prepare"
    ANALYZE = "Analyze"
    QUERY = "Query"
    AGGREGATE = "Aggregate"
    AI = "AI"
    CLEANUP = "Cleanup"


class JobFailureCategory(StrEnum):
    INPUT = "INPUT"
    ENV = "ENV"
    RESOURCE = "RESOURCE"
    ENGINE = "ENGINE"
    RULE = "RULE"
    AI = "AI"
    STORAGE = "STORAGE"
    SYSTEM = "SYSTEM"


class ScanMode(StrEnum):
    FULL = "FULL"
    VERIFY = "VERIFY"
    FAST = "FAST"


class FindingSeverity(StrEnum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    TP = "TP"
    FP = "FP"
    FIXED = "FIXED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReportType(StrEnum):
    PROJECT = "PROJECT"
    SCAN = "SCAN"
    FINDING = "FINDING"
    DIFF = "DIFF"
    VERIFY = "VERIFY"


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class ImportType(StrEnum):
    UPLOAD = "UPLOAD"
    GIT = "GIT"


class ImportJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    TIMEOUT = "TIMEOUT"


class ImportJobStage(StrEnum):
    VALIDATE = "Validate"
    EXTRACT = "Extract"
    CHECKOUT = "Checkout"
    ARCHIVE = "Archive"
    FINALIZE = "Finalize"


class SelfTestJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    TIMEOUT = "TIMEOUT"


class SelfTestJobStage(StrEnum):
    PREPARE = "Prepare"
    EXECUTE = "Execute"
    AGGREGATE = "Aggregate"
    CLEANUP = "Cleanup"


class RuntimeLogLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class RuntimeService(StrEnum):
    API = "api"
    WORKER = "worker"
    SCHEDULER = "scheduler"


class SystemLogKind(StrEnum):
    OPERATION = "OPERATION"
    RUNTIME = "RUNTIME"


class TaskLogType(StrEnum):
    SCAN = "SCAN"
    IMPORT = "IMPORT"
    SELFTEST = "SELFTEST"


class RuleVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SystemRole.USER.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProjectStatus.NEW.value
    )
    baseline_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionSource.UPLOAD.value
    )
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    git_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    baseline_of_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    snapshot_object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionStatus.READY.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "job_type",
            "idempotency_key",
            name="uq_job_project_type_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JobType.SCAN.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JobStatus.PENDING.value
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default=JobStage.PREPARE.value
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_hint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vuln_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FindingSeverity.MED.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FindingStatus.OPEN.value
    )
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    path_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sink_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sink_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FindingLabel(Base):
    __tablename__ = "finding_labels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fp_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class Rule(Base):
    __tablename__ = "rules"

    rule_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vuln_type: Mapped[str] = mapped_column(String(64), nullable=False)
    default_severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FindingSeverity.MED.value
    )
    language_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="java"
    )
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("rule_key", "version", name="uq_rule_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("rules.rule_key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RuleVersionStatus.DRAFT.value,
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RuleSet(Base):
    __tablename__ = "rule_sets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RuleSetItem(Base):
    __tablename__ = "rule_set_items"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "rule_key", name="uq_rule_set_rule_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rule_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("rules.rule_key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RuleStat(Base):
    __tablename__ = "rule_stats"
    __table_args__ = (
        UniqueConstraint(
            "rule_key", "rule_version", "metric_date", name="uq_rule_stat_daily"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fp_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReportType.SCAN.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReportStatus.DRAFT.value
    )
    object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_import_job_project_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ImportType.UPLOAD.value
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ImportJobStatus.PENDING.value, index=True
    )
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ImportJobStage.VALIDATE.value
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SelfTestJob(Base):
    __tablename__ = "selftest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SelfTestJobStatus.PENDING.value,
        index=True,
    )
    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SelfTestJobStage.PREPARE.value,
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_hint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class UserProjectRole(Base):
    __tablename__ = "user_project_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_user_project_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProjectRole.READER.value
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCEEDED")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    log_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SystemLogKind.RUNTIME.value, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", index=True
    )
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    task_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action_zh: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_group: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    level: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    service: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    summary_zh: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_high_value: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class RuntimeLog(Base):
    __tablename__ = "runtime_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RuntimeLogLevel.INFO.value, index=True
    )
    service: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RuntimeService.API.value, index=True
    )
    module: Mapped[str] = mapped_column(
        String(64), nullable=False, default="api", index=True
    )
    event: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", index=True
    )
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class TaskLogIndex(Base):
    __tablename__ = "task_log_index"
    __table_args__ = (
        UniqueConstraint(
            "task_type", "task_id", "stage", name="uq_task_log_index_task_stage"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TaskLogType.SCAN.value, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_backend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="local"
    )
    object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        index=True,
    )
