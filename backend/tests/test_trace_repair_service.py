from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_java")

from app.config import get_settings
from app.services import trace_repair_service as trace_repair_module


def test_process_external_finding_candidate_repairs_structural_java_path(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  void upload(String imageType) {\n"
        '    String filePath = "upload/" + imageType;\n'
        "    transferTo(new File(filePath));\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding = {
            "rule_key": "any_any_upload",
            "file_path": "src/Main.java",
            "line_start": 4,
            "source_file": "src/Main.java",
            "source_line": 2,
            "sink_file": "src/Main.java",
            "sink_line": 4,
            "paths": [
                {
                    "nodes": [
                        {
                            "node_id": 0,
                            "labels": ["Var", "Argument"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "imageType",
                            "symbol_name": "imageType",
                            "owner_method": "upload",
                            "node_kind": "Var",
                            "node_ref": "source-1",
                            "raw_props": {"id": "source-1", "name": "imageType"},
                        },
                        {
                            "node_id": 1,
                            "labels": ["Method"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "upload",
                            "node_ref": "method-1",
                            "raw_props": {"id": "method-1"},
                        },
                        {
                            "node_id": 2,
                            "labels": ["Call"],
                            "file": "src/Main.java",
                            "line": 4,
                            "display_name": "transferTo",
                            "symbol_name": "transferTo",
                            "owner_method": "upload",
                            "node_kind": "Call",
                            "node_ref": "sink-1",
                            "raw_props": {"id": "sink-1", "name": "transferTo"},
                        },
                    ],
                    "edges": [
                        {
                            "edge_type": "ARG",
                            "from_node_ref": "source-1",
                            "to_node_ref": "method-1",
                            "props_json": {"argIndex": -1},
                        },
                        {
                            "edge_type": "HAS_CALL",
                            "from_node_ref": "method-1",
                            "to_node_ref": "sink-1",
                            "props_json": {},
                        },
                    ],
                }
            ],
        }

        repaired = trace_repair_module.process_external_finding_candidate(
            job=SimpleNamespace(version_id=version_id),
            raw_finding=finding,
            seen_fingerprints=set(),
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert repaired is not None
    assert repaired["has_path"] is True
    assert repaired["evidence"]["repair_status"] == "java_repaired"
    assert [edge["edge_type"] for edge in repaired["paths"][0]["edges"]] == [
        "SRC_FLOW",
        "ARG",
    ]
    assert [node["display_name"] for node in repaired["paths"][0]["nodes"]] == [
        "imageType",
        "filePath",
        "transferTo",
    ]


def test_process_external_finding_candidate_drops_low_value_predicate_sink(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  void upload(String imageType) {\n"
        '    if ("single".equals(imageType)) {\n'
        '      System.out.println("ok");\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding = {
            "rule_key": "any_any_upload",
            "file_path": "src/Main.java",
            "line_start": 3,
            "source_file": "src/Main.java",
            "source_line": 2,
            "sink_file": "src/Main.java",
            "sink_line": 3,
            "paths": [
                {
                    "nodes": [
                        {
                            "node_id": 0,
                            "labels": ["Var", "Argument"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "imageType",
                            "symbol_name": "imageType",
                            "owner_method": "upload",
                            "node_kind": "Var",
                            "node_ref": "source-1",
                            "raw_props": {"id": "source-1", "name": "imageType"},
                        },
                        {
                            "node_id": 1,
                            "labels": ["Method"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "upload",
                            "node_ref": "method-1",
                            "raw_props": {"id": "method-1"},
                        },
                        {
                            "node_id": 2,
                            "labels": ["Call"],
                            "file": "src/Main.java",
                            "line": 3,
                            "display_name": "equals",
                            "symbol_name": "equals",
                            "owner_method": "upload",
                            "node_kind": "Call",
                            "node_ref": "sink-1",
                            "raw_props": {"id": "sink-1", "name": "equals"},
                        },
                    ],
                    "edges": [
                        {
                            "edge_type": "ARG",
                            "from_node_ref": "source-1",
                            "to_node_ref": "method-1",
                            "props_json": {"argIndex": -1},
                        },
                        {
                            "edge_type": "HAS_CALL",
                            "from_node_ref": "method-1",
                            "to_node_ref": "sink-1",
                            "props_json": {},
                        },
                    ],
                }
            ],
        }

        repaired = trace_repair_module.process_external_finding_candidate(
            job=SimpleNamespace(version_id=version_id),
            raw_finding=finding,
            seen_fingerprints=set(),
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert repaired is not None
    assert repaired["has_path"] is False
    assert repaired["paths"] == []
    assert repaired["evidence"]["repair_status"] == "downgraded_no_path"


def test_process_external_finding_candidate_downgrades_broken_structural_path(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  void run(String input) {\n"
        '    String safe = "ok";\n'
        "    openConnection(safe);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding = {
            "rule_key": "any_any_ssrf",
            "file_path": "src/Main.java",
            "line_start": 4,
            "source_file": "src/Main.java",
            "source_line": 2,
            "sink_file": "src/Main.java",
            "sink_line": 4,
            "paths": [
                {
                    "nodes": [
                        {
                            "node_id": 0,
                            "labels": ["Var", "Argument"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "input",
                            "symbol_name": "input",
                            "owner_method": "run",
                            "node_kind": "Var",
                            "node_ref": "source-1",
                            "raw_props": {"id": "source-1", "name": "input"},
                        },
                        {
                            "node_id": 1,
                            "labels": ["Method"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "run",
                            "node_ref": "method-1",
                            "raw_props": {"id": "method-1"},
                        },
                        {
                            "node_id": 2,
                            "labels": ["Call"],
                            "file": "src/Main.java",
                            "line": 4,
                            "display_name": "openConnection",
                            "symbol_name": "openConnection",
                            "owner_method": "run",
                            "node_kind": "Call",
                            "node_ref": "sink-1",
                            "raw_props": {"id": "sink-1", "name": "openConnection"},
                        },
                    ],
                    "edges": [
                        {
                            "edge_type": "ARG",
                            "from_node_ref": "source-1",
                            "to_node_ref": "method-1",
                            "props_json": {"argIndex": -1},
                        },
                        {
                            "edge_type": "HAS_CALL",
                            "from_node_ref": "method-1",
                            "to_node_ref": "sink-1",
                            "props_json": {},
                        },
                    ],
                }
            ],
        }

        repaired = trace_repair_module.process_external_finding_candidate(
            job=SimpleNamespace(version_id=version_id),
            raw_finding=finding,
            seen_fingerprints=set(),
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert repaired is not None
    assert repaired["has_path"] is False
    assert repaired["paths"] == []
    assert repaired["evidence"]["repair_status"] == "downgraded_no_path"


def test_process_external_finding_candidate_dedupes_by_canonical_fingerprint(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  void exec(String input) {\n"
        "    Runtime.getRuntime().exec(input);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        finding_a = {
            "rule_key": "any_any_cmdi",
            "file_path": "src/Main.java",
            "line_start": 3,
            "source_file": "src/Main.java",
            "source_line": 2,
            "sink_file": "src/Main.java",
            "sink_line": 3,
            "paths": [
                {
                    "nodes": [
                        {
                            "labels": ["Var", "Argument"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "input",
                            "symbol_name": "input",
                            "owner_method": "exec",
                            "node_kind": "Var",
                            "node_ref": "source-1",
                            "raw_props": {"id": "source-1", "name": "input"},
                        },
                        {
                            "labels": ["Call"],
                            "file": "src/Main.java",
                            "line": 3,
                            "display_name": "exec",
                            "symbol_name": "exec",
                            "owner_method": "exec",
                            "node_kind": "Call",
                            "node_ref": "sink-1",
                            "raw_props": {"id": "sink-1", "name": "exec"},
                        },
                    ],
                    "edges": [
                        {
                            "edge_type": "HAS_CALL",
                            "from_node_ref": "source-1",
                            "to_node_ref": "sink-1",
                            "props_json": {},
                        }
                    ],
                }
            ],
        }
        finding_b = {
            **finding_a,
            "paths": [
                {
                    "nodes": [
                        finding_a["paths"][0]["nodes"][0],
                        {
                            "labels": ["Method"],
                            "file": "src/Main.java",
                            "line": 2,
                            "display_name": "exec",
                            "node_ref": "method-1",
                            "raw_props": {"id": "method-1"},
                        },
                        finding_a["paths"][0]["nodes"][1],
                    ],
                    "edges": [
                        {
                            "edge_type": "ARG",
                            "from_node_ref": "source-1",
                            "to_node_ref": "method-1",
                            "props_json": {"argIndex": -1},
                        },
                        {
                            "edge_type": "HAS_CALL",
                            "from_node_ref": "method-1",
                            "to_node_ref": "sink-1",
                            "props_json": {},
                        },
                    ],
                }
            ],
        }
        seen: set[str] = set()

        first = trace_repair_module.process_external_finding_candidate(
            job=SimpleNamespace(version_id=version_id),
            raw_finding=finding_a,
            seen_fingerprints=seen,
        )
        second = trace_repair_module.process_external_finding_candidate(
            job=SimpleNamespace(version_id=version_id),
            raw_finding=finding_b,
            seen_fingerprints=seen,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert first is not None
    assert second is None
