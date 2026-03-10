from __future__ import annotations

import uuid

from app.config import get_settings
from app.models import (
    Finding,
    FindingPath,
    FindingPathStep,
    Job,
    JobStage,
    JobStatus,
    JobType,
    Project,
    Version,
)
from app.services.finding_path_service import (
    query_finding_paths,
    resolve_finding_neo4j_target,
)


def _seed_finding_scope(db_session):
    project = Project(name=f"finding-path-{uuid.uuid4().hex[:8]}", status="SCANNABLE")
    db_session.add(project)
    db_session.flush()

    version = Version(
        project_id=project.id,
        name="v1",
        source="UPLOAD",
        status="READY",
        snapshot_object_key=f"snapshots/{uuid.uuid4()}/snapshot.tar.gz",
    )
    db_session.add(version)
    db_session.flush()
    return project, version


def test_resolve_finding_neo4j_target_prefers_job_runtime_metadata(db_session) -> None:
    project, version = _seed_finding_scope(db_session)
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        payload={},
        result_summary={
            "neo4j_runtime": {
                "uri": "bolt://job-scoped-neo4j:17687",
                "database": "scan_job_graph",
            }
        },
    )
    db_session.add(job)
    db_session.flush()

    finding = Finding(
        project_id=project.id,
        version_id=version.id,
        job_id=job.id,
        rule_key="any_any_xss",
        severity="HIGH",
        status="OPEN",
        has_path=True,
        source_file="src/Main.java",
        source_line=1,
        sink_file="src/Main.java",
        sink_line=2,
        evidence_json={},
    )
    db_session.add(finding)
    db_session.commit()

    target = resolve_finding_neo4j_target(db=db_session, finding=finding)

    assert target["uri"] == "bolt://job-scoped-neo4j:17687"
    assert target["database"] == "scan_job_graph"


def test_resolve_finding_neo4j_target_falls_back_to_settings(db_session) -> None:
    settings = get_settings()
    old_uri = settings.scan_external_neo4j_uri
    old_database = settings.scan_external_neo4j_database
    settings.scan_external_neo4j_uri = "bolt://127.0.0.1:7687"
    settings.scan_external_neo4j_database = "neo4j"
    try:
        project, version = _seed_finding_scope(db_session)
        job = Job(
            project_id=project.id,
            version_id=version.id,
            job_type=JobType.SCAN.value,
            status=JobStatus.SUCCEEDED.value,
            stage=JobStage.CLEANUP.value,
            payload={},
            result_summary={},
        )
        db_session.add(job)
        db_session.flush()

        finding = Finding(
            project_id=project.id,
            version_id=version.id,
            job_id=job.id,
            rule_key="any_any_xss",
            severity="HIGH",
            status="OPEN",
            has_path=True,
            source_file="src/Main.java",
            source_line=1,
            sink_file="src/Main.java",
            sink_line=2,
            evidence_json={},
        )
        db_session.add(finding)
        db_session.commit()

        target = resolve_finding_neo4j_target(db=db_session, finding=finding)
    finally:
        settings.scan_external_neo4j_uri = old_uri
        settings.scan_external_neo4j_database = old_database

    assert target["uri"] == "bolt://127.0.0.1:7687"
    assert target["database"] == "neo4j"


def test_query_finding_paths_prefers_persisted_path_rows(db_session) -> None:
    project, version = _seed_finding_scope(db_session)
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.SUCCEEDED.value,
        stage=JobStage.CLEANUP.value,
        payload={},
        result_summary={},
    )
    db_session.add(job)
    db_session.flush()

    finding = Finding(
        project_id=project.id,
        version_id=version.id,
        job_id=job.id,
        rule_key="any_any_xss",
        severity="HIGH",
        status="OPEN",
        has_path=True,
        path_length=1,
        source_file="src/Main.java",
        source_line=1,
        sink_file="src/Main.java",
        sink_line=2,
        evidence_json={},
    )
    db_session.add(finding)
    db_session.flush()

    path = FindingPath(finding_id=finding.id, path_order=0, path_length=1)
    db_session.add(path)
    db_session.flush()
    db_session.add_all(
        [
            FindingPathStep(
                finding_path_id=path.id,
                step_order=0,
                labels_json=["Source"],
                file_path="src/Main.java",
                line_no=1,
                func_name="source",
                code_snippet="request.getParameter('q')",
                node_ref="source-1",
            ),
            FindingPathStep(
                finding_path_id=path.id,
                step_order=1,
                labels_json=["Sink"],
                file_path="src/Main.java",
                line_no=2,
                func_name="sink",
                code_snippet="writer.println(q)",
                node_ref="sink-1",
            ),
        ]
    )
    db_session.commit()

    results = query_finding_paths(
        db=db_session, finding=finding, mode="shortest", limit=5
    )

    assert len(results) == 1
    assert results[0]["path_length"] == 1
    assert results[0]["steps"][0]["node_ref"] == "source-1"
    assert results[0]["steps"][1]["node_ref"] == "sink-1"
