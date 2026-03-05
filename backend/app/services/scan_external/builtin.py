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

from app.core.errors import AppError
from app.models import Job

from .contracts import ExternalScanContext
from .neo4j_runner import execute_cypher_file


NODE_HEADER_RE = re.compile(r"^nodes_(.+)_header\.csv$", re.IGNORECASE)
EDGE_HEADER_RE = re.compile(r"^edges_(.+)_header\.csv$", re.IGNORECASE)


def run_builtin_stage(
    *,
    builtin_key: str,
    job: Job,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    timeout_seconds: int,
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
    if builtin_key == "rules":
        return _run_builtin_rules(
            job=job,
            settings=settings,
            context=context,
            append_log=append_log,
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
    joern_bin = Path(context.base_env.get("CODESCOPE_SCAN_JOERN_BIN") or "")
    joern_home = Path(context.base_env.get("CODESCOPE_SCAN_JOERN_HOME") or "")
    export_script = Path(context.base_env.get("CODESCOPE_SCAN_JOERN_EXPORT_SCRIPT") or "")

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
            detail={"export_script": str(export_script)},
        )

    javasrc2cpg_bin = _resolve_joern_binary(
        joern_home=joern_home,
        windows_name="javasrc2cpg.bat",
        unix_name="javasrc2cpg",
    )
    if not javasrc2cpg_bin.exists() or not javasrc2cpg_bin.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="javasrc2cpg 可执行文件不存在",
            detail={"javasrc2cpg_bin": str(javasrc2cpg_bin)},
        )

    _clear_directory(context.import_dir)
    context.workspace_dir.mkdir(parents=True, exist_ok=True)
    if context.cpg_file.exists() and context.cpg_file.is_file():
        context.cpg_file.unlink(missing_ok=True)

    parse_cmd = [
        str(javasrc2cpg_bin),
        str(context.source_dir),
        "-o",
        str(context.cpg_file),
    ]
    parse_result = _run_command_with_deadline(parse_cmd, deadline=deadline)
    if parse_result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="javasrc2cpg 执行失败",
            detail={
                "exit_code": parse_result.returncode,
                "stdout_tail": _tail_text(parse_result.stdout),
                "stderr_tail": _tail_text(parse_result.stderr),
            },
        )

    export_env = dict(context.base_env)
    patch = job.payload.get("joern_patch")
    patch_map = patch if isinstance(patch, dict) else {}
    enable_calls = bool(patch_map.get("ENABLE_CALLS", False))
    enable_ref = bool(patch_map.get("ENABLE_REF", False))
    ast_mode = str(patch_map.get("AST_MODE", "local") or "local").lower()
    if ast_mode not in {"none", "local", "wide"}:
        ast_mode = "local"

    export_env["cpgFile"] = str(context.cpg_file)
    export_env["outDir"] = str(context.import_dir)
    export_env["ENABLE_CALLS"] = "true" if enable_calls else "false"
    export_env["ENABLE_REF"] = "true" if enable_ref else "false"
    export_env["AST_MODE"] = ast_mode

    export_cmd = [str(joern_bin), "--script", str(export_script)]
    export_result = _run_command_with_deadline(export_cmd, deadline=deadline, env=export_env)
    if export_result.returncode != 0:
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="Joern 导出执行失败",
            detail={
                "exit_code": export_result.returncode,
                "stdout_tail": _tail_text(export_result.stdout),
                "stderr_tail": _tail_text(export_result.stderr),
            },
        )

    nodes, rels = _collect_csv_pairs(context.import_dir)
    if not nodes and not rels:
        raise AppError(
            code="SCAN_EXTERNAL_JOERN_FAILED",
            status_code=422,
            message="Joern 导出未产出 CSV 文件",
            detail={"import_dir": str(context.import_dir)},
        )

    append_log(
        "ANALYZE",
        f"[joern] 导出完成: nodes={len(nodes)}, relationships={len(rels)}, import_dir={context.import_dir}",
    )
    stdout = "\n".join(
        [
            _tail_text(parse_result.stdout),
            _tail_text(export_result.stdout),
            f"nodes={len(nodes)} rels={len(rels)}",
        ]
    ).strip()
    stderr = "\n".join([_tail_text(parse_result.stderr), _tail_text(export_result.stderr)]).strip()
    return stdout, stderr


def _run_builtin_neo4j_import(
    *,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
    deadline: float,
) -> tuple[str, str]:
    image = str(settings.scan_external_import_docker_image or "").strip()
    data_mount_raw = str(settings.scan_external_import_data_mount or "").strip()
    database = str(settings.scan_external_import_database or "neo4j").strip() or "neo4j"
    if not image:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j 导入镜像",
        )
    if not data_mount_raw:
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="未配置 Neo4j data 挂载点",
            detail={"setting": "scan_external_import_data_mount"},
        )

    nodes, rels = _collect_csv_pairs(context.import_dir)
    if not nodes and not rels:
        raise AppError(
            code="SCAN_EXTERNAL_IMPORT_FAILED",
            status_code=422,
            message="导入目录中未找到 CSV 文件",
            detail={"import_dir": str(context.import_dir)},
        )

    import_host = _normalize_host_path_for_docker(str(context.import_dir.resolve()))
    data_mount = _resolve_data_mount(data_mount_raw)

    if bool(settings.scan_external_import_preflight):
        _preflight_check_import_mount(import_host=import_host, deadline=deadline)

    restart_mode = str(settings.scan_external_neo4j_runtime_restart_mode or "none").strip().lower()
    container_name = str(settings.scan_external_neo4j_runtime_container_name or "").strip()
    restart_wait_seconds = max(0, int(settings.scan_external_neo4j_runtime_restart_wait_seconds or 0))
    manage_runtime = restart_mode == "docker" and bool(container_name)
    was_running = False

    if manage_runtime:
        was_running = _is_container_running(container_name=container_name, deadline=deadline)
        if was_running:
            append_log("ANALYZE", f"[neo4j_import] 停止运行中的 Neo4j 容器: {container_name}")
            _stop_container(container_name=container_name, deadline=deadline)

    import_error: AppError | None = None
    import_result: subprocess.CompletedProcess[str] | None = None
    restart_error: AppError | None = None
    try:
        major = _detect_neo4j_major(image=image, deadline=deadline)
        admin_parts = _build_admin_parts(
            major=major,
            database=database,
            clean_db=bool(settings.scan_external_import_clean_db),
            id_type=str(settings.scan_external_import_id_type or "").strip().lower(),
            multiline_fields=bool(settings.scan_external_import_multiline_fields),
            multiline_fields_format=str(settings.scan_external_import_multiline_fields_format or "").strip(),
            array_delimiter=str(settings.scan_external_import_array_delimiter or "\\001"),
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
        import_result = _run_command_with_deadline(docker_cmd, deadline=deadline)
        if import_result.returncode != 0:
            raise AppError(
                code="SCAN_EXTERNAL_IMPORT_FAILED",
                status_code=422,
                message="neo4j-admin import 执行失败",
                detail={
                    "exit_code": import_result.returncode,
                    "stdout_tail": _tail_text(import_result.stdout),
                    "stderr_tail": _tail_text(import_result.stderr),
                },
            )
    except AppError as exc:
        import_error = exc
    finally:
        if manage_runtime and was_running:
            try:
                append_log("ANALYZE", f"[neo4j_import] 重启 Neo4j 容器: {container_name}")
                _start_container(container_name=container_name, deadline=deadline)
                if restart_wait_seconds > 0:
                    sleep_seconds = min(restart_wait_seconds, _remaining_seconds(deadline))
                    time.sleep(max(0, sleep_seconds))
            except Exception as exc:
                restart_error = AppError(
                    code="SCAN_EXTERNAL_IMPORT_FAILED",
                    status_code=422,
                    message="Neo4j 运行时重启失败",
                    detail={"container_name": container_name, "error": str(exc)},
                )

    if import_error is not None:
        if restart_error is not None:
            detail = dict(import_error.detail) if isinstance(import_error.detail, dict) else {}
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
    cypher_file = Path(context.base_env.get("CODESCOPE_SCAN_POST_LABELS_CYPHER") or "")
    if not cypher_file.exists() or not cypher_file.is_file():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="post_labels Cypher 文件不存在",
            detail={"post_labels_cypher": str(cypher_file)},
        )

    try:
        summary = execute_cypher_file(
            cypher_file=cypher_file,
            uri=str(settings.scan_external_neo4j_uri or ""),
            user=str(settings.scan_external_neo4j_user or ""),
            password=str(settings.scan_external_neo4j_password or ""),
            database=str(settings.scan_external_neo4j_database or "neo4j"),
            connect_retry=int(settings.scan_external_neo4j_connect_retry),
            connect_wait_seconds=int(settings.scan_external_neo4j_connect_wait_seconds),
        )
    except AppError as exc:
        if exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED":
            raise
        detail = dict(exc.detail) if isinstance(exc.detail, dict) else {}
        raise AppError(
            code="SCAN_EXTERNAL_POST_LABELS_FAILED",
            status_code=422,
            message="post_labels 执行失败",
            detail=detail,
        ) from exc
    message = (
        f"[post_labels] 执行完成: statements={summary.statement_count}, "
        f"total_rows={summary.total_rows}"
    )
    append_log("QUERY", message)
    return message, ""


def _run_builtin_rules(
    *,
    job: Job,
    settings: Any,
    context: ExternalScanContext,
    append_log: Callable[[str, str], None],
) -> tuple[str, str]:
    rules_dir = Path(context.base_env.get("CODESCOPE_SCAN_RULES_DIR") or "")
    if not rules_dir.exists() or not rules_dir.is_dir():
        raise AppError(
            code="SCAN_EXTERNAL_NOT_CONFIGURED",
            status_code=501,
            message="规则目录不存在",
            detail={"rules_dir": str(rules_dir)},
        )

    allowlist = Path(context.base_env.get("CODESCOPE_SCAN_RULES_ALLOWLIST_FILE") or "")
    rule_files = _list_rule_files(rules_dir=rules_dir, allowlist_file=allowlist)

    requested_rule_names = _normalize_requested_rule_names(job.payload.get("rule_set_ids"))
    if requested_rule_names:
        rule_files, missing_rules = _filter_rule_files_by_request(
            rule_files=rule_files,
            requested_rule_names=requested_rule_names,
        )
        if missing_rules:
            raise AppError(
                code="SCAN_EXTERNAL_RULES_FAILED",
                status_code=422,
                message="规则执行阶段存在未知规则名",
                detail={"missing_rules": missing_rules},
            )

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

    rule_rows: dict[str, int] = {}
    partial_failures: list[dict[str, object]] = []
    succeeded_rule_count = 0
    for rule_file in rule_files:
        try:
            summary = execute_cypher_file(
                cypher_file=rule_file,
                uri=str(settings.scan_external_neo4j_uri or ""),
                user=str(settings.scan_external_neo4j_user or ""),
                password=str(settings.scan_external_neo4j_password or ""),
                database=str(settings.scan_external_neo4j_database or "neo4j"),
                connect_retry=int(settings.scan_external_neo4j_connect_retry),
                connect_wait_seconds=int(settings.scan_external_neo4j_connect_wait_seconds),
            )
            rule_rows[rule_file.name] = summary.total_rows
            succeeded_rule_count += 1
        except AppError as exc:
            if exc.code == "SCAN_EXTERNAL_NOT_CONFIGURED":
                raise
            rule_rows[rule_file.name] = 0
            partial_failures.append(
                {
                    "rule": rule_file.name,
                    "error_code": exc.code,
                    "message": exc.message,
                }
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
    round_report = {
        "round": 1,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "rule_rows": rule_rows,
        "rule_summary": rule_summary,
        "partial_failures": partial_failures,
    }
    report_path = context.reports_dir / "round_1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(round_report, ensure_ascii=False, indent=2), encoding="utf-8")

    append_log(
        "QUERY",
        (
            "[rules] 执行完成: "
            f"total_rules={rule_summary['total_rules']}, "
            f"hit_rules={rule_summary['hit_rules']}, "
            f"partial_failures={len(partial_failures)}"
        ),
    )
    stdout = json.dumps(
        {
            "report_path": str(report_path),
            "total_rules": rule_summary["total_rules"],
            "hit_rules": rule_summary["hit_rules"],
            "partial_failures": len(partial_failures),
        },
        ensure_ascii=False,
    )
    return stdout, ""


def _run_command_with_deadline(
    command: list[str],
    *,
    deadline: float,
    env: dict[str, str] | None = None,
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


def _collect_csv_pairs(import_dir: Path) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
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
                code="SCAN_EXTERNAL_JOERN_FAILED",
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
                code="SCAN_EXTERNAL_JOERN_FAILED",
                status_code=422,
                message="关系 CSV 缺少 data 文件",
                detail={"header": str(header), "data": str(data)},
            )
        rels.append((rel_type, header.name, data.name))

    nodes.sort(key=lambda item: item[0].lower())
    rels.sort(key=lambda item: item[0].lower())
    return nodes, rels


def _resolve_joern_binary(*, joern_home: Path, windows_name: str, unix_name: str) -> Path:
    if os.name == "nt":
        return joern_home / windows_name
    return joern_home / unix_name


def _normalize_host_path_for_docker(path_text: str) -> str:
    return path_text.strip().strip('"').replace("\\", "/")


def _resolve_data_mount(raw_value: str) -> str:
    cleaned = raw_value.strip().strip('"')
    if "/" in cleaned or ":\\" in raw_value or ":/" in raw_value:
        return _normalize_host_path_for_docker(str(Path(cleaned).expanduser().resolve()))
    return cleaned


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
        parts.extend([cleanup + "$NEO4J_ADMIN", "import", f"--database={database}", "--force"])

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


def _list_rule_files(*, rules_dir: Path, allowlist_file: Path) -> list[Path]:
    if allowlist_file.exists() and allowlist_file.is_file():
        names = _load_allowlist(allowlist_file)
        files: list[Path] = []
        for name in names:
            candidate = (rules_dir / name).resolve()
            if candidate.exists() and candidate.is_file():
                files.append(candidate)
        return files

    return sorted(
        [item for item in rules_dir.glob("*.cypher") if item.is_file()],
        key=lambda item: item.name.lower(),
    )


def _load_allowlist(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        names.append(raw)
    return names


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


def _filter_rule_files_by_request(
    *,
    rule_files: list[Path],
    requested_rule_names: list[str],
) -> tuple[list[Path], list[str]]:
    available_by_name = {item.name.lower(): item for item in rule_files}
    selected: list[Path] = []
    selected_markers: set[str] = set()
    missing: list[str] = []

    for requested in requested_rule_names:
        candidates = [requested]
        if not requested.lower().endswith(".cypher"):
            candidates.append(f"{requested}.cypher")

        matched: Path | None = None
        for candidate in candidates:
            matched = available_by_name.get(candidate.lower())
            if matched is not None:
                break

        if matched is None:
            missing.append(requested)
            continue

        marker = str(matched.resolve()).lower()
        if marker in selected_markers:
            continue
        selected_markers.add(marker)
        selected.append(matched)

    return selected, missing
