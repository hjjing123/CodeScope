from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.core.errors import AppError
from app.services.scan_external import builtin as builtin_module
from app.services.scan_external import context as context_module
from app.services.scan_external.contracts import ExternalScanContext


def _write_required_csv_files(import_dir: Path) -> None:
    for name in builtin_module.REQUIRED_JOERN_EXPORT_FILES:
        (import_dir / name).write_text("h\n", encoding="utf-8")


def _build_builtin_context(
    tmp_path: Path,
) -> tuple[SimpleNamespace, ExternalScanContext, list[tuple[str, str]]]:
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


def test_run_builtin_joern_uses_params_and_logs_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    assert any(
        "cpg_file=" in message and "import_dir=" in message for _, message in logs
    )


def test_run_builtin_joern_missing_required_csv_reports_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job, context, logs = _build_builtin_context(tmp_path)

    def _fake_run(command, *, deadline, env=None):
        if "--script" in command:
            (context.import_dir / "nodes_File_header.csv").write_text(
                "h\n", encoding="utf-8"
            )
            (context.import_dir / "nodes_File_data.csv").write_text(
                "d\n", encoding="utf-8"
            )
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
    assert (
        exc.detail["export_script"]
        == context.base_env["CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT"]
    )
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


def test_build_scan_env_renders_job_scoped_database_names(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    default_script = backend_root / "assets" / "scan" / "joern" / "export_java_min.sc"
    default_script.parent.mkdir(parents=True, exist_ok=True)
    default_script.write_text("script\n", encoding="utf-8")

    joern_home = tmp_path / "joern-home"
    joern_home.mkdir(parents=True, exist_ok=True)
    joern_bin = joern_home / "joern"
    joern_bin.write_text("binary\n", encoding="utf-8")

    job_id = uuid.uuid4()
    settings = SimpleNamespace(
        scan_external_joern_home=str(joern_home),
        scan_external_joern_bin=str(joern_bin),
        scan_external_joern_export_script=str(default_script),
        scan_external_import_csv_host_path="",
        scan_external_import_data_mount="./neo4j-data/{job_id}",
        scan_external_post_labels_cypher="",
        scan_external_rules_dir="",
        scan_external_neo4j_uri="bolt://neo4j-{job_id}:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="scan_graph_{job_id}",
        scan_external_import_database="scan_import_{job_id}",
        scan_external_neo4j_runtime_container_name="neo4j-{job_id}",
        scan_external_neo4j_runtime_network="codescope-net-{job_id}",
        scan_external_neo4j_runtime_network_alias="graph-{job_id}",
        scan_external_stage_joern_command="builtin:joern",
    )
    job = SimpleNamespace(
        id=job_id,
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

    assert env["CODESCOPE_SCAN_NEO4J_URI"] == f"bolt://neo4j-{job_id}:7687"
    assert env["CODESCOPE_SCAN_NEO4J_DATABASE"] == f"scan_graph_{job_id}"
    assert env["CODESCOPE_SCAN_IMPORT_DATABASE"] == f"scan_import_{job_id}"
    assert env["CODESCOPE_SCAN_IMPORT_DATA_MOUNT"] == f"./neo4j-data/{job_id}"
    assert env["CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME"] == f"neo4j-{job_id}"
    assert env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK"] == f"codescope-net-{job_id}"
    assert env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK_ALIAS"] == f"graph-{job_id}"


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
        tmp_path
        / "host-imports"
        / "{project_id}"
        / "{version_id}"
        / "external"
        / "import_csv"
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


def test_build_scan_env_container_compat_requires_host_mount_path(
    tmp_path: Path,
) -> None:
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
    context.base_env["CODESCOPE_SCAN_IMPORT_DATABASE"] = "scan-job-db"

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
            return subprocess.CompletedProcess(
                command, 0, "nodes_File_header.csv\n", ""
            )
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
    assert any("scan-job-db" in " ".join(cmd) for cmd in executed)
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


def test_run_builtin_neo4j_import_creates_ephemeral_runtime_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"
    context.base_env["CODESCOPE_SCAN_IMPORT_DATA_MOUNT"] = "/host/neo4j-job-1"
    context.base_env["CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME"] = "neo4j-job-1"
    context.base_env["CODESCOPE_SCAN_NEO4J_URI"] = "bolt://127.0.0.1:17687"

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
        scan_external_neo4j_password="",
        scan_external_neo4j_runtime_restart_mode="docker_ephemeral",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    executed: list[list[str]] = []
    ready_calls: list[dict[str, object]] = []

    def _fake_run(command, *, deadline, env=None):
        executed.append(list(command))
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "No such container")
        if command[:2] == ["docker", "port"]:
            return subprocess.CompletedProcess(command, 0, "127.0.0.1:17687", "")
        if "--version" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "neo4j-admin 5.26.0", "")
        if command[:3] == ["docker", "run", "-d"]:
            return subprocess.CompletedProcess(command, 0, "cid-123", "")
        return subprocess.CompletedProcess(command, 0, "import-ok", "")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)
    monkeypatch.setattr(
        builtin_module,
        "_wait_for_container_running",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        builtin_module,
        "_wait_for_ephemeral_runtime_ready",
        lambda **kwargs: ready_calls.append(dict(kwargs)),
    )

    stdout, stderr = builtin_module._run_builtin_neo4j_import(
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
        deadline=9999999999.0,
    )

    assert stderr == ""
    assert stdout == "import-ok"
    runtime_run_cmds = [cmd for cmd in executed if cmd[:3] == ["docker", "run", "-d"]]
    assert len(runtime_run_cmds) == 2
    assert "neo4j-job-1-import" in runtime_run_cmds[0]
    assert "neo4j-job-1-query" in runtime_run_cmds[1]
    assert "127.0.0.1::7687" in runtime_run_cmds[0]
    assert "127.0.0.1::7687" in runtime_run_cmds[1]
    assert "NEO4J_AUTH=none" in runtime_run_cmds[0]
    assert "/host/neo4j-job-1:/data" in runtime_run_cmds[1]
    assert ready_calls and ready_calls[0]["container_name"] == "neo4j-job-1-query"
    assert ready_calls[0]["uri"] == "bolt://127.0.0.1:17687"
    assert any("启动导入阶段 Neo4j 容器" in message for _, message in logs)
    assert any("启动查询阶段 Neo4j 容器" in message for _, message in logs)


def test_wait_for_ephemeral_runtime_ready_checks_container_and_connectivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        builtin_module,
        "_wait_for_container_running",
        lambda **kwargs: calls.append(("running", dict(kwargs))),
    )
    monkeypatch.setattr(
        builtin_module,
        "verify_neo4j_connectivity",
        lambda **kwargs: calls.append(("connectivity", dict(kwargs))),
    )

    builtin_module._wait_for_ephemeral_runtime_ready(
        container_name="neo4j-job-2",
        uri="bolt://127.0.0.1:17688",
        user="neo4j",
        password="secret",
        connect_retry=3,
        connect_wait_seconds=2,
        deadline=9999999999.0,
    )

    assert calls[0][0] == "running"
    assert calls[0][1]["container_name"] == "neo4j-job-2"
    assert calls[1][0] == "connectivity"
    assert calls[1][1]["uri"] == "bolt://127.0.0.1:17688"
    assert calls[1][1]["user"] == "neo4j"


def test_run_builtin_neo4j_import_creates_ephemeral_runtime_container_with_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    _write_required_csv_files(context.import_dir)
    context.base_env["CODESCOPE_SCAN_IMPORT_HOST_PATH"] = "/host/csv-mount"
    context.base_env["CODESCOPE_SCAN_IMPORT_DATA_MOUNT"] = "/host/neo4j-job-2"
    context.base_env["CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME"] = "neo4j-job-2"
    context.base_env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK"] = "codescope-net"
    context.base_env["CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK_ALIAS"] = "graph-job-2"
    context.base_env["CODESCOPE_SCAN_NEO4J_URI"] = "bolt://neo4j-job-2:17689"

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
        scan_external_neo4j_password="",
        scan_external_neo4j_runtime_restart_mode="docker_ephemeral",
        scan_external_neo4j_runtime_container_name="CodeScope_neo4j",
        scan_external_neo4j_runtime_restart_wait_seconds=0,
    )

    executed: list[list[str]] = []

    def _fake_run(command, *, deadline, env=None):
        executed.append(list(command))
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "No such container")
        if command[:3] == ["docker", "network", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "net-123", "")
        if "--version" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "neo4j-admin 5.26.0", "")
        if command[:3] == ["docker", "run", "-d"]:
            return subprocess.CompletedProcess(command, 0, "cid-456", "")
        return subprocess.CompletedProcess(command, 0, "import-ok", "")

    monkeypatch.setattr(builtin_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)
    monkeypatch.setattr(
        builtin_module,
        "_wait_for_container_running",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        builtin_module,
        "_wait_for_ephemeral_runtime_ready",
        lambda **kwargs: None,
    )

    stdout, stderr = builtin_module._run_builtin_neo4j_import(
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
        deadline=9999999999.0,
    )

    assert stderr == ""
    assert stdout == "import-ok"
    runtime_run_cmd = next(
        cmd for cmd in executed if cmd[:3] == ["docker", "run", "-d"]
    )
    assert any(cmd[:3] == ["docker", "network", "inspect"] for cmd in executed)
    assert "--network" in runtime_run_cmd
    assert "codescope-net" in runtime_run_cmd
    assert "--network-alias" in runtime_run_cmd
    assert "graph-job-2" in runtime_run_cmd
    assert "-p" not in runtime_run_cmd


def test_run_ephemeral_runtime_container_auto_creates_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[list[str]] = []

    def _fake_run(command, *, deadline, env=None):
        executed.append(list(command))
        if command[:3] == ["docker", "network", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "Error: No such network")
        if command[:3] == ["docker", "network", "create"]:
            return subprocess.CompletedProcess(command, 0, "net-789", "")
        if command[:3] == ["docker", "run", "-d"]:
            return subprocess.CompletedProcess(command, 0, "cid-789", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    metadata = builtin_module._run_ephemeral_runtime_container(
        image="neo4j:5.26",
        container_name="neo4j-job-5",
        data_mount="/host/neo4j-job-5",
        uri="bolt://neo4j-job-5:17692",
        password="",
        network="codescope-net-job-5",
        network_alias="graph-job-5",
        network_auto_create=True,
        deadline=9999999999.0,
    )

    assert any(cmd[:3] == ["docker", "network", "create"] for cmd in executed)
    assert metadata["network"] == "codescope-net-job-5"
    assert metadata["network_alias"] == "graph-job-5"
    assert metadata["network_created_by_job"] is True


def test_run_ephemeral_runtime_container_requires_network_for_non_local_uri() -> None:
    with pytest.raises(AppError) as exc_info:
        builtin_module._run_ephemeral_runtime_container(
            image="neo4j:5.26",
            container_name="neo4j-job-3",
            data_mount="/host/neo4j-job-3",
            uri="bolt://neo4j-job-3:17690",
            password="",
            network="",
            network_alias="",
            network_auto_create=False,
            deadline=9999999999.0,
        )

    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED"
    assert exc.detail["required"] == "scan_external_neo4j_runtime_network"


def test_run_ephemeral_runtime_container_rejects_missing_network_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(command, *, deadline, env=None):
        if command[:3] == ["docker", "network", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "Error: No such network")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(builtin_module, "_run_command_with_deadline", _fake_run)

    with pytest.raises(AppError) as exc_info:
        builtin_module._run_ephemeral_runtime_container(
            image="neo4j:5.26",
            container_name="neo4j-job-4",
            data_mount="/host/neo4j-job-4",
            uri="bolt://neo4j-job-4:17691",
            password="",
            network="codescope-net",
            network_alias="graph-job-4",
            network_auto_create=False,
            deadline=9999999999.0,
        )

    exc = exc_info.value
    assert exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED"
    assert exc.detail["network"] == "codescope-net"


def test_run_builtin_post_labels_supports_directory_scripts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, context, logs = _build_builtin_context(tmp_path)
    post_labels_dir = tmp_path / "post-labels"
    post_labels_dir.mkdir(parents=True, exist_ok=True)
    script_a = post_labels_dir / "01_base.cypher"
    script_b = post_labels_dir / "02_flow.cypher"
    script_a.write_text("RETURN 1;\n", encoding="utf-8")
    script_b.write_text("RETURN 2;\n", encoding="utf-8")
    context.base_env["CODESCOPE_SCAN_POST_LABELS_CYPHER"] = str(post_labels_dir)
    context.base_env["CODESCOPE_SCAN_NEO4J_DATABASE"] = "scan-job-db"

    settings = SimpleNamespace(
        scan_external_neo4j_uri="bolt://127.0.0.1:7687",
        scan_external_neo4j_user="neo4j",
        scan_external_neo4j_password="",
        scan_external_neo4j_database="neo4j",
        scan_external_neo4j_connect_retry=1,
        scan_external_neo4j_connect_wait_seconds=1,
    )

    executed: list[tuple[str, str]] = []

    def _fake_execute(**kwargs):
        executed.append((Path(kwargs["cypher_file"]).name, str(kwargs["database"])))
        return SimpleNamespace(statement_count=1, total_rows=len(executed))

    monkeypatch.setattr(builtin_module, "execute_cypher_file", _fake_execute)

    stdout, stderr = builtin_module._run_builtin_post_labels(
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
    )

    assert stderr == ""
    payload = json.loads(stdout)
    assert executed == [
        ("01_base.cypher", "scan-job-db"),
        ("02_flow.cypher", "scan-job-db"),
    ]
    assert payload["script_count"] == 2
    assert payload["statement_count"] == 2
    assert payload["total_rows"] == 3
    assert [item["script"] for item in payload["scripts"]] == [
        item[0] for item in executed
    ]
    assert any("开始执行脚本 1/2" in message for _, message in logs)
    assert any("脚本执行完成 2/2" in message for _, message in logs)


def test_run_builtin_rules_executes_rules_without_runtime_validation(
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

    executed: list[str] = []

    def _fake_execute(**kwargs):
        executed.append(Path(kwargs["cypher_file"]).name)
        return SimpleNamespace(total_rows=2)

    monkeypatch.setattr(builtin_module, "execute_cypher_file", _fake_execute)

    stdout, stderr = builtin_module._run_builtin_rules(
        job=job,
        settings=settings,
        context=context,
        append_log=lambda stage, message: logs.append((stage, message)),
    )

    assert stderr == ""
    payload = json.loads(stdout)
    assert executed == ["safe_rule.cypher", "unsafe_rule.cypher"]
    assert payload["failed_rules"] == 0
    assert payload["succeeded_rules"] == 2
    assert payload["failed_rule_keys"] == []
    assert payload["partial_failure_effect"] == "none"
    assert len(payload["rule_results"]) == 2
    assert payload["rule_results"][0]["duration_ms"] >= 0
    assert payload["rule_results"][1]["duration_ms"] >= 0
    round_report = json.loads(
        (context.reports_dir / "round_1.json").read_text(encoding="utf-8")
    )
    assert round_report["execution_summary"]["failed_rules"] == 0
    assert round_report["execution_summary"]["succeeded_rules"] == 2
    assert round_report["execution_summary"]["failed_rule_keys"] == []
    assert round_report["execution_summary"]["partial_failure_effect"] == "none"
    assert round_report["rule_results"][0]["status"] == "succeeded"
    assert round_report["rule_results"][1]["status"] == "succeeded"
    assert round_report["rule_results"][0]["duration_ms"] >= 0
    assert round_report["rule_results"][1]["duration_ms"] >= 0


def test_run_builtin_rules_strict_fails_on_execution_error(
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
        raise AppError(
            code="SCAN_EXTERNAL_RULES_FAILED",
            status_code=422,
            message="规则执行失败",
        )

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
    assert called["count"] == 1


def test_remove_data_mount_refuses_host_path_outside_allowlist(tmp_path: Path) -> None:
    settings = get_settings()
    old_allowlist = settings.scan_external_cleanup_host_path_allowlist
    allowed_root = tmp_path / "allowed"
    forbidden_root = tmp_path / "forbidden"
    forbidden_root.mkdir(parents=True, exist_ok=True)
    target = forbidden_root / "job-data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "marker.txt").write_text("x\n", encoding="utf-8")

    settings.scan_external_cleanup_host_path_allowlist = str(allowed_root)
    try:
        with pytest.raises(AppError) as exc_info:
            builtin_module._remove_data_mount(
                data_mount=str(target),
                deadline=time.time() + 30,
            )
    finally:
        settings.scan_external_cleanup_host_path_allowlist = old_allowlist

    assert exc_info.value.message == "拒绝删除白名单之外的宿主机 Neo4j 数据目录"
    assert target.exists()


def test_remove_data_mount_allows_host_path_within_allowlist(tmp_path: Path) -> None:
    settings = get_settings()
    old_allowlist = settings.scan_external_cleanup_host_path_allowlist
    allowed_root = tmp_path / "allowed"
    target = allowed_root / "job-data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "marker.txt").write_text("x\n", encoding="utf-8")

    settings.scan_external_cleanup_host_path_allowlist = str(allowed_root)
    try:
        builtin_module._remove_data_mount(
            data_mount=str(target),
            deadline=time.time() + 30,
        )
    finally:
        settings.scan_external_cleanup_host_path_allowlist = old_allowlist

    assert not target.exists()
