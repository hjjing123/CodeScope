from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    Finding,
    FindingStatus,
    Job,
    JobStatus,
    JobType,
    RuleStat,
    utc_now,
)


def dispatch_rule_stats_aggregation(db: Session, *, job_id: uuid.UUID) -> str | None:
    from app.worker.tasks import enqueue_rule_stats_aggregation

    bind = db.get_bind()
    bind_engine = getattr(bind, "engine", bind)
    return enqueue_rule_stats_aggregation(job_id=job_id, db_bind=bind_engine)


def run_rule_stats_aggregation(*, job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()

    try:
        job = session.get(Job, job_id)
        if job is None or job.job_type != JobType.SCAN.value:
            return

        metric_date = _metric_date_for_job(job)
        duration_map = _duration_map(job.result_summary)

        grouped: dict[tuple[str, int], dict[str, int]] = {}
        findings = session.scalars(
            select(Finding).where(Finding.job_id == job.id)
        ).all()
        for finding in findings:
            version = int(finding.rule_version or 0)
            key = (finding.rule_key, version)
            bucket = grouped.setdefault(
                key, {"hits": 0, "fp_count": 0, "timeout_count": 0}
            )
            bucket["hits"] += 1
            if finding.status == FindingStatus.FP.value:
                bucket["fp_count"] += 1

        if not grouped and job.status == JobStatus.TIMEOUT.value:
            for rule_name in _timeout_rule_candidates(job.payload):
                key = (rule_name, 0)
                grouped[key] = {"hits": 0, "fp_count": 0, "timeout_count": 1}

        for (rule_key, rule_version), metrics in grouped.items():
            duration_ms = int(duration_map.get(rule_key, 0))
            _upsert_rule_stat(
                session,
                metric_date=metric_date,
                rule_key=rule_key,
                rule_version=rule_version,
                hits=metrics["hits"],
                avg_duration_ms=duration_ms,
                timeout_count=metrics["timeout_count"],
                fp_count=metrics["fp_count"],
            )

        if grouped:
            session.commit()
    finally:
        if owns_db:
            session.close()


def _metric_date_for_job(job: Job) -> date:
    finished = job.finished_at or utc_now()
    return finished.date()


def _duration_map(summary: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(summary, dict):
        return {}
    raw = summary.get("rule_duration_ms")
    if not isinstance(raw, dict):
        return {}

    parsed: dict[str, int] = {}
    for key, value in raw.items():
        try:
            parsed[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _timeout_rule_candidates(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("resolved_rule_keys")
    if not isinstance(raw, list):
        raw = payload.get("rule_keys")
    if not isinstance(raw, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name:
            continue
        marker = name.lower()
        if marker in seen:
            continue
        seen.add(marker)
        names.append(name)
    return names


def _upsert_rule_stat(
    db: Session,
    *,
    metric_date: date,
    rule_key: str,
    rule_version: int,
    hits: int,
    avg_duration_ms: int,
    timeout_count: int,
    fp_count: int,
) -> None:
    existing = db.scalar(
        select(RuleStat).where(
            RuleStat.rule_key == rule_key,
            RuleStat.rule_version == rule_version,
            RuleStat.metric_date == metric_date,
        )
    )
    if existing is None:
        db.add(
            RuleStat(
                rule_key=rule_key,
                rule_version=rule_version,
                metric_date=metric_date,
                hits=hits,
                avg_duration_ms=avg_duration_ms,
                timeout_count=timeout_count,
                fp_count=fp_count,
            )
        )
        return

    previous_hits = int(existing.hits)
    new_total_hits = previous_hits + int(hits)
    if new_total_hits <= 0:
        existing.avg_duration_ms = 0
    elif avg_duration_ms > 0:
        weighted_total = (
            existing.avg_duration_ms * previous_hits + avg_duration_ms * int(hits)
        )
        existing.avg_duration_ms = int(weighted_total / new_total_hits)

    existing.hits = new_total_hits
    existing.timeout_count = int(existing.timeout_count) + int(timeout_count)
    existing.fp_count = int(existing.fp_count) + int(fp_count)
