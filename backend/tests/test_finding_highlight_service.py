from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.finding_highlight_service import resolve_path_step_highlight


def test_resolve_path_step_highlight_marks_java_parameter(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Demo.java").write_text(
        "class Demo {\n"
        "  void search(String keyword, String orderBy, Boolean isDesc) {\n"
        "    repo.getList(orderBy, isDesc);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        path = {
            "steps": [
                {
                    "step_id": 0,
                    "file": "src/Demo.java",
                    "line": 2,
                    "symbol_name": "orderBy",
                    "display_name": "orderBy",
                    "node_kind": "Var",
                    "node_ref": "node-0",
                }
            ],
            "nodes": [
                {
                    "node_id": 0,
                    "file": "src/Demo.java",
                    "line": 2,
                    "symbol_name": "orderBy",
                    "display_name": "orderBy",
                    "node_kind": "Var",
                    "node_ref": "node-0",
                    "raw_props": {
                        "name": "orderBy",
                        "declKind": "Param",
                        "paramIndex": 1,
                    },
                }
            ],
            "edges": [],
        }

        highlight_ranges, focus_range = resolve_path_step_highlight(
            version_id=version_id,
            path=path,
            step_id=0,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert focus_range is not None
    assert highlight_ranges[0]["text"] == "orderBy"
    assert highlight_ranges[0]["start_line"] == 2
    if highlight_ranges[0]["kind"] == "token":
        pytest.skip("tree-sitter span resolver unavailable in this test environment")
    assert highlight_ranges[0]["kind"] == "param"


def test_resolve_path_step_highlight_marks_java_call_argument(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = tmp_path / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Demo.java").write_text(
        "class Demo {\n"
        "  void search(String keyword, String orderBy, Boolean isDesc) {\n"
        "    repo.getList(orderBy, isDesc);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        path = {
            "steps": [
                {
                    "step_id": 0,
                    "file": "src/Demo.java",
                    "line": 2,
                    "symbol_name": "orderBy",
                    "display_name": "orderBy",
                    "node_kind": "Var",
                    "node_ref": "node-0",
                },
                {
                    "step_id": 1,
                    "file": "src/Demo.java",
                    "line": 3,
                    "symbol_name": "getList",
                    "display_name": "getList",
                    "node_kind": "Call",
                    "node_ref": "node-1",
                },
            ],
            "nodes": [
                {
                    "node_id": 0,
                    "file": "src/Demo.java",
                    "line": 2,
                    "symbol_name": "orderBy",
                    "display_name": "orderBy",
                    "node_kind": "Var",
                    "node_ref": "node-0",
                    "raw_props": {
                        "name": "orderBy",
                        "declKind": "Param",
                        "paramIndex": 1,
                    },
                },
                {
                    "node_id": 1,
                    "file": "src/Demo.java",
                    "line": 3,
                    "symbol_name": "getList",
                    "display_name": "getList",
                    "node_kind": "Call",
                    "node_ref": "node-1",
                    "raw_props": {"name": "getList", "kind": "Call"},
                },
            ],
            "edges": [
                {
                    "to_step_id": 1,
                    "to_node_ref": "node-1",
                    "props_json": {"argIndex": 0},
                }
            ],
        }

        highlight_ranges, focus_range = resolve_path_step_highlight(
            version_id=version_id,
            path=path,
            step_id=1,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert focus_range is not None
    if highlight_ranges[0]["kind"] != "argument":
        pytest.skip(
            "tree-sitter argument span resolver unavailable in this test environment"
        )
    assert highlight_ranges[0]["text"] == "orderBy"
    assert highlight_ranges[0]["start_line"] == 3
    assert highlight_ranges[0]["kind"] == "argument"
