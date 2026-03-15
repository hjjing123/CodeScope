from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from app.config import get_settings
from app.core.errors import AppError
from app.models import Job
from app.services.path_graph_service import (
    build_linear_path_edges,
    build_path_edge_payload,
    build_path_node_payload as build_trace_node_payload,
    build_path_step_payload,
)
from app.services.rule_file_service import (
    list_runtime_rule_files,
    resolve_runtime_rule_files,
)

from .contracts import ExternalScanContext
from .neo4j_runner import (
    execute_cypher_file,
    execute_cypher_file_stream,
    verify_neo4j_connectivity,
)
from .runtime_metadata import write_runtime_metadata
from .source_semantic_enhance import run_source_semantic_enhance


NODE_HEADER_RE = re.compile(r"^nodes_(.+)_header\.csv$", re.IGNORECASE)
EDGE_HEADER_RE = re.compile(r"^edges_(.+)_header\.csv$", re.IGNORECASE)
REQUIRED_JOERN_EXPORT_FILES = (
    "nodes_File_header.csv",
    "nodes_File_data.csv",
    "nodes_Method_header.csv",
    "nodes_Method_data.csv",
    "nodes_Call_header.csv",
    "nodes_Call_data.csv",
    "nodes_Var_header.csv",
    "nodes_Var_data.csv",
    "edges_IN_FILE_header.csv",
    "edges_IN_FILE_data.csv",
    "edges_HAS_CALL_header.csv",
    "edges_HAS_CALL_data.csv",
    "edges_ARG_header.csv",
    "edges_ARG_data.csv",
)
WSL_RUNTIME_PROFILE = "wsl"
CONTAINER_COMPAT_RUNTIME_PROFILE = "container_compat"
DOCKER_EPHEMERAL_RUNTIME_MODE = "docker_ephemeral"
MYBATIS_UNSAFE_ARG_LABELS = {"MybatisXmlUnsafeArg", "MybatisAnnotationUnsafeArg"}


def _normalize_case_file_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    marker = "/source/"
    if marker in text:
        return text.split(marker, 1)[1]
    return text


def _finding_case_node_name(node: dict[str, object]) -> str:
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    for candidate in (
        raw_props.get("name"),
        node.get("symbol_name"),
        node.get("display_name"),
        node.get("func_name"),
        raw_props.get("method"),
        raw_props.get("methodFullName"),
        raw_props.get("fullName"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _finding_case_node_fingerprint_part(node: dict[str, object]) -> str:
    labels = (
        ":".join(
            sorted(
                str(item).strip()
                for item in node.get("labels") or []
                if str(item).strip()
            )
        )
        or "Node"
    )
    raw_props = node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
    name = _finding_case_node_name(node)
    node_type = str(
        node.get("type_name")
        or raw_props.get("type")
        or raw_props.get("receiverType")
        or ""
    ).strip()
    file_path = _normalize_case_file_path(node.get("file") or raw_props.get("file"))
    line = _safe_int(node.get("line"))
    return (
        f"{labels}({name}|{node_type}|{file_path}:{line if line is not None else -1})"
    )


def _finding_case_edge_fingerprint_part(edge: dict[str, object]) -> str:
    props = edge.get("props_json") if isinstance(edge.get("props_json"), dict) else {}
    arg_index = props.get("argIndex")
    if arg_index in (None, ""):
        arg_index = props.get("argPosition")
    edge_type = str(edge.get("edge_type") or "EDGE").strip() or "EDGE"
    label = str(edge.get("label") or "").strip()
    return f"{edge_type}({label}|{arg_index if arg_index not in (None, '') else ''})"


def _finding_case_path_fingerprint(path: dict[str, object]) -> str:
    raw_nodes = path.get("nodes") if isinstance(path.get("nodes"), list) else []
    if not raw_nodes and isinstance(path.get("steps"), list):
        raw_nodes = [item for item in path.get("steps") or [] if isinstance(item, dict)]
    raw_edges = path.get("edges") if isinstance(path.get("edges"), list) else []
    node_parts = ",".join(
        _finding_case_node_fingerprint_part(node)
        for node in raw_nodes
        if isinstance(node, dict)
    )
    edge_parts = ",".join(
        _finding_case_edge_fingerprint_part(edge)
        for edge in raw_edges
        if isinstance(edge, dict)
    )
    return f"N[{node_parts}]|E[{edge_parts}]"


def _finding_hit_fingerprint(rule_key: str, finding_hit: dict[str, object]) -> str:
    paths = (
        finding_hit.get("paths") if isinstance(finding_hit.get("paths"), list) else []
    )
    path_fingerprints = [
        _finding_case_path_fingerprint(path) for path in paths if isinstance(path, dict)
    ]
    if path_fingerprints:
        return f"path|{rule_key}|{'||'.join(path_fingerprints)}"

    evidence = (
        finding_hit.get("evidence")
        if isinstance(finding_hit.get("evidence"), dict)
        else {}
    )
    labels = ",".join(
        sorted(
            str(item).strip()
            for item in evidence.get("labels") or []
            if str(item).strip()
        )
    )
    file_path = _normalize_case_file_path(
        finding_hit.get("file_path") or finding_hit.get("sink_file")
    )
    line = _safe_int(finding_hit.get("line_start") or finding_hit.get("sink_line"))
    node_ref = str(evidence.get("node_ref") or "").strip()
    return f"node|{rule_key}|{file_path}:{line if line is not None else -1}|{labels}|{node_ref}"


def _allow_mybatis_finding_hit(finding_hit: dict[str, object]) -> bool:
    paths = (
        finding_hit.get("paths") if isinstance(finding_hit.get("paths"), list) else []
    )
    if not paths or not isinstance(paths[0], dict):
        return True
    nodes = paths[0].get("nodes") if isinstance(paths[0].get("nodes"), list) else []
    if not nodes or not isinstance(nodes[0], dict):
        return True

    source_name = _finding_case_node_name(nodes[0])
    if not source_name:
        return False
    sink_root_name = (
        _finding_case_node_name(nodes[-1]) if isinstance(nodes[-1], dict) else ""
    )
    sink_args: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        labels = {
            str(item).strip() for item in node.get("labels") or [] if str(item).strip()
        }
        raw_props = (
            node.get("raw_props") if isinstance(node.get("raw_props"), dict) else {}
        )
        node_name = str(raw_props.get("name") or "").strip()
        is_mybatis_sink = bool(labels & MYBATIS_UNSAFE_ARG_LABELS)
        is_sink_family = bool(sink_root_name and node_name == sink_root_name)
        if not is_mybatis_sink and not is_sink_family:
            continue
        flat_args = raw_props.get("flatArgs") or []
        if isinstance(flat_args, list):
            sink_args.update(
                str(item).strip() for item in flat_args if str(item).strip()
            )
    if not sink_args:
        return True
    return source_name in sink_args


def _allow_finding_hit_for_rule(rule_key: str, finding_hit: dict[str, object]) -> bool:
    lower = rule_key.lower()
    if "mybatis" in lower and "sqli" in lower:
        return _allow_mybatis_finding_hit(finding_hit)
    return True


def run_builtin_stage(
    *,
    builtin_key: str,
    job: Job,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    timeout_seconds: int,
    on_rule_finding: Callable[[dict[str, object]], None] | None = None,
) -> tuple[str, str]:
    deadline = time.monotonic() + max(1, timeout_seconds)

    if builtin_key == "joern":
        return _run_builtin_joern(
            job=job,
            context=context,
            append_log=append_log,
            deadline=deadline,
        )
    if builtin_key == "neo4j_import":
        return _run_builtin_neo4j_import(
            settings=settings,
            context=context,
            append_log=append_log,
            deadline=deadline,
        )
    if builtin_key == "post_labels":
        return _run_builtin_post_labels(
            settings=settings,
            context=context,
            append_log=append_log,
        )
    if builtin_key == "source_semantic":
        return run_source_semantic_enhance(
            settings=settings,
            context=context,
            append_log=append_log,
        )
    if builtin_key == "rules":
        return _run_builtin_rules(
            job=job,
            settings=settings,
            context=context,
            append_log=append_log,
            deadline=deadline,
            on_rule_finding=on_rule_finding,
        )

    raise AppError(
        code="SCAN_EXTERNAL_NOT_CONFIGURED",
        status_code=501,
        message="未知的 builtin 阶段标识",
        detail={"builtin_key": builtin_key},
    )


def _run_builtin_joern(
    *,
    job: Job,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    deadline: float,
) -> tuple[str, str]:
    settings = get_settings()
    joern_bin = Path(context.base_env.get("CODESCOPE_SCAN_JOERN_BIN") or "")
    joern_home = Path(context.base_env.get("CODESCOPE_SCAN_JOERN_HOME") or "")
    export_script = Path(
        context.base_env.get("CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT") or ""
    )

    if not joern_bin.exists() or not joern_bin.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 可执行文件不存在",
            detail={"joern_bin": str(joern_bin)},
        )
    if not export_script.exists() or not export_script.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="Joern 导出脚本不存在",
            detail={
                "export_script": str(export_script),
                "cpg_file": str(context.cpg_file),
                "import_dir": str(context.import_dir),
            },
        )

    append_log(
        "ANALYZE",
        (
            "[joern] 路径准备: "
            f"source_dir={context.source_dir}, cpg_file={context.cpg_file}, "
            f"import_dir={context.import_dir}, joern_bin={joern_bin}, export_script={export_script}"
        ),
    )

    joern_parse_bin = _resolve_joern_binary(
        joern_home=joern_home,
        windows_name="joern-parse.bat",
        unix_name="joern-parse",
    )
    if not joern_parse_bin.exists() or not joern_parse_bin.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="joern-parse 可执行文件不存在",
            detail={"joern_parse_bin": str(joern_parse_bin)},
        )

    _clear_directory(context.import_dir)
    context.workspace_dir.mkdir(parents=True, exist_ok=True)
    if context.cpg_file.exists() and context.cpg_file.is_file():
        context.cpg_file.unlink(missing_ok=True)
    joern_runtime_dir = context.workspace_dir / "joern-runtime"
    joern_runtime_dir.mkdir(parents=True, exist_ok=True)

    parse_cmd = [
        str(joern_parse_bin),
        str(context.source_dir),
        "--output",
        str(context.cpg_file),
    ]
    parse_command_text = _command_to_text(parse_cmd)
    append_log(
        "ANALYZE",
        (
            "[joern] 执行 parse 命令: "
            f"command={parse_command_text}, script={export_script}, "
            f"cpg_file={context.cpg_file}, import_dir={context.import_dir}"
        ),
    )
    parse_result = _run_command_with_deadline(
        parse_cmd,
        deadline=deadline,
        cwd=joern_runtime_dir,
    )
    if parse_result.returncode != 0:
        parse_stdout_tail = _tail_text(parse_result.stdout)
        parse_stderr_tail = _tail_text(parse_result.stderr)
        append_log(
            "ANALYZE",
            (
                f"[joern] parse 失败: exit_code={parse_result.returncode}, "
                f"command={parse_command_text}, script={export_script}, "
                f"cpg_file={context.cpg_file}, import_dir={context.import_dir}, "
                f"stdout_tail={parse_stdout_tail}, stderr_tail={parse_stderr_tail}"
            ),
        )
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="joern-parse 执行失败",
            detail={
                "exit_code": parse_result.returncode,
                "command": parse_cmd,
                "source_dir": str(context.source_dir),
                "cpg_file": str(context.cpg_file),
                "import_dir": str(context.import_dir),
                "export_script": str(export_script),
                "stdout_tail": parse_stdout_tail,
                "stderr_tail": parse_stderr_tail,
            },
        )

    export_env = dict(context.base_env)
    patch = job.payload.get("joern_patch")
    patch_map = patch if isinstance(patch, dict) else {}
    enable_calls = _to_bool_flag(
        patch_map.get("ENABLE_CALLS"),
        default=bool(
            getattr(settings, "scan_external_joern_enable_calls_default", True)
        ),
    )
    enable_ref = _to_bool_flag(
        patch_map.get("ENABLE_REF"),
        default=bool(getattr(settings, "scan_external_joern_enable_ref_default", True)),
    )
    ast_mode = str(patch_map.get("AST_MODE", "local") or "local").lower()
    if ast_mode not in {"none", "local", "wide"}:
        ast_mode = "local"

    export_env["cpgFile"] = str(context.cpg_file)
    export_env["outDir"] = str(context.import_dir)
    export_env.setdefault("CODE_ROOT", str(context.source_dir))
    export_env.setdefault("SCAN_ROOT", str(context.source_dir))
    export_env["ENABLE_CALLS"] = "true" if enable_calls else "false"
    export_env["ENABLE_REF"] = "true" if enable_ref else "false"
    export_env["AST_MODE"] = ast_mode
    raw_array_delim = str(
        getattr(settings, "scan_external_import_array_delimiter", "\\001") or "\\001"
    )
    export_env["ARRAY_DELIM"] = (
        "001"
        if raw_array_delim in {"\\001", "\\u0001", "U+0001", "\u0001"}
        else raw_array_delim
    )

    export_cmd = [
        str(joern_bin),
        "--script",
        str(export_script),
        "--param",
        f"cpgFile={context.cpg_file}",
        "--param",
        f"outDir={context.import_dir}",
        "--param",
        f"ENABLE_CALLS={export_env['ENABLE_CALLS']}",
        "--param",
        f"ENABLE_REF={export_env['ENABLE_REF']}",
        "--param",
        f"AST_MODE={export_env['AST_MODE']}",
        "--param",
        f"ARRAY_DELIM={export_env['ARRAY_DELIM']}",
    ]
    export_command_text = _command_to_text(export_cmd)
    append_log(
        "ANALYZE",
        (
            "[joern] 执行 export 命令: "
            f"command={export_command_text}, script={export_script}, "
            f"cpg_file={context.cpg_file}, import_dir={context.import_dir}"
        ),
    )
    export_result = _run_command_with_deadline(
        export_cmd,
        deadline=deadline,
        env=export_env,
        cwd=joern_runtime_dir,
    )
    if export_result.returncode != 0:
        export_stdout_tail = _tail_text(export_result.stdout)
        export_stderr_tail = _tail_text(export_result.stderr)
        append_log(
            "ANALYZE",
            (
                f"[joern] export 失败: exit_code={export_result.returncode}, "
                f"command={export_command_text}, script={export_script}, "
                f"cpg_file={context.cpg_file}, import_dir={context.import_dir}, "
                f"stdout_tail={export_stdout_tail}, stderr_tail={export_stderr_tail}"
            ),
        )
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="Joern 导出执行失败",
            detail={
                "exit_code": export_result.returncode,
                "command": export_cmd,
                "source_dir": str(context.source_dir),
                "cpg_file": str(context.cpg_file),
                "import_dir": str(context.import_dir),
                "export_script": str(export_script),
                "stdout_tail": export_stdout_tail,
                "stderr_tail": export_stderr_tail,
            },
        )

    nodes, rels = _collect_csv_pairs(
        context.import_dir, failure_code="SCAN_EXTERNAL_JOERN_FAILED"
    )
    missing_required_files = _find_missing_required_csv_files(context.import_dir)
    if missing_required_files:
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="Joern 导出关键 CSV 产物缺失",
            detail={
                "source_dir": str(context.source_dir),
                "cpg_file": str(context.cpg_file),
                "import_dir": str(context.import_dir),
                "export_script": str(export_script),
                "missing_files": missing_required_files,
            },
        )

    export_stdout_tail = _tail_text(export_result.stdout)
    export_stderr_tail = _tail_text(export_result.stderr)
    append_log(
        "ANALYZE",
        (
            "[joern] 导出完成: "
            f"command={export_command_text}, script={export_script}, "
            f"cpg_file={context.cpg_file}, import_dir={context.import_dir}, "
            f"stdout_tail={export_stdout_tail}, stderr_tail={export_stderr_tail}, "
            f"nodes={len(nodes)}, relationships={len(rels)}"
        ),
    )
    stdout = "\n".join(
        [
            _tail_text(parse_result.stdout),
            _tail_text(export_result.stdout),
            f"nodes={len(nodes)} rels={len(rels)}",
        ]
    ).strip()
    stderr = "\n".join(
        [_tail_text(parse_result.stderr), _tail_text(export_result.stderr)]
    ).strip()
    return stdout, stderr


def _run_builtin_neo4j_import(
    *,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    deadline: float,
) -> tuple[str, str]:
    _ensure_docker_cli_available()
    image = str(settings.scan_external_import_docker_image or "").strip()
    data_mount_raw = (
        str(context.base_env.get("CODESCOPE_SCAN_IMPORT_DATA_MOUNT") or "").strip()
        or str(settings.scan_external_import_data_mount or "").strip()
    )
    database = (
        str(context.base_env.get("CODESCOPE_SCAN_IMPORT_DATABASE") or "").strip()
        or str(context.base_env.get("CODESCOPE_SCAN_NEO4J_DATABASE") or "").strip()
        or str(settings.scan_external_import_database or "").strip()
        or str(settings.scan_external_neo4j_database or "").strip()
        or "neo4j"
    )
    if not image:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 导入镜像",
            detail={"required": "scan_external_import_docker_image"},
        )
    if not data_mount_raw:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j data 挂载点",
            detail={"required": "scan_external_import_data_mount"},
        )

    nodes, rels = _collect_csv_pairs(
        context.import_dir, failure_code="SCAN_EXTERNAL_IMPORT_FAILED"
    )
    if not nodes and not rels:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="导入目录中未找到 CSV 文件",
            detail={"import_dir": str(context.import_dir)},
        )

    runtime_profile = _resolve_runtime_profile(context=context)
    import_host = _resolve_import_host_mount_path(
        context=context, runtime_profile=runtime_profile
    )
    data_mount = _resolve_data_mount(data_mount_raw)

    if bool(settings.scan_external_import_preflight):
        if bool(getattr(settings, "scan_external_import_preflight_check_docker", True)):
            _preflight_check_docker_daemon(deadline=deadline)
        _preflight_check_import_mount(import_host=import_host, deadline=deadline)

    restart_mode = (
        str(settings.scan_external_neo4j_runtime_restart_mode or "none").strip().lower()
    )
    runtime_container_name = (
        str(
            context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME") or ""
        ).strip()
        or str(settings.scan_external_neo4j_runtime_container_name or "").strip()
    )
    runtime_network = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK") or "").strip()
        or str(
            getattr(settings, "scan_external_neo4j_runtime_network", "") or ""
        ).strip()
    )
    runtime_network_alias = (
        str(
            context.base_env.get("CODESCOPE_SCAN_NEO4J_RUNTIME_NETWORK_ALIAS") or ""
        ).strip()
        or str(
            getattr(settings, "scan_external_neo4j_runtime_network_alias", "") or ""
        ).strip()
    )
    runtime_network_auto_create = bool(
        getattr(settings, "scan_external_neo4j_runtime_network_auto_create", False)
    )
    restart_wait_seconds = max(
        0, int(settings.scan_external_neo4j_runtime_restart_wait_seconds or 0)
    )
    runtime_uri = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_URI") or "").strip()
        or str(getattr(settings, "scan_external_neo4j_uri", "") or "").strip()
    )
    runtime_user = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_USER") or "").strip()
        or str(getattr(settings, "scan_external_neo4j_user", "") or "").strip()
    )
    runtime_password = (
        str(context.base_env.get("CODESCOPE_SCAN_NEO4J_PASSWORD") or "").strip()
        or str(getattr(settings, "scan_external_neo4j_password", "") or "").strip()
    )
    manage_runtime = restart_mode == "docker" and bool(runtime_container_name)
    manage_ephemeral_runtime = restart_mode == DOCKER_EPHEMERAL_RUNTIME_MODE and bool(
        runtime_container_name
    )
    import_runtime_container_name = _runtime_container_name_for_phase(
        runtime_container_name, phase="import"
    )
    query_runtime_container_name = _runtime_container_name_for_phase(
        runtime_container_name, phase="query"
    )
    runtime_container_exists = False
    was_running = False

    if manage_runtime:
        runtime_container_exists = _container_exists(
            container_name=runtime_container_name, deadline=deadline
        )
        if runtime_container_exists:
            was_running = _is_container_running(
                container_name=runtime_container_name, deadline=deadline
            )
            if was_running:
                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 停止运行中的 Neo4j 容器: {runtime_container_name}",
                )
                _stop_container(
                    container_name=runtime_container_name, deadline=deadline
                )
            else:
                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 导入前 Neo4j 容器未运行，导入后将启动: {runtime_container_name}",
                )
        else:
            append_log(
                "ANALYZE",
                f"[neo4j_import] 导入前 Neo4j 容器不存在，导入后将创建并启动: {runtime_container_name}",
            )
    elif manage_ephemeral_runtime:
        for stale_container in (
            import_runtime_container_name,
            query_runtime_container_name,
        ):
            if not stale_container:
                continue
            if _container_exists(container_name=stale_container, deadline=deadline):
                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 清理历史任务 Neo4j 容器: {stale_container}",
                )
                _remove_container(
                    container_name=stale_container,
                    deadline=deadline,
                    ignore_missing=True,
                )

    import_error: AppError | None = None
    import_result: subprocess.CompletedProcess[str] | None = None
    restart_error: AppError | None = None
    ephemeral_runtime_metadata: dict[str, object] = {}
    try:
        major = _detect_neo4j_major(image=image, deadline=deadline)
        admin_parts = _build_admin_parts(
            major=major,
            database=database,
            clean_db=bool(settings.scan_external_import_clean_db),
            id_type=str(settings.scan_external_import_id_type or "").strip().lower(),
            multiline_fields=bool(settings.scan_external_import_multiline_fields),
            multiline_fields_format=str(
                settings.scan_external_import_multiline_fields_format or ""
            ).strip(),
            array_delimiter=str(
                settings.scan_external_import_array_delimiter or "\\001"
            ),
            nodes=nodes,
            rels=rels,
        )

        resolver = _neo4j_admin_resolver_shell()
        admin_cmd = f"{resolver}; {' '.join(admin_parts)}"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-t",
            "-v",
            f"{data_mount}:/data",
            "-v",
            f"{import_host}:/import:ro",
            image,
            "bash",
            "-lc",
            admin_cmd,
        ]
        append_log(
            "ANALYZE",
            (
                "[neo4j_import] 执行导入命令: "
                f"image={image}, database={database}, data_mount={data_mount}, "
                f"import_host={import_host}, command={_command_to_text(docker_cmd)}"
            ),
        )
        import_result = _run_command_with_deadline(docker_cmd, deadline=deadline)
        if import_result.returncode != 0:
            import_stdout_tail = _tail_text(import_result.stdout)
            import_stderr_tail = _tail_text(import_result.stderr)
            append_log(
                "ANALYZE",
                (
                    "[neo4j_import] 导入失败: "
                    f"exit_code={import_result.returncode}, image={image}, "
                    f"database={database}, data_mount={data_mount}, "
                    f"import_host={import_host}, command={_command_to_text(docker_cmd)}, "
                    f"stdout_tail={import_stdout_tail}, stderr_tail={import_stderr_tail}"
                ),
            )
            raise AppError(
                code="SCAN_EXTERNAL_IMPORT_FAILED",
                status_code=422,
                message="neo4j-admin import 执行失败",
                detail={
                    "exit_code": import_result.returncode,
                    "command": docker_cmd,
                    "image": image,
                    "database": database,
                    "data_mount": data_mount,
                    "import_host": import_host,
                    "failure_kind": "neo4j_admin_import_failed",
                    "stdout_tail": import_stdout_tail,
                    "stderr_tail": import_stderr_tail,
                },
            )
    except AppError as exc:
        import_error = exc
    finally:
        if manage_runtime:
            try:
                should_start_existing = runtime_container_exists and (
                    was_running or import_error is None
                )
                should_create_runtime = (
                    not runtime_container_exists and import_error is None
                )
                if should_start_existing:
                    action = "重启" if was_running else "启动"
                    append_log(
                        "ANALYZE",
                        f"[neo4j_import] {action} Neo4j 容器: {runtime_container_name}",
                    )
                    _start_container(
                        container_name=runtime_container_name, deadline=deadline
                    )
                elif should_create_runtime:
                    append_log(
                        "ANALYZE",
                        f"[neo4j_import] 创建并启动 Neo4j 运行时容器: {runtime_container_name}",
                    )
                    _run_ephemeral_runtime_container(
                        image=image,
                        container_name=runtime_container_name,
                        data_mount=data_mount,
                        uri=runtime_uri,
                        password=runtime_password,
                        network=runtime_network,
                        network_alias=runtime_network_alias,
                        network_auto_create=runtime_network_auto_create,
                        runtime_phase="runtime",
                        deadline=deadline,
                    )
                if restart_wait_seconds > 0:
                    sleep_seconds = min(
                        restart_wait_seconds, _remaining_seconds(deadline)
                    )
                    time.sleep(max(0, sleep_seconds))
                if import_error is None and (
                    should_start_existing or should_create_runtime
                ):
                    _wait_for_ephemeral_runtime_ready(
                        container_name=runtime_container_name,
                        uri=runtime_uri,
                        user=runtime_user,
                        password=runtime_password,
                        connect_retry=int(
                            getattr(settings, "scan_external_neo4j_connect_retry", 15)
                        ),
                        connect_wait_seconds=int(
                            getattr(
                                settings,
                                "scan_external_neo4j_connect_wait_seconds",
                                2,
                            )
                        ),
                        deadline=deadline,
                    )
                    append_log(
                        "ANALYZE",
                        f"[neo4j_import] Neo4j 运行时就绪: {runtime_container_name}, uri={runtime_uri}",
                    )
            except Exception as exc:
                restart_error = AppError(
                    code="SCAN_EXTERNAL_IMPORT_FAILED",
                    status_code=422,
                    message="Neo4j 运行时重启失败",
                    detail={
                        "container_name": runtime_container_name,
                        "error": str(exc),
                    },
                )
        elif manage_ephemeral_runtime and import_error is None:
            try:
                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 启动导入阶段 Neo4j 容器: {import_runtime_container_name}",
                )
                import_runtime_metadata = _run_ephemeral_runtime_container(
                    image=image,
                    container_name=import_runtime_container_name,
                    data_mount=data_mount,
                    uri=runtime_uri,
                    password=runtime_password,
                    network=runtime_network,
                    network_alias=runtime_network_alias,
                    network_auto_create=runtime_network_auto_create,
                    runtime_phase="import",
                    deadline=deadline,
                )
                ephemeral_runtime_metadata = dict(import_runtime_metadata)
                if restart_wait_seconds > 0:
                    sleep_seconds = min(
                        restart_wait_seconds, _remaining_seconds(deadline)
                    )
                    time.sleep(max(0, sleep_seconds))
                _wait_for_container_running(
                    container_name=str(
                        import_runtime_metadata.get("container_name") or ""
                    ),
                    retry=int(
                        getattr(settings, "scan_external_neo4j_connect_retry", 15)
                    ),
                    wait_seconds=int(
                        getattr(settings, "scan_external_neo4j_connect_wait_seconds", 2)
                    ),
                    deadline=deadline,
                )
                append_log(
                    "ANALYZE",
                    (
                        "[neo4j_import] 导入阶段 Neo4j 容器已运行: "
                        f"{import_runtime_metadata.get('container_name')}, "
                        f"uri={import_runtime_metadata.get('uri')}"
                    ),
                )
                cleanup_ephemeral_runtime_resources(
                    container_name=str(
                        import_runtime_metadata.get("container_name") or ""
                    )
                    or None,
                    data_mount=None,
                    network_name=None,
                    cleanup_network=False,
                    deadline=deadline,
                )
                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 导入阶段 Neo4j 容器已销毁: {import_runtime_container_name}",
                )

                append_log(
                    "ANALYZE",
                    f"[neo4j_import] 启动查询阶段 Neo4j 容器: {query_runtime_container_name}",
                )
                ephemeral_runtime_metadata = _run_ephemeral_runtime_container(
                    image=image,
                    container_name=query_runtime_container_name,
                    data_mount=data_mount,
                    uri=runtime_uri,
                    password=runtime_password,
                    network=runtime_network,
                    network_alias=runtime_network_alias,
                    network_auto_create=runtime_network_auto_create,
                    runtime_phase="query",
                    deadline=deadline,
                )
                if restart_wait_seconds > 0:
                    sleep_seconds = min(
                        restart_wait_seconds, _remaining_seconds(deadline)
                    )
                    time.sleep(max(0, sleep_seconds))
                query_runtime_uri = str(
                    ephemeral_runtime_metadata.get("uri") or runtime_uri
                )
                _wait_for_ephemeral_runtime_ready(
                    container_name=str(
                        ephemeral_runtime_metadata.get("container_name") or ""
                    ),
                    uri=query_runtime_uri,
                    user=runtime_user,
                    password=runtime_password,
                    connect_retry=int(
                        getattr(settings, "scan_external_neo4j_connect_retry", 15)
                    ),
                    connect_wait_seconds=int(
                        getattr(
                            settings,
                            "scan_external_neo4j_connect_wait_seconds",
                            2,
                        )
                    ),
                    deadline=deadline,
                )
                context.base_env["CODESCOPE_SCAN_NEO4J_URI"] = query_runtime_uri
                context.base_env["CODESCOPE_SCAN_NEO4J_RUNTIME_CONTAINER_NAME"] = str(
                    ephemeral_runtime_metadata.get("container_name")
                    or query_runtime_container_name
                )
                if ephemeral_runtime_metadata:
                    write_runtime_metadata(
                        reports_dir=context.reports_dir,
                        payload=ephemeral_runtime_metadata,
                    )
                append_log(
                    "ANALYZE",
                    (
                        "[neo4j_import] 查询阶段 Neo4j 容器就绪: "
                        f"{ephemeral_runtime_metadata.get('container_name')}, "
                        f"uri={query_runtime_uri}"
                    ),
                )
            except Exception as exc:
                cleanup_detail: dict[str, object] = {}
                try:
                    cleanup_detail = cleanup_ephemeral_runtime_resources(
                        container_name=str(
                            ephemeral_runtime_metadata.get("container_name")
                            or query_runtime_container_name
                            or import_runtime_container_name
                        )
                        or None,
                        data_mount=data_mount,
                        network_name=str(
                            ephemeral_runtime_metadata.get("network") or ""
                        )
                        or None,
                        cleanup_network=bool(
                            ephemeral_runtime_metadata.get("network_created_by_job")
                        ),
                        deadline=deadline,
                    )
                except Exception as cleanup_exc:
                    cleanup_detail = {"cleanup_error": str(cleanup_exc)}
                restart_error = AppError(
                    code="SCAN_EXTERNAL_IMPORT_FAILED",
                    status_code=422,
                    message="Neo4j 任务级运行时启动失败",
                    detail={
                        "container_name": str(
                            ephemeral_runtime_metadata.get("container_name")
                            or query_runtime_container_name
                            or import_runtime_container_name
                        ),
                        "error": str(exc),
                        "runtime_cleanup": cleanup_detail,
                    },
                )

    if import_error is not None:
        if restart_error is not None:
            detail = (
                dict(import_error.detail)
                if isinstance(import_error.detail, dict)
                else {}
            )
            detail["runtime_restart_error"] = restart_error.detail
            raise AppError(
                code=import_error.code,
                status_code=import_error.status_code,
                message=import_error.message,
                detail=detail,
            )
        raise import_error
    if restart_error is not None:
        raise restart_error

    if import_result is None:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="neo4j-admin import 未返回执行结果",
        )

    append_log(
        "ANALYZE",
        f"[neo4j_import] 导入完成: nodes={len(nodes)}, relationships={len(rels)}, database={database}",
    )
    return _tail_text(import_result.stdout), _tail_text(import_result.stderr)


def _run_builtin_post_labels(
    *,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
) -> tuple[str, str]:
    post_labels_path = Path(
        context.base_env.get("CODESCOPE_SCAN_POST_LABELS_CYPHER") or ""
    )
    cypher_files = _resolve_post_labels_files(post_labels_path)

    script_results: list[dict[str, object]] = []
    total_statements = 0
    total_rows = 0
    total_scripts = len(cypher_files)

    for index, cypher_file in enumerate(cypher_files, start=1):
        append_log(
            "QUERY",
            f"[post_labels] 开始执行脚本 {index}/{total_scripts}: {cypher_file.name}",
        )
        started = time.monotonic()
        try:
            summary = execute_cypher_file(
                cypher_file=cypher_file,
                uri=(
                    str(context.base_env.get("CODESCOPE_SCAN_NEO4J_URI") or "").strip()
                    or str(settings.scan_external_neo4j_uri or "").strip()
                ),
                user=(
                    str(context.base_env.get("CODESCOPE_SCAN_NEO4J_USER") or "").strip()
                    or str(settings.scan_external_neo4j_user or "").strip()
                ),
                password=(
                    str(
                        context.base_env.get("CODESCOPE_SCAN_NEO4J_PASSWORD") or ""
                    ).strip()
                    or str(settings.scan_external_neo4j_password or "").strip()
                ),
                database=(
                    str(
                        context.base_env.get("CODESCOPE_SCAN_NEO4J_DATABASE") or ""
                    ).strip()
                    or str(settings.scan_external_neo4j_database or "").strip()
                    or "neo4j"
                ),
                connect_retry=int(settings.scan_external_neo4j_connect_retry),
                connect_wait_seconds=int(
                    settings.scan_external_neo4j_connect_wait_seconds
                ),
            )
        except AppError as exc:
            if exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED":
                raise
            detail = dict(exc.detail) if isinstance(exc.detail, dict) else {}
            detail.update(
                {
                    "script_name": cypher_file.name,
                    "script_path": str(cypher_file),
                    "script_index": index,
                    "script_count": total_scripts,
                }
            )
            raise AppError(
                code="SCAN_EXTERNAL_POST_LABELS_FAILED",
                status_code=422,
                message="post_labels 执行失败",
                detail=detail,
            ) from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        total_statements += summary.statement_count
        total_rows += summary.total_rows
        script_results.append(
            {
                "script": cypher_file.name,
                "statement_count": summary.statement_count,
                "total_rows": summary.total_rows,
                "duration_ms": duration_ms,
            }
        )
        append_log(
            "QUERY",
            (
                f"[post_labels] 脚本执行完成 {index}/{total_scripts}: {cypher_file.name}, "
                f"statements={summary.statement_count}, total_rows={summary.total_rows}, "
                f"duration_ms={duration_ms}"
            ),
        )

    payload = {
        "scripts": script_results,
        "script_count": total_scripts,
        "statement_count": total_statements,
        "total_rows": total_rows,
    }
    message = (
        f"[post_labels] 执行完成: scripts={total_scripts}, "
        f"statements={total_statements}, total_rows={total_rows}"
    )
    append_log("QUERY", message)
    return json.dumps(payload, ensure_ascii=False), ""


def _compute_rule_query_timeout_seconds(
    *, deadline: float | None, remaining_rules: int
) -> int | None:
    if deadline is None:
        return None
    remaining_seconds = max(1, int(deadline - time.monotonic()))
    safe_remaining_rules = max(1, int(remaining_rules))
    per_rule_budget = max(1, remaining_seconds // safe_remaining_rules)
    return max(5, min(60, per_rule_budget))


def _run_builtin_rules(
    *,
    job: Job,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    deadline: float | None = None,
    on_rule_finding: Callable[[dict[str, object]], None] | None = None,
) -> tuple[str, str]:
    rules_dir = Path(context.base_env.get("CODESCOPE_SCAN_RULES_DIR") or "")
    if not rules_dir.exists() or not rules_dir.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="规则目录不存在",
            detail={"rules_dir": str(rules_dir)},
        )

    requested_rule_names = _normalize_requested_rule_names(
        job.payload.get("resolved_rule_keys")
    )
    if not requested_rule_names:
        requested_rule_names = _normalize_requested_rule_names(
            job.payload.get("rule_keys")
        )
    if requested_rule_names:
        rule_files, missing_rules, disabled_rules = resolve_runtime_rule_files(
            requested_rule_names=requested_rule_names,
            rules_dir=rules_dir,
        )
        if missing_rules:
            raise AppError(
                code="SCAN_EXTERNAL_RULES_FAILED",
                status_code=422,
                message="规则执行阶段存在未知规则名",
                detail={"missing_rules": missing_rules},
            )
        if disabled_rules:
            raise AppError(
                code="SCAN_EXTERNAL_RULES_FAILED",
                status_code=422,
                message="规则执行阶段包含已停用规则",
                detail={"disabled_rules": disabled_rules},
            )
    else:
        rule_files = _list_rule_files(rules_dir=rules_dir)

    max_count = int(getattr(settings, "scan_external_rules_max_count", 0) or 0)
    if max_count > 0:
        rule_files = rule_files[:max_count]
    if not rule_files:
        raise AppError(
            code="SCAN_EXTERNAL_RULES_FAILED",
            status_code=422,
            message="未找到可执行规则文件",
            detail={"rules_dir": str(rules_dir)},
        )

    failure_mode = _normalize_rules_failure_mode(
        getattr(settings, "scan_external_rules_failure_mode", "permissive")
    )
    rule_rows: dict[str, int] = {}
    partial_failures: list[dict[str, object]] = []
    rule_results: list[dict[str, object]] = []
    succeeded_rule_count = 0
    total_rule_count = len(rule_files)
    emitted_finding_count = 0
    for index, rule_file in enumerate(rule_files, start=1):
        rule_key = _rule_key_from_file(rule_file)
        seen_case_fingerprints: set[str] = set()
        query_timeout_seconds = _compute_rule_query_timeout_seconds(
            deadline=deadline,
            remaining_rules=(total_rule_count - index + 1),
        )
        append_log(
            "QUERY",
            (
                f"[rules] 开始执行规则 {index}/{total_rule_count}: {rule_key}"
                + (
                    f", query_timeout_s={query_timeout_seconds}"
                    if query_timeout_seconds is not None
                    else ""
                )
            ),
        )
        started = time.monotonic()
        try:

            def _on_rule_record(record: dict[str, object]) -> None:
                nonlocal emitted_finding_count
                finding_hit = _build_finding_from_rule_record(
                    rule_key=rule_key,
                    record=record,
                )
                if finding_hit is None:
                    return
                if not _allow_finding_hit_for_rule(rule_key, finding_hit):
                    return
                fingerprint = _finding_hit_fingerprint(rule_key, finding_hit)
                if fingerprint in seen_case_fingerprints:
                    return
                seen_case_fingerprints.add(fingerprint)
                emitted_finding_count += 1
                if on_rule_finding is not None:
                    on_rule_finding(finding_hit)

            summary = execute_cypher_file_stream(
                cypher_file=rule_file,
                uri=(
                    str(context.base_env.get("CODESCOPE_SCAN_NEO4J_URI") or "").strip()
                    or str(settings.scan_external_neo4j_uri or "").strip()
                ),
                user=(
                    str(context.base_env.get("CODESCOPE_SCAN_NEO4J_USER") or "").strip()
                    or str(settings.scan_external_neo4j_user or "").strip()
                ),
                password=(
                    str(
                        context.base_env.get("CODESCOPE_SCAN_NEO4J_PASSWORD") or ""
                    ).strip()
                    or str(settings.scan_external_neo4j_password or "").strip()
                ),
                database=(
                    str(
                        context.base_env.get("CODESCOPE_SCAN_NEO4J_DATABASE") or ""
                    ).strip()
                    or str(settings.scan_external_neo4j_database or "").strip()
                    or "neo4j"
                ),
                connect_retry=int(settings.scan_external_neo4j_connect_retry),
                connect_wait_seconds=int(
                    settings.scan_external_neo4j_connect_wait_seconds
                ),
                query_timeout_seconds=query_timeout_seconds,
                query_metadata={
                    "codescope_stage": "rules",
                    "codescope_job_id": str(getattr(job, "id", "") or ""),
                    "codescope_rule": rule_key,
                    "codescope_rule_index": index,
                    "codescope_rule_count": total_rule_count,
                },
                on_record=_on_rule_record,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            rule_rows[rule_key] = summary.total_rows
            succeeded_rule_count += 1
            rule_results.append(
                {
                    "rule": rule_key,
                    "status": "succeeded",
                    "rows": summary.total_rows,
                    "duration_ms": duration_ms,
                    "error_code": None,
                    "message": None,
                }
            )
            append_log(
                "QUERY",
                (
                    f"[rules] 规则执行完成 {index}/{total_rule_count}: {rule_key}, "
                    f"rows={summary.total_rows}, duration_ms={duration_ms}"
                ),
            )
        except AppError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            if exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED":
                raise
            if failure_mode == "strict":
                raise AppError(
                    code="SCAN_EXTERNAL_RULES_FAILED",
                    status_code=422,
                    message="规则执行失败（strict 模式）",
                    detail={
                        "failure_mode": failure_mode,
                        "failed_rule": rule_key,
                        "error_code": exc.code,
                        "error_message": exc.message,
                        "partial_failures": [],
                        "succeeded_rules": succeeded_rule_count,
                        "failed_rules": 1,
                        "duration_ms": duration_ms,
                    },
                ) from exc
            rule_rows[rule_key] = 0
            failure_detail = {
                "rule": rule_key,
                "error_code": exc.code,
                "message": exc.message,
                "duration_ms": duration_ms,
            }
            partial_failures.append(failure_detail)
            rule_results.append(
                {
                    "rule": rule_key,
                    "status": "failed",
                    "rows": 0,
                    "duration_ms": duration_ms,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
            detail_text = ""
            if isinstance(exc.detail, dict):
                error_text = str(exc.detail.get("error") or "").strip()
                cypher_file_text = str(exc.detail.get("cypher_file") or "").strip()
                detail_parts = [
                    part
                    for part in [
                        f"error={error_text}" if error_text else "",
                        f"cypher_file={cypher_file_text}" if cypher_file_text else "",
                    ]
                    if part
                ]
                if detail_parts:
                    detail_text = ", " + ", ".join(detail_parts)
            append_log(
                "QUERY",
                (
                    f"[rules] 规则执行失败 {index}/{total_rule_count}: {rule_key}, "
                    f"error_code={exc.code}, duration_ms={duration_ms}{detail_text}"
                ),
            )

    if succeeded_rule_count == 0 and partial_failures:
        raise AppError(
            code="SCAN_EXTERNAL_RULES_FAILED",
            status_code=422,
            message="规则执行全部失败",
            detail={
                "failed_rules": len(partial_failures),
                "sample_error": partial_failures[0],
            },
        )

    rule_summary = _summarize_rule_rows(rule_rows)
    failed_rule_keys = [
        str(item.get("rule") or "")
        for item in partial_failures
        if str(item.get("rule") or "")
    ]
    execution_summary = {
        "total_rules": total_rule_count,
        "executed_rules": len(rule_rows),
        "succeeded_rules": succeeded_rule_count,
        "failed_rules": len(partial_failures),
        "failed_rule_keys": failed_rule_keys,
        "failure_mode": failure_mode,
        "has_partial_failures": bool(partial_failures),
        "partial_failure_effect": (
            "continued" if failure_mode == "permissive" and partial_failures else "none"
        ),
    }
    round_report = {
        "round": 1,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "rule_rows": rule_rows,
        "rule_summary": rule_summary,
        "rule_results": rule_results,
        "partial_failures": partial_failures,
        "execution_summary": execution_summary,
    }
    report_path = context.reports_dir / "round_1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(round_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    append_log(
        "QUERY",
        (
            "[rules] 执行完成: "
            f"total_rules={rule_summary['total_rules']}, "
            f"hit_rules={rule_summary['hit_rules']}, "
            f"succeeded_rules={execution_summary['succeeded_rules']}, "
            f"failed_rules={execution_summary['failed_rules']}, "
            f"partial_failures={len(partial_failures)}"
        ),
    )
    stdout = json.dumps(
        {
            "report_path": str(report_path),
            "total_rules": rule_summary["total_rules"],
            "hit_rules": rule_summary["hit_rules"],
            "succeeded_rules": execution_summary["succeeded_rules"],
            "failed_rules": execution_summary["failed_rules"],
            "failed_rule_keys": execution_summary["failed_rule_keys"],
            "partial_failures": len(partial_failures),
            "partial_failure_effect": execution_summary["partial_failure_effect"],
            "emitted_findings": emitted_finding_count,
            "rule_results": rule_results,
        },
        ensure_ascii=False,
    )
    return stdout, ""


def _build_finding_from_rule_record(
    *, rule_key: str, record: dict[str, object]
) -> dict[str, object] | None:
    candidate = _select_rule_record_candidate(record)
    if not isinstance(candidate, dict):
        return None
    kind = str(candidate.get("kind") or "").strip().lower()
    if kind == "path":
        return _build_path_finding(rule_key=rule_key, path_payload=candidate)
    if kind == "node":
        return _build_node_finding(rule_key=rule_key, node_payload=candidate)
    return None


def _select_rule_record_candidate(
    record: dict[str, object],
) -> dict[str, object] | None:
    preferred = record.get("path")
    if isinstance(preferred, dict):
        return preferred
    for value in record.values():
        if isinstance(value, dict) and str(value.get("kind") or "") in {"path", "node"}:
            return value
    return None


def _build_path_finding(
    *, rule_key: str, path_payload: dict[str, object]
) -> dict[str, object] | None:
    nodes = path_payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    node_items = [
        _build_path_node_payload(node_payload=item, index=index)
        for index, item in enumerate(nodes)
        if isinstance(item, dict)
    ]
    if not node_items:
        return None
    steps = [build_path_step_payload(node) for node in node_items]
    edges = _build_path_edge_payloads(
        edge_payloads=path_payload.get("edges"),
        nodes=node_items,
    )
    if not edges:
        edges = build_linear_path_edges(node_items)
    if not steps:
        return None
    source = steps[0]
    sink = steps[-1]
    sink_file = str(sink.get("file") or "").strip() or None
    source_file = str(source.get("file") or "").strip() or None
    sink_line = _safe_int(sink.get("line"))
    source_line = _safe_int(source.get("line"))
    location_file = sink_file or source_file
    location_line = sink_line if sink_line is not None else source_line
    return {
        "rule_key": rule_key,
        "file_path": location_file,
        "line_start": location_line,
        "line_end": location_line,
        "source_file": source_file,
        "source_line": source_line,
        "sink_file": sink_file,
        "sink_line": sink_line,
        "has_path": True,
        "path_length": max(0, len(edges) or (len(steps) - 1)),
        "evidence": {
            "match_kind": "path",
            "path_nodes": len(steps),
            "path_edges": len(edges),
            "edge_types": list(
                dict.fromkeys(
                    str(edge.get("edge_type") or "")
                    for edge in edges
                    if edge.get("edge_type")
                )
            ),
            "labels": list(
                dict.fromkeys(label for step in steps for label in step["labels"])
            ),
        },
        "paths": [
            {
                "path_length": max(0, len(edges) or (len(steps) - 1)),
                "steps": steps,
                "nodes": node_items,
                "edges": edges,
            }
        ],
    }


def _build_node_finding(
    *, rule_key: str, node_payload: dict[str, object]
) -> dict[str, object]:
    props = (
        node_payload.get("props") if isinstance(node_payload.get("props"), dict) else {}
    )
    file_path = str(props.get("file") or "").strip() or None
    line_no = _safe_int(props.get("line"))
    return {
        "rule_key": rule_key,
        "file_path": file_path,
        "line_start": line_no,
        "line_end": line_no,
        "source_file": None,
        "source_line": None,
        "sink_file": file_path,
        "sink_line": line_no,
        "has_path": False,
        "path_length": None,
        "evidence": {
            "match_kind": "node",
            "labels": list(node_payload.get("labels") or []),
            "node_ref": str(node_payload.get("node_ref") or "node"),
        },
        "paths": [],
    }


def _build_path_node_payload(
    *, node_payload: dict[str, object], index: int
) -> dict[str, object]:
    props = (
        node_payload.get("props") if isinstance(node_payload.get("props"), dict) else {}
    )
    labels = [str(item) for item in node_payload.get("labels") or [] if str(item)]
    node_ref = str(node_payload.get("node_ref") or f"node-{index}")
    return build_trace_node_payload(
        index=index,
        labels=labels,
        props=props,
        node_ref=node_ref,
    )


def _build_path_edge_payloads(
    *, edge_payloads: object, nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    if not isinstance(edge_payloads, list):
        return []
    node_index_by_ref = {
        str(node.get("node_ref") or ""): int(node.get("node_id") or 0)
        for node in nodes
        if str(node.get("node_ref") or "")
    }
    edges: list[dict[str, object]] = []
    for index, item in enumerate(edge_payloads):
        if not isinstance(item, dict):
            continue
        props = item.get("props") if isinstance(item.get("props"), dict) else {}
        from_node_ref = str(item.get("from_node_ref") or "").strip() or None
        to_node_ref = str(item.get("to_node_ref") or "").strip() or None
        edges.append(
            build_path_edge_payload(
                index=index,
                edge_type=str(item.get("type") or "").strip() or None,
                from_node_id=node_index_by_ref.get(from_node_ref or ""),
                to_node_id=node_index_by_ref.get(to_node_ref or ""),
                from_node_ref=from_node_ref,
                to_node_ref=to_node_ref,
                props=props,
                edge_ref=str(item.get("edge_ref") or "").strip() or None,
            )
        )
    return edges


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_bool_flag(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _run_command_with_deadline(
    command: list[str],
    *,
    deadline: float,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    timeout = _remaining_seconds(deadline)
    prepared = _prepare_command(command)
    try:
        return subprocess.run(
            prepared,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            env=env,
            cwd=str(cwd) if cwd is not None else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc


def _prepare_command(command: list[str]) -> list[str]:
    if not command:
        return command
    if os.name == "nt" and command[0].lower().endswith(".bat"):
        return ["cmd", "/c", *command]
    return command


def _remaining_seconds(deadline: float) -> int:
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError("stage deadline exceeded")
    return remaining


def _clear_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return
    for child in path.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)


def _collect_csv_pairs(
    import_dir: Path,
    *,
    failure_code: str,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    nodes: list[tuple[str, str, str]] = []
    rels: list[tuple[str, str, str]] = []

    for header in import_dir.glob("nodes_*_header.csv"):
        match = NODE_HEADER_RE.match(header.name)
        if match is None:
            continue
        label = match.group(1)
        data = import_dir / f"nodes_{label}_data.csv"
        if not data.exists():
            raise AppError(
                code=failure_code,
                status_code=422,
                message="节点 CSV 缺少 data 文件",
                detail={"header": str(header), "data": str(data)},
            )
        nodes.append((label, header.name, data.name))

    for header in import_dir.glob("edges_*_header.csv"):
        match = EDGE_HEADER_RE.match(header.name)
        if match is None:
            continue
        rel_type = match.group(1)
        data = import_dir / f"edges_{rel_type}_data.csv"
        if not data.exists():
            raise AppError(
                code=failure_code,
                status_code=422,
                message="关系 CSV 缺少 data 文件",
                detail={"header": str(header), "data": str(data)},
            )
        rels.append((rel_type, header.name, data.name))

    nodes.sort(key=lambda item: item[0].lower())
    rels.sort(key=lambda item: item[0].lower())
    return nodes, rels


def _find_missing_required_csv_files(import_dir: Path) -> list[str]:
    return [
        name for name in REQUIRED_JOERN_EXPORT_FILES if not (import_dir / name).exists()
    ]


def _resolve_post_labels_files(post_labels_path: Path) -> list[Path]:
    if not post_labels_path.exists():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="post_labels Cypher 文件不存在",
            detail={"post_labels_cypher": str(post_labels_path)},
        )
    if post_labels_path.is_file():
        return [post_labels_path]
    if not post_labels_path.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="post_labels 路径不是文件或目录",
            detail={"post_labels_cypher": str(post_labels_path)},
        )

    cypher_files = sorted(
        [item for item in post_labels_path.glob("*.cypher") if item.is_file()],
        key=lambda item: item.name.lower(),
    )
    if not cypher_files:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="post_labels 目录中不存在可执行脚本",
            detail={"post_labels_cypher": str(post_labels_path)},
        )
    return cypher_files


def _resolve_joern_binary(
    *, joern_home: Path, windows_name: str, unix_name: str
) -> Path:
    if os.name == "nt":
        windows_candidate = joern_home / windows_name
        if windows_candidate.exists() and windows_candidate.is_file():
            return windows_candidate
    linux_candidate = joern_home / unix_name
    if linux_candidate.exists() and linux_candidate.is_file():
        return linux_candidate
    if os.name == "nt":
        return joern_home / windows_name
    return linux_candidate


def _normalize_host_path_for_docker(path_text: str) -> str:
    return path_text.strip().strip('"').replace("\\", "/")


def _resolve_import_host_mount_path(
    *, context: ExternalScanContext, runtime_profile: str
) -> str:
    configured = str(
        context.base_env.get("CODESCOPE_SCAN_IMPORT_HOST_PATH") or ""
    ).strip()
    raw_path = configured or str(context.import_dir.resolve())
    normalized_path = _normalize_host_path_for_docker(raw_path)
    if (
        runtime_profile == WSL_RUNTIME_PROFILE
        and normalized_path
        and not normalized_path.startswith("/")
    ):
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="WSL 模式下导入目录必须为 Linux 绝对路径",
            detail={
                "runtime_profile": runtime_profile,
                "import_host": normalized_path,
            },
        )
    return normalized_path


def _resolve_data_mount(raw_value: str) -> str:
    cleaned = raw_value.strip().strip('"')
    if cleaned.startswith("/"):
        return _normalize_host_path_for_docker(cleaned)
    if "/" in cleaned or ":\\" in raw_value or ":/" in raw_value:
        return _normalize_host_path_for_docker(
            str(Path(cleaned).expanduser().resolve())
        )
    return cleaned


def _resolve_runtime_profile(*, context: ExternalScanContext) -> str:
    profile = (
        str(context.base_env.get("CODESCOPE_SCAN_RUNTIME_PROFILE") or "")
        .strip()
        .lower()
    )
    compat_flag = str(
        context.base_env.get("CODESCOPE_SCAN_CONTAINER_COMPAT_MODE") or ""
    ).strip()
    if profile == CONTAINER_COMPAT_RUNTIME_PROFILE or compat_flag == "1":
        return CONTAINER_COMPAT_RUNTIME_PROFILE
    return WSL_RUNTIME_PROFILE


def _ensure_docker_cli_available() -> None:
    if shutil.which("docker"):
        return
    raise AppError(
        code="SCAN_EXTERNAL_NOT_CONFIGURED",
        status_code=501,
        message="Docker CLI 不可用",
        detail={"required_command": "docker"},
    )


def _preflight_check_docker_daemon(*, deadline: float) -> None:
    _ensure_docker_cli_available()
    cmd = ["docker", "info", "--format", "{{.ServerVersion}}"]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="Docker daemon 不可达",
            detail={
                "failure_kind": "docker_daemon_unreachable",
                "command": cmd,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )


def _preflight_check_import_mount(*, import_host: str, deadline: float) -> None:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{import_host}:/import:ro",
        "alpine:3.19",
        "sh",
        "-lc",
        "ls -1 /import",
    ]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    out = (result.stdout or "").strip()
    if result.returncode != 0 or not out:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="Docker 挂载 /import 预检失败",
            detail={
                "failure_kind": "import_mount_unreachable",
                "command": cmd,
                "import_host": import_host,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )


def _is_container_running(*, container_name: str, deadline: float) -> bool:
    cmd = ["docker", "inspect", container_name, "--format", "{{.State.Running}}"]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="无法读取 Neo4j 容器状态",
            detail={
                "container_name": container_name,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )
    return (result.stdout or "").strip().lower() == "true"


def _stop_container(*, container_name: str, deadline: float) -> None:
    cmd = ["docker", "stop", container_name]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="停止 Neo4j 容器失败",
            detail={
                "container_name": container_name,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )


def _start_container(*, container_name: str, deadline: float) -> None:
    cmd = ["docker", "start", container_name]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="启动 Neo4j 容器失败",
            detail={
                "container_name": container_name,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )


def _container_exists(*, container_name: str, deadline: float) -> bool:
    cmd = ["docker", "inspect", container_name, "--format", "{{.Id}}"]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    return result.returncode == 0 and bool((result.stdout or "").strip())


def _remove_container(
    *, container_name: str, deadline: float, ignore_missing: bool = False
) -> None:
    cmd = ["docker", "rm", "-f", container_name]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode == 0:
        return
    output_text = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if ignore_missing and "no such container" in output_text:
        return
    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="删除 Neo4j 容器失败",
        detail={
            "container_name": container_name,
            "stdout": _tail_text(result.stdout),
            "stderr": _tail_text(result.stderr),
        },
    )


def _run_ephemeral_runtime_container(
    *,
    image: str,
    container_name: str,
    data_mount: str,
    uri: str,
    password: str,
    network: str,
    network_alias: str,
    network_auto_create: bool,
    runtime_phase: str = "query",
    publish_bolt: bool = True,
    deadline: float,
) -> dict[str, object]:
    docker_network, docker_network_alias = _resolve_ephemeral_runtime_networking(
        uri=uri,
        network=network,
        network_alias=network_alias,
    )
    network_created_by_job = False
    if docker_network:
        network_created_by_job = _ensure_network_exists(
            network_name=docker_network,
            deadline=deadline,
            auto_create=network_auto_create,
        )
    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "-v",
        f"{data_mount}:/data",
        "-e",
        f"NEO4J_AUTH={_build_neo4j_auth_value(password=password)}",
        "-e",
        "NEO4J_server_default__listen__address=0.0.0.0",
    ]
    if docker_network:
        cmd.extend(["--network", docker_network])
    if docker_network_alias:
        cmd.extend(["--network-alias", docker_network_alias])
    publish_arg = _build_bolt_publish_arg(uri=uri) if publish_bolt else None
    if publish_arg:
        cmd.extend(["-p", publish_arg])
    cmd.append(image)
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="启动任务级 Neo4j 容器失败",
            detail={
                "container_name": container_name,
                "command": cmd,
                "stdout": _tail_text(result.stdout),
                "stderr": _tail_text(result.stderr),
            },
        )
    runtime_uri = uri
    published_port = None
    if publish_bolt:
        runtime_uri, published_port = _resolve_runtime_uri_after_start(
            container_name=container_name,
            configured_uri=uri,
            network_alias=docker_network_alias,
            deadline=deadline,
        )
    return {
        "phase": runtime_phase,
        "restart_mode": DOCKER_EPHEMERAL_RUNTIME_MODE,
        "container_name": container_name,
        "data_mount": data_mount,
        "uri": runtime_uri,
        "published_port": published_port,
        "publish_bolt": publish_bolt,
        "network": docker_network,
        "network_alias": docker_network_alias,
        "network_created_by_job": network_created_by_job,
    }


def _ensure_network_exists(
    *, network_name: str, deadline: float, auto_create: bool
) -> bool:
    cmd = ["docker", "network", "inspect", network_name, "--format", "{{.Id}}"]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode == 0 and bool((result.stdout or "").strip()):
        return False
    if auto_create:
        _create_network(network_name=network_name, deadline=deadline)
        return True
    raise AppError(
        code="SCAN_EXTERNAL_NOT_CONFIGURED",
        status_code=501,
        message="Neo4j 运行时网络不存在或不可用",
        detail={
            "network": network_name,
            "stdout": _tail_text(result.stdout),
            "stderr": _tail_text(result.stderr),
        },
    )


def _create_network(*, network_name: str, deadline: float) -> None:
    cmd = ["docker", "network", "create", network_name]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode == 0:
        return
    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="创建 Neo4j 运行时网络失败",
        detail={
            "network": network_name,
            "stdout": _tail_text(result.stdout),
            "stderr": _tail_text(result.stderr),
        },
    )


def _build_neo4j_auth_value(*, password: str) -> str:
    secret = password.strip()
    if not secret:
        return "none"
    return f"neo4j/{secret}"


def _runtime_container_name_for_phase(container_name: str, *, phase: str) -> str:
    base = container_name.strip()
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", phase).strip("-") or "runtime"
    if not base:
        return ""
    return f"{base}-{suffix}"


def _build_bolt_publish_arg(*, uri: str) -> str | None:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1::7687"
    if host == "0.0.0.0":
        return "0.0.0.0::7687"
    return None


def _resolve_runtime_uri_after_start(
    *,
    container_name: str,
    configured_uri: str,
    network_alias: str,
    deadline: float,
) -> tuple[str, int | None]:
    parsed = urlparse(configured_uri)
    scheme = parsed.scheme or "bolt"
    host = (parsed.hostname or "").strip()
    if not _uri_host_requires_runtime_network(host=host):
        published_port = _inspect_container_host_port(
            container_name=container_name,
            deadline=deadline,
        )
        return f"{scheme}://127.0.0.1:{published_port}", published_port

    runtime_host = network_alias.strip() or host or "neo4j"
    runtime_port = parsed.port or 7687
    return f"{scheme}://{runtime_host}:{runtime_port}", None


def _inspect_container_host_port(*, container_name: str, deadline: float) -> int:
    cmd = ["docker", "port", container_name, "7687/tcp"]
    port_deadline = min(deadline, time.monotonic() + 30)
    last_stdout = ""
    last_stderr = ""
    last_output = ""

    while True:
        result = _run_command_with_deadline(cmd, deadline=deadline)
        last_stdout = result.stdout or ""
        last_stderr = result.stderr or ""
        last_output = last_stdout.strip()
        if result.returncode == 0 and last_output:
            port_text = last_output.splitlines()[-1].rsplit(":", 1)[-1].strip()
            try:
                return int(port_text)
            except ValueError:
                pass
        if time.monotonic() >= port_deadline:
            break
        time.sleep(1)

    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="无法识别 Neo4j 容器映射端口",
        detail={
            "container_name": container_name,
            "stdout": _tail_text(last_stdout),
            "stderr": _tail_text(last_stderr),
            "output": _tail_text(last_output),
        },
    )


def _resolve_ephemeral_runtime_networking(
    *, uri: str, network: str, network_alias: str
) -> tuple[str, str]:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").strip()
    normalized_network = network.strip()
    normalized_alias = network_alias.strip()

    if normalized_alias and not normalized_network:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="配置 Neo4j 运行时网络别名时必须同时配置网络",
            detail={"required": "scan_external_neo4j_runtime_network"},
        )

    if _uri_host_requires_runtime_network(host=host) and not normalized_network:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="docker_ephemeral 模式下，非本地 Neo4j URI 需要配置运行时网络",
            detail={
                "uri": uri,
                "required": "scan_external_neo4j_runtime_network",
            },
        )

    if not normalized_network:
        return "", ""

    resolved_alias = normalized_alias
    if not resolved_alias and _uri_host_requires_runtime_network(host=host):
        resolved_alias = host
    return normalized_network, resolved_alias


def _uri_host_requires_runtime_network(*, host: str) -> bool:
    normalized = host.strip().lower()
    if not normalized:
        return False
    return normalized not in {"127.0.0.1", "localhost", "0.0.0.0"}


def cleanup_ephemeral_runtime_resources(
    *,
    container_name: str | None,
    data_mount: str | None,
    network_name: str | None = None,
    cleanup_network: bool = False,
    deadline: float,
) -> dict[str, object]:
    container_cleanup_attempted = False
    container_cleanup_succeeded = False
    data_cleanup_attempted = False
    data_cleanup_succeeded = False
    network_cleanup_attempted = False
    network_cleanup_succeeded = False

    normalized_container_name = str(container_name or "").strip()
    normalized_data_mount = str(data_mount or "").strip()
    normalized_network_name = str(network_name or "").strip()

    if normalized_container_name:
        container_cleanup_attempted = True
        _remove_container(
            container_name=normalized_container_name,
            deadline=deadline,
            ignore_missing=True,
        )
        container_cleanup_succeeded = True

    if normalized_data_mount:
        data_cleanup_attempted = True
        _remove_data_mount(data_mount=normalized_data_mount, deadline=deadline)
        data_cleanup_succeeded = True

    if cleanup_network and normalized_network_name:
        network_cleanup_attempted = True
        _remove_network(network_name=normalized_network_name, deadline=deadline)
        network_cleanup_succeeded = True

    return {
        "container_cleanup_attempted": container_cleanup_attempted,
        "container_cleanup_succeeded": container_cleanup_succeeded,
        "data_cleanup_attempted": data_cleanup_attempted,
        "data_cleanup_succeeded": data_cleanup_succeeded,
        "network_cleanup_attempted": network_cleanup_attempted,
        "network_cleanup_succeeded": network_cleanup_succeeded,
    }


def _wait_for_ephemeral_runtime_ready(
    *,
    container_name: str,
    uri: str,
    user: str,
    password: str,
    connect_retry: int,
    connect_wait_seconds: int,
    deadline: float,
) -> None:
    retry = max(1, int(connect_retry))
    wait_seconds = max(1, int(connect_wait_seconds))
    _wait_for_container_running(
        container_name=container_name,
        retry=retry,
        wait_seconds=wait_seconds,
        deadline=deadline,
    )
    try:
        verify_neo4j_connectivity(
            uri=uri,
            user=user,
            password=password,
            connect_retry=retry,
            connect_wait_seconds=wait_seconds,
        )
    except AppError as exc:
        logs_tail = _read_container_logs_tail(
            container_name=container_name,
            deadline=deadline,
        )
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="任务级 Neo4j 运行时未就绪",
            detail={
                "container_name": container_name,
                "uri": uri,
                "error": str(exc),
                "container_logs_tail": logs_tail,
            },
        ) from exc


def _wait_for_container_running(
    *, container_name: str, retry: int, wait_seconds: int, deadline: float
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retry + 1):
        try:
            if _is_container_running(container_name=container_name, deadline=deadline):
                return
            last_error = RuntimeError("container not running yet")
        except Exception as exc:
            last_error = exc

        if attempt < retry:
            sleep_seconds = min(wait_seconds, _remaining_seconds(deadline))
            time.sleep(max(0, sleep_seconds))

    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="任务级 Neo4j 容器未进入运行状态",
        detail={
            "container_name": container_name,
            "error": str(last_error or "unknown"),
        },
    )


def _read_container_logs_tail(*, container_name: str, deadline: float) -> str:
    try:
        result = _run_command_with_deadline(
            ["docker", "logs", "--tail", "120", container_name],
            deadline=deadline,
        )
    except Exception as exc:
        return f"<unavailable: {exc}>"
    text = (
        (result.stdout or "")
        + ("\n" if result.stdout and result.stderr else "")
        + (result.stderr or "")
    )
    return _tail_text(text, max_chars=4000)


def _remove_data_mount(*, data_mount: str, deadline: float) -> None:
    if _looks_like_path_mount(data_mount):
        target = _absolute_path_without_resolve(data_mount)
        if target.exists():
            if not _is_allowed_cleanup_host_path(target=target):
                raise AppError(
                    code="SCAN_EXTERNAL_IMPORT_FAILED",
                    status_code=422,
                    message="拒绝删除白名单之外的宿主机 Neo4j 数据目录",
                    detail={
                        "data_mount": str(target),
                        "allowed_roots": [
                            str(item) for item in _cleanup_host_path_allowlist_roots()
                        ],
                    },
                )
            shutil.rmtree(target, ignore_errors=False)
        return

    cmd = ["docker", "volume", "rm", "-f", data_mount]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode == 0:
        return
    output_text = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if "no such volume" in output_text:
        return
    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="删除 Neo4j 数据挂载失败",
        detail={
            "data_mount": data_mount,
            "stdout": _tail_text(result.stdout),
            "stderr": _tail_text(result.stderr),
        },
    )


def _remove_network(*, network_name: str, deadline: float) -> None:
    cmd = ["docker", "network", "rm", network_name]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    if result.returncode == 0:
        return
    output_text = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if "no such network" in output_text:
        return
    raise AppError(
        code="SCAN_EXTERNAL_IMPORT_FAILED",
        status_code=422,
        message="删除 Neo4j 运行时网络失败",
        detail={
            "network": network_name,
            "stdout": _tail_text(result.stdout),
            "stderr": _tail_text(result.stderr),
        },
    )


def _looks_like_path_mount(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    return (
        "/" in cleaned
        or "\\" in cleaned
        or re.match(r"^[A-Za-z]:", cleaned) is not None
    )


def _absolute_path_without_resolve(path: Path | str) -> Path:
    return Path(os.path.abspath(os.path.normpath(str(path))))


def _cleanup_host_path_allowlist_roots() -> list[Path]:
    raw_value = str(
        getattr(get_settings(), "scan_external_cleanup_host_path_allowlist", "") or ""
    )
    roots: list[Path] = []
    for item in re.split(r"[,;\n]", raw_value):
        cleaned = item.strip()
        if not cleaned:
            continue
        roots.append(_absolute_path_without_resolve(cleaned))
    return roots


def _is_allowed_cleanup_host_path(*, target: Path) -> bool:
    for root in _cleanup_host_path_allowlist_roots():
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _neo4j_admin_resolver_shell() -> str:
    return (
        "NEO4J_ADMIN=; "
        "if command -v neo4j-admin >/dev/null 2>&1; then NEO4J_ADMIN=neo4j-admin; "
        "elif [ -x /var/lib/neo4j/bin/neo4j-admin ]; then NEO4J_ADMIN=/var/lib/neo4j/bin/neo4j-admin; "
        "elif [ -x /usr/share/neo4j/bin/neo4j-admin ]; then NEO4J_ADMIN=/usr/share/neo4j/bin/neo4j-admin; "
        "else echo neo4j-admin-not-found 1>&2; exit 127; fi"
    )


def _detect_neo4j_major(*, image: str, deadline: float) -> int:
    resolver = _neo4j_admin_resolver_shell()
    cmd = [
        "docker",
        "run",
        "--rm",
        image,
        "bash",
        "-lc",
        f"{resolver}; $NEO4J_ADMIN --version",
    ]
    result = _run_command_with_deadline(cmd, deadline=deadline)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = re.search(r"(\d+)\.", text)
    if result.returncode != 0 or match is None:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="无法识别 Neo4j 版本",
            detail={"output": _tail_text(text)},
        )
    return int(match.group(1))


def _build_admin_parts(
    *,
    major: int,
    database: str,
    clean_db: bool,
    id_type: str,
    multiline_fields: bool,
    multiline_fields_format: str,
    array_delimiter: str,
    nodes: list[tuple[str, str, str]],
    rels: list[tuple[str, str, str]],
) -> list[str]:
    parts: list[str] = []
    cleanup = ""
    if clean_db:
        cleanup = f"rm -rf /data/databases/{database} /data/transactions/{database}; "

    if major >= 5:
        parts.extend(
            [
                cleanup + "$NEO4J_ADMIN",
                "database",
                "import",
                "full",
                database,
                "--overwrite-destination=true",
            ]
        )
    else:
        parts.extend(
            [cleanup + "$NEO4J_ADMIN", "import", f"--database={database}", "--force"]
        )

    mapped_id = _map_id_type(id_type)
    if mapped_id:
        parts.append(f"--id-type={mapped_id}")
    parts.append(f"--multiline-fields={'true' if multiline_fields else 'false'}")
    if multiline_fields_format:
        parts.append(f"--multiline-fields-format={multiline_fields_format}")
    if array_delimiter:
        parts.append(f'--array-delimiter="{array_delimiter}"')

    for label, header, data in nodes:
        parts.append(f"--nodes={label}=/import/{header},/import/{data}")
    for rel_type, header, data in rels:
        parts.append(f"--relationships={rel_type}=/import/{header},/import/{data}")
    return parts


def _map_id_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "integer":
        return "INTEGER"
    if normalized == "actual":
        return "ACTUAL"
    if normalized == "string":
        return "STRING"
    return ""


def _list_rule_files(*, rules_dir: Path) -> list[Path]:
    return list_runtime_rule_files(rules_dir=rules_dir)


def _rule_key_from_file(path: Path) -> str:
    return path.stem


def _normalize_rules_failure_mode(value: object) -> str:
    mode = str(value or "permissive").strip().lower()
    if mode == "strict":
        return "strict"
    return "permissive"


def _summarize_rule_rows(rule_rows: dict[str, int]) -> dict[str, int]:
    total_rules = len(rule_rows)
    hit_rules = sum(1 for value in rule_rows.values() if int(value) > 0)
    zero_rules = total_rules - hit_rules
    total_rows = sum(int(value) for value in rule_rows.values())
    return {
        "total_rules": total_rules,
        "hit_rules": hit_rules,
        "zero_rules": zero_rules,
        "total_rows": total_rows,
    }


def _tail_text(value: str | None, max_chars: int = 2000) -> str:
    text = value or ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _command_to_text(command: list[str]) -> str:
    return " ".join(command)


def _normalize_requested_rule_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name:
            continue
        marker = name.lower()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(name)
    return normalized
