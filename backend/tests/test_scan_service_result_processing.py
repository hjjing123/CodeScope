from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models import JobStepStatus
from app.services import artifact_service as artifact_service_module
from app.services import scan_service as scan_service_module


def test_attach_code_contexts_and_ai_payloads_use_snapshot_source(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        '  String input = request.getParameter("id");\n'
        '  String sql = "select * from user where id=" + input;\n'
        "  statement.executeQuery(sql);\n"
        "}\n",
        encoding="utf-8",
    )

    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding_drafts = [
            {
                "rule_key": "any_any_sqli",
                "severity": "HIGH",
                "vuln_type": "SQLI",
                "file_path": "src/Main.java",
                "line_start": 3,
                "line_end": 4,
                "source": {"file": "src/Main.java", "line": 2},
                "sink": {"file": "src/Main.java", "line": 4},
                "evidence": {"items": ["request.id", "executeQuery"]},
                "trace_summary": "request -> sql -> executeQuery",
                "has_path": True,
                "path_length": 3,
            }
        ]

        enriched = scan_service_module._attach_code_contexts(
            job=SimpleNamespace(version_id=version_id),
            finding_drafts=finding_drafts,
        )
        assert enriched[0]["code_context"]["focus"]["file_path"] == "src/Main.java"
        assert "3:   String sql" in enriched[0]["code_context"]["focus"]["snippet"]

        llm_enriched = scan_service_module._attach_ai_payloads(enriched)
        payload = llm_enriched[0]["llm_payload"]
        assert payload["why_flagged"]
        assert payload["code_context"]["focus"]
        assert "Code:" in llm_enriched[0]["llm_prompt_block"]
        assert "Reason:" in llm_enriched[0]["llm_prompt_block"]
    finally:
        settings.snapshot_storage_root = old_snapshot_root


def test_attach_code_contexts_supports_relative_snapshot_root_without_cwd_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    backend_root = Path(scan_service_module.__file__).resolve().parents[2]
    relative_root = f"storage/test-snapshots-{uuid.uuid4().hex}"
    version_id = uuid.uuid4()
    source_root = backend_root / relative_root / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        '  String input = request.getParameter("id");\n'
        '  String sql = "select * from user where id=" + input;\n'
        "}\n",
        encoding="utf-8",
    )

    original_resolve = Path.resolve

    def _resolve_fail_on_relative(self, *args, **kwargs):
        if not self.is_absolute():
            raise FileNotFoundError("cwd missing")
        return original_resolve(self, *args, **kwargs)

    settings.snapshot_storage_root = f"./{relative_root}"
    monkeypatch.setattr(Path, "resolve", _resolve_fail_on_relative)
    try:
        finding_drafts = [
            {
                "rule_key": "any_any_sqli",
                "severity": "HIGH",
                "vuln_type": "SQLI",
                "file_path": "src/Main.java",
                "line_start": 3,
                "line_end": 3,
                "source": {"file": "src/Main.java", "line": 2},
                "sink": {"file": "src/Main.java", "line": 3},
                "evidence": {},
                "trace_summary": "request -> sql",
                "has_path": True,
                "path_length": 1,
            }
        ]
        enriched = scan_service_module._attach_code_contexts(
            job=SimpleNamespace(version_id=version_id),
            finding_drafts=finding_drafts,
        )
    finally:
        monkeypatch.setattr(Path, "resolve", original_resolve)
        settings.snapshot_storage_root = old_snapshot_root
        shutil.rmtree(backend_root / relative_root, ignore_errors=True)

    assert enriched[0]["code_context"]["focus"]["file_path"] == "src/Main.java"


def test_run_stub_scan_emits_snapshot_location_when_source_exists(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "README.md").write_text("hello\nworld\n", encoding="utf-8")

    settings.snapshot_storage_root = str(tmp_path)
    try:
        result = scan_service_module._run_stub_scan(
            job=SimpleNamespace(
                id=uuid.uuid4(),
                version_id=version_id,
                payload={"rule_keys": ["any_any_xss"]},
            )
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert result.findings
    first = result.findings[0]
    assert first["file_path"] == "README.md"
    assert first["line_start"] == 1
    assert first["sink_line"] >= 1


def test_write_scan_result_archive_persists_job_summary(tmp_path: Path) -> None:
    settings = get_settings()
    old_log_root = settings.scan_log_root
    settings.scan_log_root = str(tmp_path / "job-logs")
    job_id = uuid.uuid4()
    try:
        archive = scan_service_module._write_scan_result_archive(
            job=SimpleNamespace(
                id=job_id,
                project_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                job_type="SCAN",
                status="SUCCEEDED",
                stage="CLEANUP",
                failure_code=None,
                failure_stage=None,
                failure_category=None,
                failure_hint=None,
                started_at=None,
                finished_at=None,
                result_summary={"total_findings": 2, "partial_failures": []},
            )
        )
        archive_path = Path(archive["path"])
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
    finally:
        settings.scan_log_root = old_log_root

    assert archive_path.exists()
    assert payload["job_id"] == str(job_id)
    assert payload["status"] == "SUCCEEDED"
    assert payload["result_summary"]["total_findings"] == 2


def test_normalize_external_finding_payload_preserves_graph_shape() -> None:
    version_id = uuid.uuid4()
    raw_finding = {
        "rule_key": "any_any_cmdi",
        "file_path": "src/Main.java",
        "line_start": 12,
        "source_file": "src/Main.java",
        "source_line": 10,
        "sink_file": "src/Main.java",
        "sink_line": 12,
        "paths": [
            {
                "nodes": [
                    {
                        "node_id": 7,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 10,
                        "func_name": "processbuilderVul",
                        "display_name": "filepath",
                        "symbol_name": "filepath",
                        "owner_method": "processbuilderVul",
                        "type_name": "String",
                        "node_kind": "Var",
                        "code_snippet": "String filepath",
                        "node_ref": "source-1",
                        "raw_props": {"kind": "Var", "name": "filepath"},
                    },
                    {
                        "node_id": 9,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 12,
                        "func_name": "processbuilderVul",
                        "display_name": "cmdList",
                        "symbol_name": "cmdList",
                        "owner_method": "processbuilderVul",
                        "type_name": "String[]",
                        "node_kind": "Var",
                        "code_snippet": 'String[] cmdList = {"sh", "-c", "ls -l " + filepath};',
                        "node_ref": "sink-1",
                        "raw_props": {"kind": "Var", "name": "cmdList"},
                    },
                ],
                "edges": [
                    {
                        "edge_type": "ARG",
                        "from_node_ref": "source-1",
                        "to_node_ref": "sink-1",
                        "props_json": {"argIndex": 0},
                    }
                ],
            }
        ],
    }

    normalized = scan_service_module._normalize_external_finding_payload(
        version_id=version_id,
        raw_finding=raw_finding,
    )

    assert normalized["paths"][0]["path_id"] == 0
    assert normalized["paths"][0]["nodes"][0]["display_name"] == "filepath"
    assert normalized["paths"][0]["steps"][1]["display_name"] == "cmdList"
    assert normalized["paths"][0]["edges"][0]["edge_type"] == "ARG"
    assert normalized["paths"][0]["edges"][0]["from_step_id"] == 0
    assert normalized["paths"][0]["edges"][0]["to_step_id"] == 1


def test_normalize_external_finding_payload_supports_relative_snapshot_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    backend_root = Path(scan_service_module.__file__).resolve().parents[2]
    relative_root = f"storage/test-norm-{uuid.uuid4().hex}"
    version_id = uuid.uuid4()
    source_root = backend_root / relative_root / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        '  String input = request.getParameter("id");\n'
        "  Runtime.getRuntime().exec(input);\n"
        "}\n",
        encoding="utf-8",
    )

    original_resolve = Path.resolve

    def _resolve_fail_on_relative(self, *args, **kwargs):
        if not self.is_absolute():
            raise FileNotFoundError("cwd missing")
        return original_resolve(self, *args, **kwargs)

    raw_finding = {
        "rule_key": "any_any_cmdi",
        "file_path": "src/Main.java",
        "line_start": 3,
        "source_file": "src/Main.java",
        "source_line": 2,
        "sink_file": "src/Main.java",
        "sink_line": 3,
        "paths": [
            {
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var", "Argument"],
                        "file": "src/Main.java",
                        "line": 2,
                        "func_name": "exec",
                        "display_name": "input",
                        "node_kind": "Var",
                        "code_snippet": 'String input = request.getParameter("id")',
                        "node_ref": "source-1",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 3,
                        "func_name": "exec",
                        "display_name": "exec",
                        "node_kind": "Call",
                        "code_snippet": "Runtime.getRuntime().exec(input)",
                        "node_ref": "sink-1",
                    },
                ]
            }
        ],
    }

    settings.snapshot_storage_root = f"./{relative_root}"
    monkeypatch.setattr(Path, "resolve", _resolve_fail_on_relative)
    try:
        normalized = scan_service_module._normalize_external_finding_payload(
            version_id=version_id,
            raw_finding=raw_finding,
        )
    finally:
        monkeypatch.setattr(Path, "resolve", original_resolve)
        settings.snapshot_storage_root = old_snapshot_root
        shutil.rmtree(backend_root / relative_root, ignore_errors=True)

    assert normalized["source_file"] == "src/Main.java"
    assert normalized["sink_file"] == "src/Main.java"
    assert normalized["paths"][0]["steps"][0]["file"] == "src/Main.java"


def test_refine_external_finding_paths_with_runtime_replaces_structural_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(id=uuid.uuid4(), version_id=uuid.uuid4())
    finding_payload = {
        "rule_key": "any_xstream_deserialization",
        "file_path": "src/Main.java",
        "line_start": 23,
        "line_end": 23,
        "source_file": "src/Main.java",
        "source_line": 21,
        "sink_file": "src/Main.java",
        "sink_line": 23,
        "has_path": True,
        "path_length": 2,
        "evidence": {"match_kind": "path"},
        "paths": [
            {
                "path_id": 0,
                "path_length": 2,
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "source-1",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Method"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "vul",
                        "node_ref": "method-1",
                    },
                    {
                        "step_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "fromXML",
                        "node_ref": "sink-1",
                    },
                ],
                "nodes": [
                    {
                        "node_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "source-1",
                        "raw_props": {"id": "src-node"},
                    },
                    {
                        "node_id": 1,
                        "labels": ["Method"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "vul",
                        "node_ref": "method-1",
                        "raw_props": {"id": "method-node"},
                    },
                    {
                        "node_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "fromXML",
                        "node_ref": "sink-1",
                        "raw_props": {"id": "sink-node"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": 0,
                        "edge_type": "ARG",
                        "from_step_id": 0,
                        "to_step_id": 1,
                        "props_json": {"argIndex": -1},
                    },
                    {
                        "edge_id": 1,
                        "edge_type": "HAS_CALL",
                        "from_step_id": 1,
                        "to_step_id": 2,
                        "props_json": {},
                    },
                ],
            }
        ],
    }

    monkeypatch.setattr(
        scan_service_module,
        "_load_external_runtime_metadata",
        lambda **kwargs: {"uri": "bolt://127.0.0.1:7687", "database": "neo4j"},
    )
    monkeypatch.setattr(
        scan_service_module,
        "query_runtime_semantic_paths_by_node_refs",
        lambda **kwargs: [
            {
                "path_id": 0,
                "path_length": 2,
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var", "Param"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "src-node",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Var", "Identifier"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "content",
                        "node_ref": "id-node",
                    },
                    {
                        "step_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "fromXML",
                        "node_ref": "sink-node",
                    },
                ],
                "nodes": [
                    {
                        "node_id": 0,
                        "labels": ["Var", "Param"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "src-node",
                        "raw_props": {"id": "src-node"},
                    },
                    {
                        "node_id": 1,
                        "labels": ["Var", "Identifier"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "content",
                        "node_ref": "id-node",
                        "raw_props": {"id": "id-node"},
                    },
                    {
                        "node_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "fromXML",
                        "node_ref": "sink-node",
                        "raw_props": {"id": "sink-node"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": 0,
                        "edge_type": "REF",
                        "from_step_id": 0,
                        "to_step_id": 1,
                        "props_json": {},
                    },
                    {
                        "edge_id": 1,
                        "edge_type": "ARG",
                        "from_step_id": 1,
                        "to_step_id": 2,
                        "props_json": {"argIndex": 0},
                    },
                ],
            }
        ],
    )

    refined = scan_service_module._refine_external_finding_paths_with_runtime(
        job=job,
        finding_payload=finding_payload,
    )

    assert refined["paths"][0]["edges"][0]["edge_type"] == "REF"
    assert refined["paths"][0]["steps"][1]["display_name"] == "content"
    assert refined["source_line"] == 21
    assert refined["sink_line"] == 23
    assert refined["path_length"] == 2
    assert refined["evidence"]["edge_types"] == ["REF", "ARG"]


def test_refine_external_finding_paths_with_runtime_keeps_raw_path_without_semantic_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(id=uuid.uuid4(), version_id=uuid.uuid4())
    finding_payload = {
        "rule_key": "any_any_ssrf",
        "file_path": "src/Main.java",
        "line_start": 23,
        "line_end": 23,
        "source_file": "src/Main.java",
        "source_line": 21,
        "sink_file": "src/Main.java",
        "sink_line": 23,
        "has_path": True,
        "path_length": 2,
        "evidence": {"match_kind": "path", "edge_types": ["ARG", "HAS_CALL"]},
        "paths": [
            {
                "path_id": 0,
                "path_length": 2,
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "source-1",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Method"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "vul",
                        "node_ref": "method-1",
                    },
                    {
                        "step_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "openConnection",
                        "node_ref": "sink-1",
                    },
                ],
                "nodes": [
                    {
                        "node_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "source-1",
                        "raw_props": {"id": "src-node"},
                    },
                    {
                        "node_id": 1,
                        "labels": ["Method"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "vul",
                        "node_ref": "method-1",
                        "raw_props": {"id": "method-node"},
                    },
                    {
                        "node_id": 2,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "openConnection",
                        "node_ref": "sink-1",
                        "raw_props": {"id": "sink-node"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": 0,
                        "edge_type": "ARG",
                        "from_step_id": 0,
                        "to_step_id": 1,
                        "props_json": {"argIndex": -1},
                    },
                    {
                        "edge_id": 1,
                        "edge_type": "HAS_CALL",
                        "from_step_id": 1,
                        "to_step_id": 2,
                        "props_json": {},
                    },
                ],
            }
        ],
    }

    monkeypatch.setattr(
        scan_service_module,
        "_load_external_runtime_metadata",
        lambda **kwargs: {"uri": "bolt://127.0.0.1:7687", "database": "neo4j"},
    )
    monkeypatch.setattr(
        scan_service_module,
        "query_runtime_semantic_paths_by_node_refs",
        lambda **kwargs: [
            {
                "path_id": 0,
                "path_length": 1,
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "src-node",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "openConnection",
                        "node_ref": "sink-node",
                    },
                ],
                "nodes": [
                    {
                        "node_id": 0,
                        "labels": ["Var"],
                        "file": "src/Main.java",
                        "line": 21,
                        "display_name": "content",
                        "node_ref": "src-node",
                        "raw_props": {"id": "src-node"},
                    },
                    {
                        "node_id": 1,
                        "labels": ["Call"],
                        "file": "src/Main.java",
                        "line": 23,
                        "display_name": "openConnection",
                        "node_ref": "sink-node",
                        "raw_props": {"id": "sink-node"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": 0,
                        "edge_type": "ARG",
                        "from_step_id": 0,
                        "to_step_id": 1,
                        "props_json": {"argIndex": 0},
                    }
                ],
            }
        ],
    )

    refined = scan_service_module._refine_external_finding_paths_with_runtime(
        job=job,
        finding_payload=finding_payload,
    )

    assert refined["paths"][0]["steps"][1]["display_name"] == "vul"
    assert [edge["edge_type"] for edge in refined["paths"][0]["edges"]] == [
        "ARG",
        "HAS_CALL",
    ]
    assert refined["evidence"]["edge_types"] == ["ARG", "HAS_CALL"]


def test_build_scan_progress_payload_caps_at_99_until_job_terminal() -> None:
    steps = [
        SimpleNamespace(step_key="prepare", status=JobStepStatus.SUCCEEDED.value),
        SimpleNamespace(step_key="cleanup", status=JobStepStatus.SUCCEEDED.value),
    ]

    running_payload = scan_service_module.build_scan_progress_payload(
        steps=steps,
        job_status="RUNNING",
    )
    succeeded_payload = scan_service_module.build_scan_progress_payload(
        steps=steps,
        job_status="SUCCEEDED",
    )

    assert running_payload["percent"] == 99
    assert running_payload["current_step"] == "cleanup"
    assert succeeded_payload["percent"] == 100


def test_release_scan_workspace_does_not_depend_on_path_resolve(
    tmp_path: Path, monkeypatch
) -> None:
    settings = get_settings()
    old_workspace_root = settings.scan_workspace_root
    workspace_root = tmp_path / "scan-root"
    job_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_dir = workspace_root / str(project_id) / str(job_id) / "external"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "marker.txt").write_text("ok\n", encoding="utf-8")

    original_resolve = Path.resolve

    def _boom_resolve(self, *args, **kwargs):
        raise FileNotFoundError("resolve boom")

    settings.scan_workspace_root = str(workspace_root)
    monkeypatch.setattr(Path, "resolve", _boom_resolve)
    try:
        summary = scan_service_module._release_scan_workspace(
            job=SimpleNamespace(project_id=project_id, id=job_id)
        )
    finally:
        monkeypatch.setattr(Path, "resolve", original_resolve)
        settings.scan_workspace_root = old_workspace_root

    assert summary["workspace_released"] is True
    assert not workspace_dir.exists()


def test_release_scan_workspace_does_not_depend_on_os_abspath(
    tmp_path: Path, monkeypatch
) -> None:
    settings = get_settings()
    old_workspace_root = settings.scan_workspace_root
    workspace_root = tmp_path / "scan-root"
    job_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_dir = workspace_root / str(project_id) / str(job_id) / "external"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "marker.txt").write_text("ok\n", encoding="utf-8")

    def _boom_abspath(_value: str) -> str:
        raise FileNotFoundError("cwd missing")

    settings.scan_workspace_root = str(workspace_root)
    monkeypatch.setattr(scan_service_module.os.path, "abspath", _boom_abspath)
    try:
        summary = scan_service_module._release_scan_workspace(
            job=SimpleNamespace(project_id=project_id, id=job_id)
        )
    finally:
        settings.scan_workspace_root = old_workspace_root

    assert summary["workspace_released"] is True
    assert not workspace_dir.exists()


def test_release_scan_workspace_refuses_path_outside_root(
    tmp_path: Path, monkeypatch
) -> None:
    settings = get_settings()
    old_workspace_root = settings.scan_workspace_root
    workspace_root = tmp_path / "scan-root"
    outside_dir = tmp_path / "outside" / "external"
    outside_dir.mkdir(parents=True, exist_ok=True)
    (outside_dir / "marker.txt").write_text("ok\n", encoding="utf-8")

    settings.scan_workspace_root = str(workspace_root)
    monkeypatch.setattr(
        scan_service_module,
        "_scan_external_workspace_dir",
        lambda **kwargs: outside_dir,
    )
    try:
        summary = scan_service_module._release_scan_workspace(
            job=SimpleNamespace(project_id=uuid.uuid4(), id=uuid.uuid4())
        )
    finally:
        settings.scan_workspace_root = old_workspace_root

    assert summary["workspace_released"] is False
    assert "outside configured root" in str(summary["workspace_cleanup_error"])
    assert outside_dir.exists()


def test_list_job_artifacts_includes_scan_result_archive(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    old_log_root = settings.scan_log_root
    settings.snapshot_storage_root = str(tmp_path / "snapshots")
    settings.scan_log_root = str(tmp_path / "job-logs")
    job_id = uuid.uuid4()
    version_id = uuid.uuid4()
    try:
        log_dir = Path(settings.scan_log_root) / str(job_id)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "prepare.log").write_text("prepare\n", encoding="utf-8")
        (log_dir / "scan_result.json").write_text("{}\n", encoding="utf-8")

        snapshot_dir = Path(settings.snapshot_storage_root) / str(version_id)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "snapshot.tar.gz").write_bytes(b"snapshot")

        items = artifact_service_module.list_job_artifacts(
            job=SimpleNamespace(id=job_id, version_id=version_id, result_summary={})
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        settings.scan_log_root = old_log_root

    artifact_types = {item["artifact_type"] for item in items}
    assert "LOG" in artifact_types
    assert "ARCHIVE" in artifact_types
    assert "SNAPSHOT" in artifact_types


def test_cleanup_external_neo4j_database_drops_job_scoped_database(
    monkeypatch,
) -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = True
    captured: dict[str, object] = {}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    try:
        monkeypatch.setattr(
            scan_service_module,
            "drop_database_if_exists",
            lambda **kwargs: captured.update(kwargs),
        )
        monkeypatch.setattr(
            scan_service_module,
            "_load_external_runtime_metadata",
            lambda **kwargs: {},
        )
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=job,
            result_summary={
                "neo4j_runtime": {
                    "uri": "bolt://127.0.0.1:17687",
                    "database": "scan_job_123",
                }
            },
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert captured["uri"] == "bolt://127.0.0.1:17687"
    assert captured["database"] == "scan_job_123"
    assert summary["cleanup_attempted"] is True
    assert summary["cleanup_succeeded"] is True


def test_cleanup_external_neo4j_database_skips_protected_database() -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = True
    try:
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=SimpleNamespace(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
            ),
            result_summary={"neo4j_runtime": {"database": "neo4j"}},
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert summary["cleanup_attempted"] is False
    assert summary["cleanup_succeeded"] is False
    assert summary["cleanup_skipped_reason"] == "protected_database"


def test_cleanup_external_neo4j_database_cleans_ephemeral_runtime_even_when_db_cleanup_disabled(
    monkeypatch,
) -> None:
    settings = get_settings()
    old_cleanup_enabled = settings.scan_external_neo4j_cleanup_enabled
    settings.scan_external_neo4j_cleanup_enabled = False
    captured: dict[str, object] = {}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    try:
        monkeypatch.setattr(
            scan_service_module,
            "cleanup_ephemeral_runtime_resources",
            lambda **kwargs: (
                captured.update(kwargs)
                or {
                    "container_cleanup_attempted": True,
                    "container_cleanup_succeeded": True,
                    "data_cleanup_attempted": True,
                    "data_cleanup_succeeded": True,
                    "network_cleanup_attempted": True,
                    "network_cleanup_succeeded": True,
                }
            ),
        )
        monkeypatch.setattr(
            scan_service_module,
            "_load_external_runtime_metadata",
            lambda **kwargs: {},
        )
        summary = scan_service_module._cleanup_external_neo4j_database(
            job=job,
            result_summary={
                "neo4j_runtime": {
                    "restart_mode": "docker_ephemeral",
                    "container_name": "neo4j-job-1",
                    "data_mount": "/tmp/neo4j-job-1",
                    "network": "codescope-net-job-1",
                    "network_created_by_job": True,
                }
            },
        )
    finally:
        settings.scan_external_neo4j_cleanup_enabled = old_cleanup_enabled

    assert captured["container_name"] == "neo4j-job-1"
    assert captured["data_mount"] == "/tmp/neo4j-job-1"
    assert captured["network_name"] == "codescope-net-job-1"
    assert captured["cleanup_network"] is True
    assert summary["cleanup_attempted"] is True
    assert summary["cleanup_succeeded"] is True
    assert summary["container_cleanup_succeeded"] is True
    assert summary["data_cleanup_succeeded"] is True
    assert summary["network_cleanup_succeeded"] is True
