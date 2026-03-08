from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services.scan_external import builtin as builtin_module
from app.services.scan_external import context as context_module
from app.services.scan_external.contracts import ExternalScanContext


def _write_required_csv_files(import_dir: Path) -> None:
    for name in builtin_module.REQUIRED_JOERN_EXPORT_FILES:
        (import_dir / name).write_text("h\n", encoding="utf-8")


def _build_builtin_context(tmp_path: Path) -> tuple[SimpleNamespace, ExternalScanContext, list[tuple[str, str]]]:
    job = SimpleNamespace(payload={})

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")
    (joern_home / "joern-parse").write_text("binary\n", encoding="utf-8")
    (joern_home / "joern-parse.bat").write_text("@echo off\n", encoding="utf-8")

    export_script = tmp_path / "export_java_min.sc"
    export_script.write_text("script\n", encoding="utf-8")

    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    import_dir = workspace_dir / "import_csv"
    import_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    cpg_file = workspace_dir / "code.bin"

    context = ExternalScanContext(
        reports_dir=reports_dir,
        workdir=str(tmp_path),
        base_env={
            "CODESCOPE_SCAN_JOERN_BIN": str(joern_bin),
            "CODESCOPE_SCAN_JOERN_HOME": str(joern_home),
            "CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT": str(export_script),
        },
        stage_specs=[],
        backend_root=tmp_path,
        source_dir=source_dir,
        workspace_dir=workspace_dir,
        import_dir=import_dir,
        cpg_file=cpg_file,
    )
    logs: list[tuple[str, str]] = []
    return job, context, logs


def test_run_builtin_joern_uses_params_and_logs_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job, context, logs = _build_builtin_context(tmp_path)
    captured_command: list[str] = []
    captured_env: dict[str, str] = {}

    def _fake_run(command, *, deadline, env=None):
        if "--script" in command:
            captured_command[:] = command
            captured_env.update(env or {})
            _write_required_csv_files(context.import_dir)
            return subprocess.CompletedProcess(command, 0, "export-ok", "")
        return subprocess.CompletedProcess(command, 0, "parse-ok", "")

    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    stdout, stderr = builtin_module._run_builtin_joern(
        job=job,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
        deadline=9999999999.0,
    )

    assert stderr == ""
    assert "nodes=" in stdout
    assert "--param" in captured_command
    assert f"cpgFile={context.cpg_file}" in captured_command
    assert f"outDir={context.import_dir}" in captured_command
    assert captured_env.get("cpgFile") == str(context.cpg_file)
    assert captured_env.get("outDir") == str(context.import_dir)
    assert any("command=" in message and "script=" in message for _, message in logs)
    assert any("cpg_file=" in message and "import_dir=" in message for _, message in logs)


def test_run_builtin_joern_missing_required_csv_reports_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job, context, logs = _build_builtin_context(tmp_path)

    def _fake_run(command, *, deadline, env=None):
        if "--script" in command:
            (context.import_dir / "nodes_File_header.csv").write_text("h\n", encoding="utf-8")
            (context.import_dir / "nodes_File_data.csv").write_text("d\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "export-ok", "")
        return subprocess.CompletedProcess(command, 0, "parse-ok", "")

    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_builtin_joern(
            job=job,
            context=context,
            append_log=lambda stage, message: logs.append((stage, message)),
            deadline=9999999999.0,
        )

    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_JOERN_FAILED"
    assert exc.message == "Joern 导出关键 CSV 产物缺失"
    assert exc.detail["export_script"] == context.base_env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"]
    assert exc.detail["import_dir"] == str(context.import_dir)
    assert "nodes_Method_header.csv" in exc.detail["missing_files"]
    assert "edges_ARG_data.csv" in exc.detail["missing_files"]


def test_build_scan_env_falls_back_default_export_script(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    default_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    default_script.parent.mkdir(parents=True, exist_ok=True)
    default_script.write_text("script\n", encoding="utf-8")

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")

    settings = SimpleNamespace(
        scan_external_joern_home=str(joern_home),
        scan_external_joern_bin=str(joern_bin),
        scan_external_joern_export_script="",
        scan_external_import_csv_host_path="",
        scan_external_post_labels_cypher="",
        scan_external_rules_dir="",
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_stage_joern_command="builtin:joern",
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        payload={},
    )

    env = context_module._build_scan_env(
        job=job,
        settings=settings,
        backend_root=backend_root,
        reports_dir=tmp_path / "reports",
        source_dir=tmp_path / "source",
        import_dir=tmp_path / "import_csv",
        cpg_file=tmp_path / "code.bin",
    )

    assert env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"] == str(default_script.resolve())
    assert env["CODESCOPE_SCAN_RUNTIME_PROFILE"] == "wsl"
    assert env["CODESCOPE_SCAN_CONTAINER_COMPAT_MODE"] == "0"


def test_build_scan_env_uses_custom_export_script(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    default_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    default_script.parent.mkdir(parents=True, exist_ok=True)
    default_script.write_text("default\n", encoding="utf-8")

    custom_script = tmp_path / "custom_export.sc"
    custom_script.write_text("custom\n", encoding="utf-8")

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")

    settings = SimpleNamespace(
        scan_external_joern_home=str(joern_home),
        scan_external_joern_bin=str(joern_bin),
        scan_external_joern_export_script=str(custom_script),
        scan_external_import_csv_host_path="",
        scan_external_post_labels_cypher="",
        scan_external_rules_dir="",
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_stage_joern_command="builtin:joern",
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        payload={},
    )

    env = context_module._build_scan_env(
        job=job,
        settings=settings,
        backend_root=backend_root,
        reports_dir=tmp_path / "reports",
        source_dir=tmp_path / "source",
        import_dir=tmp_path / "import_csv",
        cpg_file=tmp_path / "code.bin",
    )

    assert env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"] == str(custom_script.resolve())


def test_build_scan_env_uses_custom_import_host_path(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    default_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    default_script.parent.mkdir(parents=True, exist_ok=True)
    default_script.write_text("default\n", encoding="utf-8")

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")

    host_template = str(
        tmp_path / "host-imports" / "{project_id}" / "{version_id}" / "external" / "import_csv"
    )
    settings = SimpleNamespace(
        scan_external_joern_home=str(joern_home),
        scan_external_joern_bin=str(joern_bin),
        scan_external_joern_export_script=str(default_script),
        scan_external_import_csv_host_path=host_template,
        scan_external_post_labels_cypher="",
        scan_external_rules_dir="",
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_stage_joern_command="builtin:joern",
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        payload={},
    )

    env = context_module._build_scan_env(
        job=job,
        settings=settings,
        backend_root=backend_root,
        reports_dir=tmp_path / "reports",
        source_dir=tmp_path / "source",
        import_dir=tmp_path / "import_csv",
        cpg_file=tmp_path / "code.bin",
    )

    expected = (
        tmp_path
        / "host-imports"
        / str(job.project_id)
        / str(job.version_id)
        / "external"
        / "import_csv"
    )
    assert env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] == str(expected.resolve())


def test_build_scan_env_container_compat_requires_host_mount_path(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    default_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    default_script.parent.mkdir(parents=True, exist_ok=True)
    default_script.write_text("default\n", encoding="utf-8")

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")

    settings = SimpleNamespace(
        scan_external_runtime_profile="container_compat",
        scan_external_container_compat_mode=False,
        scan_external_joern_home=str(joern_home),
        scan_external_joern_bin=str(joern_bin),
        scan_external_joern_export_script=str(default_script),
        scan_external_import_csv_host_path="",
        scan_external_post_labels_cypher="",
        scan_external_rules_dir="",
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_stage_joern_command="builtin:joern",
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        payload={},
    )

    with pytest.raises(AppError) as exc_info:
        context_module._build_scan_env(
            job=job,
            settings=settings,
            backend_root=backend_root,
            reports_dir=tmp_path / "reports",
            source_dir=tmp_path / "source",
            import_dir=tmp_path / "import_csv",
            cpg_file=tmp_path / "code.bin",
        )
    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED"
    assert exc.detail["required"] == "scan_external_import_csv_host_path"


def test_preflight_check_docker_daemon_reports_reachability_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(command, *, deadline, env=None):
        return subprocess.CompletedProcess(command, 1, "", "cannot connect daemon")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    with pytest.raises(AppError) as exc_info:
        builtin_module._preflight_check_docker_daemon(deadline=9999999999.0)

    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_IMPORT_FAILED"
    assert exc.message == "Docker daemon 不可达"
    assert exc.detail["failure_kind"] == "docker_daemon_unreachable"
    assert exc.detail["command"] == ["docker", "info", "--format", "{{.ServerVersion}}"]


def test_preflight_check_import_mount_reports_failure_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(command, *, deadline, env=None):
        return subprocess.CompletedProcess(command, 1, "", "mount denied")

    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    with pytest.raises(AppError) as exc_info:
        builtin_module._preflight_check_import_mount(
            import_host="/host/csv", deadline=9999999999.0
        )

    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_IMPORT_FAILED"
    assert exc.detail["failure_kind"] == "import_mount_unreachable"
    assert exc.detail["import_host"] == "/host/csv"


def test_run_builtin_neo4j_import_wsl_rejects_non_linux_import_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, _ = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_RUNTIME_PROFILE"] = "wsl"
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "C:/host/csv-mount"
    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")

    settings = SimpleNamespace(
        scan_external_import_docker_image="neo4j:5.26",
        scan_external_import_data_mount=str(tmp_path / "neo4j-data"),
        scan_external_import_database="neo4j",
        scan_external_import_id_type="string",
        scan_external_import_array_delimiter="\\001",
        scan_external_import_clean_db=False,
        scan_external_import_multiline_fields=True,
        scan_external_import_multiline_fields_format="",
        scan_external_import_preflight=False,
        scan_external_import_preflight_check_docker=False,
        scan_external_neo4j_runtime_restart_mode="none",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_builtin_neo4j_import(
            settings=settings,
            context=context,
            append_log=lambda stage, message: None,
            deadline=9999999999.0,
        )
    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED"
    assert exc.detail["runtime_profile"] == "wsl"


def test_resolve_import_host_mount_path_wsl_accepts_linux_path(tmp_path: Path) -> None:
    _, context, _ = _build_builtin_context(tmp_path)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"

    mount_path = builtin_module._resolve_import_host_mount_path(
        context=context,
        runtime_profile="wsl",
    )

    assert mount_path == "/host/csv-mount"


def test_run_builtin_neo4j_import_uses_host_mapping_and_logs_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"

    settings = SimpleNamespace(
        scan_external_import_docker_image="neo4j:5.26",
        scan_external_import_data_mount=str(tmp_path / "neo4j-data"),
        scan_external_import_database="neo4j",
        scan_external_import_id_type="string",
        scan_external_import_array_delimiter="\\001",
        scan_external_import_clean_db=False,
        scan_external_import_multiline_fields=True,
        scan_external_import_multiline_fields_format="",
        scan_external_import_preflight=True,
        scan_external_import_preflight_check_docker=True,
        scan_external_neo4j_runtime_restart_mode="none",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    executed: list[list[str]] = []

    def _fake_run(command, *, deadline, env=None):
        executed.append(list(command))
        if command[:3] == ["docker", "info", "--format"]:
            return subprocess.CompletedProcess(command, 0, "26.0.0", "")
        if "alpine:3.19" in command:
            return subprocess.CompletedProcess(command, 0, "nodes_File_header.csv\n", "")
        if "--version" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "neo4j-admin 5.26.0", "")
        return subprocess.CompletedProcess(command, 0, "import-ok", "")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    stdout, stderr = builtin_module._run_builtin_neo4j_import(
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
        deadline=9999999999.0,
    )

    assert stderr == ""
    assert stdout == "import-ok"
    assert any("/host/csv-mount:/import:ro" in " ".join(cmd) for cmd in executed)
    assert any("执行导入命令" in message for _, message in logs)


def test_run_builtin_neo4j_import_missing_csv_pair_maps_import_failure_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, _ = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    (context.import_dir / "nodes_File_data.csv").unlink()

    settings = SimpleNamespace(
        scan_external_import_docker_image="neo4j:5.26",
        scan_external_import_data_mount=str(tmp_path / "neo4j-data"),
        scan_external_import_database="neo4j",
        scan_external_import_id_type="string",
        scan_external_import_array_delimiter="\\001",
        scan_external_import_clean_db=False,
        scan_external_import_multiline_fields=True,
        scan_external_import_multiline_fields_format="",
        scan_external_import_preflight=False,
        scan_external_import_preflight_check_docker=False,
        scan_external_neo4j_runtime_restart_mode="none",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_builtin_neo4j_import(
            settings=settings,
            context=context,
            append_log=lambda stage, message: None,
            deadline=9999999999.0,
        )
    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_IMPORT_FAILED"
    assert "nodes_File_data.csv" in exc.detail["data"]


def test_run_builtin_neo4j_import_logs_failure_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"

    settings = SimpleNamespace(
        scan_external_import_docker_image="neo4j:5.26",
        scan_external_import_data_mount=str(tmp_path / "neo4j-data"),
        scan_external_import_database="neo4j",
        scan_external_import_id_type="string",
        scan_external_import_array_delimiter="\\001",
        scan_external_import_clean_db=False,
        scan_external_import_multiline_fields=True,
        scan_external_import_multiline_fields_format="",
        scan_external_import_preflight=False,
        scan_external_import_preflight_check_docker=False,
        scan_external_neo4j_runtime_restart_mode="none",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    def _fake_run(command, *, deadline, env=None):
        if "--version" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "neo4j-admin 5.26.0", "")
        return subprocess.CompletedProcess(command, 7, "import stdout", "import stderr")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_builtin_neo4j_import(
            settings=settings,
            context=context,
            append_log=lambda stage, message: logs.append((stage, message)),
            deadline=9999999999.0,
        )
    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_IMPORT_FAILED"
    assert exc.detail["stdout_tail"] == "import stdout"
    assert exc.detail["stderr_tail"] == "import stderr"
    assert any("导入失败" in message for _, message in logs)
    assert any("stdout_tail=import stdout" in message for _, message in logs)


def test_run_builtin_neo4j_import_starts_container_after_import_when_initially_stopped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"

    settings = SimpleNamespace(
        scan_external_import_docker_image="neo4j:5.26",
        scan_external_import_data_mount=str(tmp_path / "neo4j-data"),
        scan_external_import_database="neo4j",
        scan_external_import_id_type="string",
        scan_external_import_array_delimiter="\\001",
        scan_external_import_clean_db=False,
        scan_external_import_multiline_fields=True,
        scan_external_import_multiline_fields_format="",
        scan_external_import_preflight=False,
        scan_external_import_preflight_check_docker=False,
        scan_external_neo4j_runtime_restart_mode="docker",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    executed: list[list[str]] = []

    def _fake_run(command, *, deadline, env=None):
        executed.append(list(command))
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "false", "")
        if "--version" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "neo4j-admin 5.26.0", "")
        if command[:2] == ["docker", "start"]:
            return subprocess.CompletedProcess(command, 0, "CodeScope_neo4j", "")
        return subprocess.CompletedProcess(command, 0, "import-ok", "")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    stdout, stderr = builtin_module._run_builtin_neo4j_import(
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
        deadline=9999999999.0,
    )

    assert stderr == ""
    assert stdout == "import-ok"
    assert any(cmd[:2] == ["docker", "inspect"] for cmd in executed)
    assert any(cmd[:2] == ["docker", "start"] for cmd in executed)
    assert any("导入前 Neo4j 容器未运行" in message for _, message in logs)
    assert any("启动 Neo4j 容器" in message for _, message in logs)


def test_run_builtin_rules_permissive_records_runtime_validation_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job, context, logs = _build_builtin_context(tmp_path)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    context.base_env["CODESCOPE_SCAN_RULES_DIR"] = str(rules_dir)
    (rules_dir / "safe_rule.cypher").write_text(
        "MATCH (n) RETURN n LIMIT 1;",
        encoding="utf-8",
    )
    (rules_dir / "unsafe_rule.cypher").write_text(
        "MATCH (n) SET n.tmp = 1 RETURN n;",
        encoding="utf-8",
    )

    settings = SimpleNamespace(
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_neo4j_connect_retry=1,
        scan_external_neo4j_connect_wait_seconds=1,
        scan_external_rules_max_count=0,
        scan_external_rules_failure_mode="permissive",
    )
    job.payload["resolved_rule_keys"] = ["safe_rule", "unsafe_rule"]

    monkeypatch.setattr(
        builtin_module,
        "execute_cypher_file",
        lambda **kwargs: SimpleNamespace(total_rows=2),
    )

    stdout, stderr = builtin_module._run_builtin_rules(
        job=job,
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
    )

    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["failed_rules"] == 1
    assert payload["succeeded_rules"] == 1
    assert payload["failed_rule_keys"] == ["unsafe_rule"]
    round_report = json.loads((context.reports_dir / "round_1.json").read_text(encoding="utf-8"))
    assert round_report["execution_summary"]["failed_rules"] == 1
    assert round_report["execution_summary"]["succeeded_rules"] == 1
    assert round_report["execution_summary"]["failed_rule_keys"] == ["unsafe_rule"]


def test_run_builtin_rules_strict_fails_on_runtime_validation_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job, context, _ = _build_builtin_context(tmp_path)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    context.base_env["CODESCOPE_SCAN_RULES_DIR"] = str(rules_dir)
    (rules_dir / "unsafe_rule.cypher").write_text(
        "MATCH (n) SET n.tmp = 1 RETURN n;",
        encoding="utf-8",
    )

    settings = SimpleNamespace(
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_neo4j_connect_retry=1,
        scan_external_neo4j_connect_wait_seconds=1,
        scan_external_rules_max_count=0,
        scan_external_rules_failure_mode="strict",
    )
    job.payload["resolved_rule_keys"] = ["unsafe_rule"]

    called = {"count": 0}

    def _fake_execute(**kwargs):
        called["count"] += 1
        return SimpleNamespace(total_rows=1)

    monkeypatch.setattr(builtin_module, "execute_cypher_file", _fake_execute)

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_builtin_rules(
            job=job,
            settings=settings,
            context=context,
            append_log=lambda stage, message: None,
        )
    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_RULES_FAILED"
    assert exc.message == "规则执行失败（strict 模式）"
    assert exc.detail["failure_mode"] == "strict"
    assert exc.detail["failed_rule"] == "unsafe_rule"
    assert called["count"] == 0
