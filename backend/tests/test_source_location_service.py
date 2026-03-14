from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.config import get_settings
from app.services import source_location_service as source_location_service_module


def test_normalize_graph_location_prefers_variable_usage_line_for_var_nodes() -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    backend_root = Path(source_location_service_module.__file__).resolve().parents[2]
    relative_root = f"storage/test-source-location-{uuid.uuid4().hex}"
    version_id = uuid.uuid4()
    source_root = backend_root / relative_root / str(version_id) / "source" / "src"
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
        file_path, line = source_location_service_module.normalize_graph_location(
            version_id=version_id,
            file_path="/tmp/jimple2cpg-1/com/example/Main.class",
            line=-1,
            func_name="run",
            node_ref="Var|/tmp/jimple2cpg-1/com/example/Main.class|-1|-1|id|templateString|com.example.Main.run:java.lang.String(java.lang.String)",
            labels=["Var", "Reference"],
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        shutil.rmtree(backend_root / relative_root, ignore_errors=True)

    assert file_path == "src/Main.java"
    assert line == 3


def test_normalize_graph_location_skips_comment_matches_before_method_context() -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    backend_root = Path(source_location_service_module.__file__).resolve().parents[2]
    relative_root = f"storage/test-source-location-{uuid.uuid4().hex}"
    version_id = uuid.uuid4()
    source_root = backend_root / relative_root / str(version_id) / "source" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Main.java").write_text(
        "class Main {\n"
        "  /**\n"
        "   * username should not resolve here\n"
        "   */\n"
        "  String run(String username) {\n"
        "    return username.trim();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    settings.snapshot_storage_root = f"./{relative_root}"
    try:
        file_path, line = source_location_service_module.normalize_graph_location(
            version_id=version_id,
            file_path="/tmp/jimple2cpg-1/com/example/Main.class",
            line=-1,
            func_name="run",
            node_ref=(
                "Var|/tmp/jimple2cpg-1/com/example/Main.class|-1|-1|param|username|"
                "com.example.Main.run:java.lang.String(java.lang.String)"
            ),
            labels=["Var", "Argument", "Reference"],
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root
        shutil.rmtree(backend_root / relative_root, ignore_errors=True)

    assert file_path == "src/Main.java"
    assert line == 5
