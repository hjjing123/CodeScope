from __future__ import annotations

import uuid
from pathlib import Path

from app.config import get_settings
from app.api.v1.findings import _finding_payload
from app.models import (
    Finding,
    FindingPath,
    FindingPathEdge,
    FindingPathStep,
    Job,
    JobStage,
    JobStatus,
    JobType,
    Project,
    Version,
)
from app.services.finding_path_service import (
    load_finding_path_context,
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
                display_name="filepath",
                symbol_name="filepath",
                owner_method="source",
                node_kind="Var",
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
                display_name="cmdList",
                symbol_name="cmdList",
                owner_method="sink",
                node_kind="Var",
                code_snippet="writer.println(q)",
                node_ref="sink-1",
            ),
            FindingPathEdge(
                finding_path_id=path.id,
                edge_order=0,
                from_step_order=0,
                to_step_order=1,
                edge_type="ARG",
                label="参数传递",
                props_json={"argIndex": 0},
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
    assert results[0]["nodes"][0]["display_name"] == "filepath"
    assert results[0]["edges"][0]["edge_type"] == "ARG"
    assert results[0]["edges"][0]["from_step_id"] == 0
    assert results[0]["edges"][0]["to_step_id"] == 1


def test_query_finding_paths_reinfers_identifier_line_from_raw_props(
    db_session,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    project, version = _seed_finding_scope(db_session)
    backend_root = Path(__file__).resolve().parents[1]
    relative_root = f"storage/test-finding-path-{uuid.uuid4().hex}"
    source_root = backend_root / relative_root / str(version.id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  String run(String username) {\n"
        "    String templateString = username.trim();\n"
        "    return templateString;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = f"./{relative_root}"
    try:
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
            source_line=2,
            sink_file="src/Main.java",
            sink_line=3,
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
                    labels_json=["Var", "Reference"],
                    file_path="src/Main.java",
                    line_no=2,
                    func_name="run",
                    display_name="templateString",
                    symbol_name="templateString",
                    owner_method="run",
                    node_kind="Var",
                    code_snippet="",
                    node_ref="Var|/tmp/jimple2cpg-1/com/example/Main.class|-1|-1|id|templateString|com.example.Main.run:java.lang.String(java.lang.String)",
                    raw_props_json={
                        "file": "/tmp/jimple2cpg-1/com/example/Main.class",
                        "declKind": "Identifier",
                        "id": "Var|/tmp/jimple2cpg-1/com/example/Main.class|-1|-1|id|templateString|com.example.Main.run:java.lang.String(java.lang.String)",
                    },
                ),
                FindingPathStep(
                    finding_path_id=path.id,
                    step_order=1,
                    labels_json=["Call"],
                    file_path="src/Main.java",
                    line_no=4,
                    func_name="run",
                    display_name="trim",
                    symbol_name="trim",
                    owner_method="run",
                    node_kind="Call",
                    code_snippet="templateString.trim()",
                    node_ref="sink-1",
                    raw_props_json={},
                ),
            ]
        )
        db_session.commit()

        results = query_finding_paths(
            db=db_session, finding=finding, mode="shortest", limit=5
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        import shutil

        shutil.rmtree(backend_root / relative_root, ignore_errors=True)

    assert results[0]["steps"][0]["line"] == 3


def test_query_finding_paths_normalizes_compiled_paths_and_infers_lines(
    db_session, tmp_path: Path
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    project, version = _seed_finding_scope(db_session)
    source_file = (
        tmp_path
        / str(version.id)
        / "source"
        / "src"
        / "main"
        / "java"
        / "com"
        / "best"
        / "hello"
        / "controller"
        / "SSTI.java"
    )
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "package com.best.hello.controller;\n"
        "public class SSTI {\n"
        "  public String thymeleafVul(String lang) {\n"
        '    return "lang/" + lang;\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    compiled_file = (
        tmp_path
        / str(version.id)
        / "source"
        / "target"
        / "classes"
        / "com"
        / "best"
        / "hello"
        / "controller"
        / "SSTI.class"
    )
    compiled_file.parent.mkdir(parents=True, exist_ok=True)
    compiled_file.write_bytes(b"compiled")
    settings.snapshot_storage_root = str(tmp_path)
    try:
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

        raw_path = "/tmp/jimple2cpg-123/com/best/hello/controller/SSTI.class"
        finding = Finding(
            project_id=project.id,
            version_id=version.id,
            job_id=job.id,
            rule_key="spring_thymeleaf_ssti",
            severity="MED",
            status="OPEN",
            has_path=True,
            path_length=2,
            source_file=raw_path,
            source_line=-1,
            sink_file=raw_path,
            sink_line=-1,
            file_path=raw_path,
            line_start=-1,
            line_end=-1,
            evidence_json={},
        )
        db_session.add(finding)
        db_session.flush()

        path = FindingPath(finding_id=finding.id, path_order=0, path_length=2)
        db_session.add(path)
        db_session.flush()
        db_session.add_all(
            [
                FindingPathStep(
                    finding_path_id=path.id,
                    step_order=0,
                    labels_json=["Method"],
                    file_path=raw_path,
                    line_no=-1,
                    func_name="thymeleafVul",
                    code_snippet=None,
                    node_ref=(
                        "Method|/tmp/jimple2cpg-123/com/best/hello/controller/SSTI.class"
                        "|-1|-1|com.best.hello.controller.SSTI.thymeleafVul:java.lang.String(java.lang.String)"
                    ),
                )
            ]
        )
        db_session.commit()

        results = query_finding_paths(
            db=db_session, finding=finding, mode="shortest", limit=5
        )
        payload = _finding_payload(finding)
        context = load_finding_path_context(db=db_session, finding=finding, step_id=0)
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert (
        results[0]["steps"][0]["file"]
        == "src/main/java/com/best/hello/controller/SSTI.java"
    )
    assert results[0]["steps"][0]["line"] == 3
    assert payload.file_path == "src/main/java/com/best/hello/controller/SSTI.java"
    assert payload.line_start is None
    assert context["file"] == "src/main/java/com/best/hello/controller/SSTI.java"
    assert context["line"] == 3


def test_load_finding_path_context_supports_node_only_pom_dependency(
    db_session,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    project, version = _seed_finding_scope(db_session)
    backend_root = Path(__file__).resolve().parents[1]
    relative_root = f"storage/test-node-only-context-{uuid.uuid4().hex}"
    source_root = backend_root / relative_root / str(version.id) / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "pom.xml").write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>com.thoughtworks.xstream</groupId>\n"
        "      <artifactId>xstream</artifactId>\n"
        "      <version>1.4.10</version>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = f"./{relative_root}"
    try:
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
            rule_key="pom_log4j_codei",
            vuln_type="RCE",
            severity="MED",
            status="OPEN",
            has_path=False,
            file_path="pom.xml",
            line_start=3,
            sink_file="pom.xml",
            sink_line=3,
            evidence_json={
                "match_kind": "node",
                "labels": ["PomDependency"],
                "node_ref": "PomDependency|pom.xml|3|1|com.thoughtworks.xstream:xstream:1.4.10",
            },
        )
        db_session.add(finding)
        db_session.commit()

        context = load_finding_path_context(
            db=db_session,
            finding=finding,
            step_id=0,
            before=2,
            after=4,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert context["file"] == "pom.xml"
    assert context["line"] == 3
    assert [item["text"] for item in context["highlight_ranges"]] == [
        "xstream",
        "1.4.10",
    ]


def test_load_finding_path_context_supports_node_only_properties_value(
    db_session,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    project, version = _seed_finding_scope(db_session)
    backend_root = Path(__file__).resolve().parents[1]
    relative_root = f"storage/test-node-only-properties-{uuid.uuid4().hex}"
    source_root = (
        backend_root
        / relative_root
        / str(version.id)
        / "source"
        / "src"
        / "main"
        / "resources"
    )
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "application.properties").write_text(
        "local.admin.name = admin\nlocal.admin.password = admin\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = f"./{relative_root}"
    try:
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
            rule_key="config_secret_hardcode",
            vuln_type="CUSTOM",
            severity="MED",
            status="OPEN",
            has_path=False,
            file_path="src/main/resources/application.properties",
            line_start=2,
            sink_file="src/main/resources/application.properties",
            sink_line=2,
            evidence_json={
                "match_kind": "node",
                "labels": ["PropertiesKeyValue"],
                "node_ref": "PropertiesKeyValue|application.properties|2|1|local.admin.password",
            },
        )
        db_session.add(finding)
        db_session.commit()

        context = load_finding_path_context(
            db=db_session,
            finding=finding,
            step_id=0,
            before=1,
            after=1,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert [item["text"] for item in context["highlight_ranges"]] == [
        "local.admin.password",
        "admin",
    ]
