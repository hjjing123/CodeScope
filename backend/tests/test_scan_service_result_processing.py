from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models import (
    Job,
    JobStage,
    JobStatus,
    JobStepStatus,
    JobType,
    Project,
    Version,
)
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
        "  PreparedStatement ps = connection.prepareStatement(sql);\n"
        "  ps.setString(1, input);\n"
        "  ps.executeQuery();\n"
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
                "line_end": 6,
                "source": {"file": "src/Main.java", "line": 2},
                "sink": {"file": "src/Main.java", "line": 6},
                "evidence": {"items": ["request.id", "prepareStatement", "setString"]},
                "trace_summary": "request -> sql -> prepareStatement -> setString -> executeQuery",
                "has_path": True,
                "path_length": 5,
                "paths": [
                    {
                        "steps": [
                            {
                                "file": "src/Main.java",
                                "line": 2,
                                "display_name": "request.id",
                                "node_kind": "Param",
                                "code_snippet": 'request.getParameter("id")',
                            },
                            {
                                "file": "src/Main.java",
                                "line": 3,
                                "display_name": "sql",
                                "node_kind": "Var",
                                "code_snippet": 'String sql = "select * from user where id=" + input;',
                            },
                            {
                                "file": "src/Main.java",
                                "line": 4,
                                "display_name": "prepareStatement",
                                "node_kind": "Call",
                                "code_snippet": "PreparedStatement ps = connection.prepareStatement(sql);",
                            },
                            {
                                "file": "src/Main.java",
                                "line": 5,
                                "display_name": "setString",
                                "node_kind": "Call",
                                "code_snippet": "ps.setString(1, input);",
                            },
                            {
                                "file": "src/Main.java",
                                "line": 6,
                                "display_name": "executeQuery",
                                "node_kind": "Call",
                                "code_snippet": "ps.executeQuery();",
                            },
                        ],
                        "edges": [
                            {"from_step_id": 0, "to_step_id": 1, "edge_type": "REF"},
                            {"from_step_id": 1, "to_step_id": 2, "edge_type": "ARG"},
                            {"from_step_id": 2, "to_step_id": 3, "edge_type": "ARG"},
                            {"from_step_id": 3, "to_step_id": 4, "edge_type": "CALLS"},
                        ],
                    }
                ],
            }
        ]

        enriched = scan_service_module._attach_code_contexts(
            job=SimpleNamespace(version_id=version_id),
            finding_drafts=finding_drafts,
        )
        assert enriched[0]["code_context"]["focus"]["file_path"] == "src/Main.java"
        assert "3:   String sql" in enriched[0]["code_context"]["focus"]["snippet"]

        llm_enriched = scan_service_module._attach_ai_payloads(
            version_id=version_id,
            finding_drafts=enriched,
        )
        payload = llm_enriched[0]["llm_payload"]
        assert llm_enriched[0]["assessment_profile"] == "SQLI"
        assert llm_enriched[0]["assessment_extraction"]["profile"] == "SQLI"
        assert (
            llm_enriched[0]["assessment_extraction"]["general_facts"]["path_available"]
            == "yes"
        )
        assert (
            llm_enriched[0]["assessment_extraction"]["structured_facts"][
                "sql_string_contains_user_input"
            ]
            == "yes"
        )
        assert llm_enriched[0]["assessment_extraction"]["expanded_code_context"][
            "path_steps"
        ]
        assert llm_enriched[0]["assessment_extraction"]["source_highlights"]
        assert {
            item["kind"]
            for item in llm_enriched[0]["assessment_extraction"]["source_highlights"]
        } & {"sql_execution", "sql_binding", "sql_construction"}
        assert llm_enriched[0]["assessment_extraction"]["filter_points"]
        assert payload["why_flagged"]
        assert payload["code_context"]["focus"]
        assert "Code:" in llm_enriched[0]["llm_prompt_block"]
        assert "Reason:" in llm_enriched[0]["llm_prompt_block"]

        finding_model = scan_service_module._create_finding_model_from_draft(
            job=SimpleNamespace(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                version_id=version_id,
            ),
            draft=llm_enriched[0],
        )
        assert finding_model.evidence_json["assessment_profile"] == "SQLI"
        assert finding_model.evidence_json["assessment_extraction"]["profile"] == "SQLI"
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


@pytest.mark.parametrize(
    ("profile", "file_path", "content", "draft", "expected_kind", "expected_text"),
    [
        (
            "CMDI",
            "src/CommandController.java",
            "class CommandController {\n"
            "  public String runCommand(String path) {\n"
            '    String command = String.format("ls %s", path);\n'
            '    ProcessBuilder pb = new ProcessBuilder("sh", "-c", command);\n'
            "    return pb.start().toString();\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/CommandController.java",
                "line_start": 4,
                "source": {"file": "src/CommandController.java", "line": 2},
                "sink": {"file": "src/CommandController.java", "line": 5},
            },
            "command_execution",
            "public String runCommand",
        ),
        (
            "CODEI",
            "src/ExpressionController.java",
            "class ExpressionController {\n"
            "  public Object evaluate(String expr) {\n"
            "    StandardEvaluationContext context = new StandardEvaluationContext();\n"
            "    return new SpelExpressionParser().parseExpression(expr).getValue(context);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/ExpressionController.java",
                "line_start": 4,
                "source": {"file": "src/ExpressionController.java", "line": 2},
                "sink": {"file": "src/ExpressionController.java", "line": 4},
            },
            "expression_execution",
            "public Object evaluate",
        ),
        (
            "JNDII",
            "src/JndiController.java",
            "class JndiController {\n"
            "  public Object lookup(String name) throws Exception {\n"
            "    InitialContext ctx = new InitialContext();\n"
            "    return ctx.lookup(name);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/JndiController.java",
                "line_start": 4,
                "source": {"file": "src/JndiController.java", "line": 2},
                "sink": {"file": "src/JndiController.java", "line": 4},
            },
            "jndi_lookup",
            "public Object lookup",
        ),
        (
            "DESERIALIZATION",
            "src/FastjsonService.java",
            "class FastjsonService {\n"
            "  public Object parse(String body) {\n"
            "    ParserConfig.getGlobalInstance().setSafeMode(false);\n"
            "    return JSON.parseObject(body, UserDto.class);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/FastjsonService.java",
                "line_start": 4,
                "source": {"file": "src/FastjsonService.java", "line": 2},
                "sink": {"file": "src/FastjsonService.java", "line": 4},
            },
            "deserialization_sink",
            "public Object parse",
        ),
        (
            "HARDCODE_SECRET",
            "src/SecretConfig.java",
            "class SecretConfig {\n"
            "  public DataSource build() throws Exception {\n"
            '    dataSource.setPassword("p@ssw0rd");\n'
            '    return DriverManager.getConnection(url, "admin", "p@ssw0rd");\n'
            "  }\n"
            "}\n",
            {
                "file_path": "src/SecretConfig.java",
                "line_start": 4,
                "source": {"file": "src/SecretConfig.java", "line": 3},
                "sink": {"file": "src/SecretConfig.java", "line": 4},
            },
            "secret_literal",
            "public DataSource build",
        ),
        (
            "XSS",
            "src/ViewController.java",
            "class ViewController {\n"
            "  public void render(HttpServletResponse response, String name) throws Exception {\n"
            "    response.getWriter().println(name);\n"
            '    response.setHeader("Content-Security-Policy", "default-src \'self\'");\n'
            "  }\n"
            "}\n",
            {
                "file_path": "src/ViewController.java",
                "line_start": 3,
                "source": {"file": "src/ViewController.java", "line": 2},
                "sink": {"file": "src/ViewController.java", "line": 3},
            },
            "output_sink",
            "public void render",
        ),
        (
            "SSTI",
            "src/TemplateController.java",
            "class TemplateController {\n"
            "  public String preview(String templateContent) throws Exception {\n"
            '    stringTemplateLoader.putTemplate("preview", templateContent);\n'
            '    return templateEngine.process("preview", context);\n'
            "  }\n"
            "}\n",
            {
                "file_path": "src/TemplateController.java",
                "line_start": 4,
                "source": {"file": "src/TemplateController.java", "line": 2},
                "sink": {"file": "src/TemplateController.java", "line": 4},
            },
            "template_render",
            "public String preview",
        ),
        (
            "REDIRECT",
            "src/LoginController.java",
            "class LoginController {\n"
            "  public void redirect(HttpServletRequest request, HttpServletResponse response) throws Exception {\n"
            '    String targetUrl = request.getParameter("returnUrl");\n'
            "    response.sendRedirect(targetUrl);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/LoginController.java",
                "line_start": 4,
                "source": {"file": "src/LoginController.java", "line": 3},
                "sink": {"file": "src/LoginController.java", "line": 4},
            },
            "redirect_sink",
            "public void redirect",
        ),
        (
            "LDAPI",
            "src/LdapController.java",
            "class LdapController {\n"
            "  public Object search(String uid) throws Exception {\n"
            '    String filter = String.format("(uid=%s)", uid);\n'
            "    return dirContext.search(baseDn, filter, controls);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/LdapController.java",
                "line_start": 4,
                "source": {"file": "src/LdapController.java", "line": 2},
                "sink": {"file": "src/LdapController.java", "line": 4},
            },
            "ldap_search",
            "public Object search",
        ),
        (
            "WEAK_HASH",
            "src/HashService.java",
            "class HashService {\n"
            "  public String hash(String password) throws Exception {\n"
            '    MessageDigest md = MessageDigest.getInstance("MD5");\n'
            "    return Hex.encodeHexString(md.digest(password.getBytes()));\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/HashService.java",
                "line_start": 4,
                "source": {"file": "src/HashService.java", "line": 2},
                "sink": {"file": "src/HashService.java", "line": 4},
            },
            "hash_selection",
            "public String hash",
        ),
        (
            "CORS",
            "src/WebConfig.java",
            "class WebConfig {\n"
            "  public void addCorsMappings(CorsRegistry registry) {\n"
            '    registry.addMapping("/**").allowedOrigins("*").allowCredentials(true);\n'
            "  }\n"
            "}\n",
            {
                "file_path": "src/WebConfig.java",
                "line_start": 3,
                "source": {},
                "sink": {},
            },
            "cors_header",
            "public void addCorsMappings",
        ),
        (
            "INFOLEAK",
            "src/ErrorController.java",
            "class ErrorController {\n"
            "  public void handle(Exception ex, HttpServletResponse response) throws Exception {\n"
            "    response.getWriter().println(ex.getMessage());\n"
            "    ex.printStackTrace();\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/ErrorController.java",
                "line_start": 3,
                "source": {"file": "src/ErrorController.java", "line": 2},
                "sink": {"file": "src/ErrorController.java", "line": 3},
            },
            "exception_sink",
            "public void handle",
        ),
        (
            "COOKIE_FLAGS",
            "src/AuthController.java",
            "class AuthController {\n"
            "  public void login(HttpServletResponse response) {\n"
            '    Cookie cookie = new Cookie("JSESSIONID", token);\n'
            "    response.addCookie(cookie);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/AuthController.java",
                "line_start": 4,
                "source": {"file": "src/AuthController.java", "line": 2},
                "sink": {"file": "src/AuthController.java", "line": 4},
            },
            "cookie_creation",
            "public void login",
        ),
        (
            "SSRF",
            "src/ProxyController.java",
            "class ProxyController {\n"
            "  public String proxy(String url) throws Exception {\n"
            "    URL target = new URL(url);\n"
            "    return target.openStream().toString();\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/ProxyController.java",
                "line_start": 4,
                "source": {"file": "src/ProxyController.java", "line": 2},
                "sink": {"file": "src/ProxyController.java", "line": 4},
            },
            "network_sink",
            "public String proxy",
        ),
        (
            "UPLOAD",
            "src/UploadController.java",
            "class UploadController {\n"
            "  String fileName = file.getOriginalFilename();\n"
            '  String key = UUID.randomUUID() + "-" + fileName;\n'
            "  String url = client.presignedGetObject(bucket, key);\n"
            "  client.putObject(bucket, key, file.getInputStream(), meta);\n"
            "}\n",
            {
                "file_path": "src/UploadController.java",
                "line_start": 4,
                "source": {"file": "src/UploadController.java", "line": 2},
                "sink": {"file": "src/UploadController.java", "line": 5},
            },
            "upload_sink",
            "client.putObject",
        ),
        (
            "PATHTRAVERSAL",
            "src/FileController.java",
            "class FileController {\n"
            "  public byte[] readFile(String fileName) throws Exception {\n"
            "    Path path = Paths.get(baseDir, fileName).normalize();\n"
            "    return Files.readAllBytes(path);\n"
            "  }\n"
            "}\n",
            {
                "file_path": "src/FileController.java",
                "line_start": 4,
                "source": {"file": "src/FileController.java", "line": 2},
                "sink": {"file": "src/FileController.java", "line": 4},
            },
            "path_access",
            "public byte[] readFile",
        ),
        (
            "HPE",
            "src/OrderService.java",
            "class OrderService {\n"
            '  Long orderId = Long.valueOf(request.getParameter("orderId"));\n'
            "  Long currentUserId = auth.getCurrentUserId();\n"
            "  checkPermission(currentUserId, orderId);\n"
            "  return orderMapper.selectById(orderId);\n"
            "}\n",
            {
                "file_path": "src/OrderService.java",
                "line_start": 5,
                "source": {"file": "src/OrderService.java", "line": 2},
                "sink": {"file": "src/OrderService.java", "line": 5},
            },
            "authorization_check",
            "checkPermission",
        ),
        (
            "MISCONFIG",
            "application.yml",
            "management:\n"
            "  endpoints:\n"
            "    web:\n"
            "      exposure:\n"
            "        include: '*'\n"
            "spring:\n"
            "  profiles:\n"
            "    active: dev\n",
            {
                "file_path": "application.yml",
                "line_start": 1,
                "source": {},
                "sink": {},
            },
            "config_block",
            "management:",
        ),
    ],
)
def test_build_profile_source_highlights_for_priority_profiles(
    tmp_path: Path,
    profile: str,
    file_path: str,
    content: str,
    draft: dict[str, object],
    expected_kind: str,
    expected_text: str,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    target = tmp_path / str(version_id) / "source" / Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    settings.snapshot_storage_root = str(tmp_path)
    try:
        highlights = scan_service_module._build_profile_source_highlights(
            version_id=version_id,
            draft={
                "rule_key": f"test_{profile.lower()}",
                "vuln_type": profile,
                **draft,
            },
            profile=profile,
            data_flow_chain=[],
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert highlights
    assert expected_kind in {item["kind"] for item in highlights}
    assert any(expected_text in item["snippet"] for item in highlights)


def test_build_profile_source_highlights_skips_disabled_rules(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    target = tmp_path / str(version_id) / "source" / "src" / "FastjsonService.java"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "class FastjsonService {\n"
        "  public Object parse(String body) {\n"
        "    return JSON.parseObject(body, UserDto.class);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    settings.snapshot_storage_root = str(tmp_path)
    try:
        highlights = scan_service_module._build_profile_source_highlights(
            version_id=version_id,
            draft={
                "rule_key": "any_fastjson_deserialization",
                "rule_enabled": False,
                "vuln_type": "DESERIALIZATION",
                "file_path": "src/FastjsonService.java",
                "line_start": 3,
                "source": {"file": "src/FastjsonService.java", "line": 2},
                "sink": {"file": "src/FastjsonService.java", "line": 3},
            },
            profile="DESERIALIZATION",
            data_flow_chain=[],
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert highlights == []


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


def test_normalize_finding_drafts_prefers_explicit_severity() -> None:
    drafts = scan_service_module._normalize_finding_drafts(
        findings=[
            {
                "rule_key": "any_any_xss",
                "severity": "low",
                "file_path": "src/Main.java",
            }
        ],
        rule_meta_by_key={
            "any_any_xss": SimpleNamespace(
                enabled=True,
                active_version=3,
                vuln_type="XSS",
                default_severity="HIGH",
            )
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["severity"] == "LOW"


def test_normalize_finding_drafts_uses_rule_default_severity_when_missing() -> None:
    drafts = scan_service_module._normalize_finding_drafts(
        findings=[
            {
                "rule_key": "other_fastjson_deserialization",
                "file_path": "src/Main.java",
            }
        ],
        rule_meta_by_key={
            "other_fastjson_deserialization": SimpleNamespace(
                enabled=True,
                active_version=1,
                vuln_type="DESERIALIZATION",
                default_severity="HIGH",
            )
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["severity"] == "HIGH"


def test_normalize_finding_drafts_infers_severity_from_rule_key_when_meta_missing() -> None:
    drafts = scan_service_module._normalize_finding_drafts(
        findings=[
            {
                "rule_key": "any_any_xxe",
                "file_path": "src/Main.java",
            }
        ],
        rule_meta_by_key={},
    )

    assert len(drafts) == 1
    assert drafts[0]["severity"] == "HIGH"


def test_normalize_finding_drafts_falls_back_to_med_when_sources_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan_service_module, "infer_rule_severity", lambda _rule_key: "??")

    drafts = scan_service_module._normalize_finding_drafts(
        findings=[
            {
                "rule_key": "custom_safe_rule",
                "file_path": "src/Main.java",
            }
        ],
        rule_meta_by_key={
            "custom_safe_rule": SimpleNamespace(
                enabled=True,
                active_version=1,
                vuln_type="CUSTOM",
                default_severity="unknown",
            )
        },
    )

    assert len(drafts) == 1
    assert drafts[0]["severity"] == "MED"


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
        "repair_external_finding_candidate",
        lambda **kwargs: {
            **finding_payload,
            "source_line": 21,
            "sink_line": 23,
            "path_length": 2,
            "evidence": {
                "match_kind": "path",
                "edge_types": ["REF", "ARG"],
                "repair_status": "java_repaired",
            },
            "paths": [
                {
                    **finding_payload["paths"][0],
                    "steps": [
                        finding_payload["paths"][0]["steps"][0],
                        {
                            "step_id": 1,
                            "labels": ["Var", "Identifier"],
                            "file": "src/Main.java",
                            "line": 23,
                            "display_name": "content",
                            "node_ref": "id-node",
                        },
                        finding_payload["paths"][0]["steps"][2],
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
        },
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
        "repair_external_finding_candidate",
        lambda **kwargs: {
            **finding_payload,
            "paths": [],
            "has_path": False,
            "path_length": None,
            "evidence": {
                "match_kind": "path",
                "edge_types": ["ARG", "HAS_CALL"],
                "repair_status": "downgraded_no_path",
            },
        },
    )

    refined = scan_service_module._refine_external_finding_paths_with_runtime(
        job=job,
        finding_payload=finding_payload,
    )

    assert refined["paths"] == []
    assert refined["has_path"] is False
    assert refined["evidence"]["edge_types"] == ["ARG", "HAS_CALL"]
    assert refined["evidence"]["repair_status"] == "downgraded_no_path"


def test_persist_external_finding_live_replaces_weaker_duplicate(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project(name="demo")
    db_session.add(project)
    db_session.flush()
    version = Version(project_id=project.id, name="v1", status="READY")
    db_session.add(version)
    db_session.flush()
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        payload={},
        result_summary={},
    )
    db_session.add(job)
    db_session.commit()

    service_finding = {
        "rule_key": "any_mybatis_sqli",
        "severity": "MED",
        "file_path": "src/service/ProductOrderServiceImpl.java",
        "line_start": 44,
        "line_end": 44,
        "source_file": "src/controller/OrderController.java",
        "source_line": 144,
        "sink_file": "src/service/ProductOrderServiceImpl.java",
        "sink_line": 44,
        "has_path": True,
        "path_length": 5,
        "evidence": {
            "match_kind": "path",
            "repair_status": "normalized",
            "coarse_dedupe_key": "any_mybatis_sqli|src/controller/ordercontroller.java:144|op|select",
            "dedupe_score": 58,
            "edge_types": ["SRC_FLOW", "PARAM_PASS", "REF"],
        },
        "paths": [
            {
                "path_id": 0,
                "path_length": 5,
                "steps": [
                    {
                        "step_id": 0,
                        "labels": ["Var", "Argument"],
                        "file": "src/controller/OrderController.java",
                        "line": 144,
                        "display_name": "orderBy",
                        "symbol_name": "orderBy",
                        "node_kind": "Var",
                        "node_ref": "src-order-by",
                    },
                    {
                        "step_id": 1,
                        "labels": ["Var"],
                        "file": "src/service/ProductOrderServiceImpl.java",
                        "line": 44,
                        "display_name": "orderUtil",
                        "symbol_name": "orderUtil",
                        "node_kind": "Var",
                        "node_ref": "service-order-util",
                    },
                ],
                "nodes": [
                    {
                        "node_id": 0,
                        "labels": ["Var", "Argument"],
                        "file": "src/controller/OrderController.java",
                        "line": 144,
                        "display_name": "orderBy",
                        "symbol_name": "orderBy",
                        "node_kind": "Var",
                        "node_ref": "src-order-by",
                        "raw_props": {"id": "src-order-by", "name": "orderBy"},
                    },
                    {
                        "node_id": 1,
                        "labels": ["Var"],
                        "file": "src/service/ProductOrderServiceImpl.java",
                        "line": 44,
                        "display_name": "orderUtil",
                        "symbol_name": "orderUtil",
                        "node_kind": "Var",
                        "node_ref": "service-order-util",
                        "raw_props": {"id": "service-order-util", "name": "orderUtil"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": 0,
                        "edge_type": "SRC_FLOW",
                        "from_step_id": 0,
                        "to_step_id": 1,
                        "props_json": {"kind": "assign"},
                    }
                ],
            }
        ],
    }
    mapper_finding = {
        **service_finding,
        "file_path": "src/dao/ProductOrderMapper.java",
        "line_start": 19,
        "line_end": 19,
        "sink_file": "src/dao/ProductOrderMapper.java",
        "sink_line": 19,
        "evidence": {
            **service_finding["evidence"],
            "dedupe_score": 72,
        },
        "paths": [
            {
                **service_finding["paths"][0],
                "steps": [
                    service_finding["paths"][0]["steps"][0],
                    {
                        "step_id": 1,
                        "labels": ["Var"],
                        "file": "src/dao/ProductOrderMapper.java",
                        "line": 19,
                        "display_name": "orderUtil",
                        "symbol_name": "orderUtil",
                        "node_kind": "Var",
                        "node_ref": "mapper-order-util",
                    },
                ],
                "nodes": [
                    service_finding["paths"][0]["nodes"][0],
                    {
                        "node_id": 1,
                        "labels": ["Var"],
                        "file": "src/dao/ProductOrderMapper.java",
                        "line": 19,
                        "display_name": "orderUtil",
                        "symbol_name": "orderUtil",
                        "node_kind": "Var",
                        "node_ref": "mapper-order-util",
                        "raw_props": {"id": "mapper-order-util", "name": "orderUtil"},
                    },
                ],
            }
        ],
    }

    queue = [service_finding, mapper_finding]
    monkeypatch.setattr(
        scan_service_module,
        "process_external_finding_candidate",
        lambda **kwargs: queue.pop(0),
    )

    first = scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "any_mybatis_sqli"},
        seen_fingerprints=None,
    )
    second = scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "any_mybatis_sqli"},
        seen_fingerprints=None,
    )

    stored = (
        db_session.query(scan_service_module.Finding).filter_by(job_id=job.id).all()
    )

    assert first is not None
    assert second is not None
    assert len(stored) == 1
    assert stored[0].file_path == "src/dao/ProductOrderMapper.java"
    assert stored[0].evidence_json["dedupe_score"] == 72


def test_persist_external_finding_live_uses_rule_default_severity_when_missing(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project(name="demo")
    db_session.add(project)
    db_session.flush()
    version = Version(project_id=project.id, name="v1", status="READY")
    db_session.add(version)
    db_session.flush()
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        payload={},
        result_summary={},
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        scan_service_module,
        "process_external_finding_candidate",
        lambda **kwargs: {
            "rule_key": "other_fastjson_deserialization",
            "file_path": "src/Main.java",
            "line_start": 42,
            "line_end": 42,
            "source_file": "src/Main.java",
            "source_line": 12,
            "sink_file": "src/Main.java",
            "sink_line": 42,
            "vuln_type": "DESERIALIZATION",
            "has_path": False,
            "path_length": None,
            "paths": [],
            "evidence": {"repair_status": "node_only"},
        },
    )
    monkeypatch.setattr(
        scan_service_module,
        "get_rules_by_keys",
        lambda rule_keys: {
            "other_fastjson_deserialization": SimpleNamespace(
                enabled=True,
                active_version=1,
                vuln_type="DESERIALIZATION",
                default_severity="HIGH",
            )
        },
    )

    persisted = scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "other_fastjson_deserialization"},
        seen_fingerprints=None,
    )

    stored = (
        db_session.query(scan_service_module.Finding).filter_by(job_id=job.id).all()
    )

    assert persisted is not None
    assert persisted["finding"]["severity"] == "HIGH"
    assert len(stored) == 1
    assert stored[0].severity == "HIGH"


def test_persist_external_finding_live_keeps_different_business_entries(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project(name="demo")
    db_session.add(project)
    db_session.flush()
    version = Version(project_id=project.id, name="v1", status="READY")
    db_session.add(version)
    db_session.flush()
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        payload={},
        result_summary={},
    )
    db_session.add(job)
    db_session.commit()

    first_finding = {
        "rule_key": "any_mybatis_sqli",
        "severity": "MED",
        "file_path": "src/dao/ProductMapper.java",
        "line_start": 17,
        "line_end": 17,
        "source_file": "src/controller/AdminProductController.java",
        "source_line": 372,
        "sink_file": "src/dao/ProductMapper.java",
        "sink_line": 17,
        "has_path": True,
        "path_length": 3,
        "evidence": {
            "match_kind": "path",
            "repair_status": "normalized",
            "coarse_dedupe_key": "any_mybatis_sqli|src/controller/adminproductcontroller.java:372|op|select",
            "dedupe_score": 82,
        },
        "paths": [],
    }
    second_finding = {
        **first_finding,
        "source_file": "src/controller/ForeProductListController.java",
        "source_line": 128,
        "evidence": {
            "match_kind": "path",
            "repair_status": "normalized",
            "coarse_dedupe_key": "any_mybatis_sqli|src/controller/foreproductlistcontroller.java:128|op|select",
            "dedupe_score": 82,
        },
    }

    queue = [first_finding, second_finding]
    monkeypatch.setattr(
        scan_service_module,
        "process_external_finding_candidate",
        lambda **kwargs: queue.pop(0),
    )

    scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "any_mybatis_sqli"},
        seen_fingerprints=None,
    )
    scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "any_mybatis_sqli"},
        seen_fingerprints=None,
    )

    stored = (
        db_session.query(scan_service_module.Finding)
        .filter_by(job_id=job.id)
        .order_by(scan_service_module.Finding.source_line.asc())
        .all()
    )

    assert len(stored) == 2
    assert {item.source_line for item in stored} == {128, 372}


def test_persist_external_finding_live_skips_downgraded_broken_path(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project(name="demo")
    db_session.add(project)
    db_session.flush()
    version = Version(project_id=project.id, name="v1", status="READY")
    db_session.add(version)
    db_session.flush()
    job = Job(
        project_id=project.id,
        version_id=version.id,
        job_type=JobType.SCAN.value,
        status=JobStatus.RUNNING.value,
        stage=JobStage.QUERY.value,
        payload={},
        result_summary={},
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        scan_service_module,
        "process_external_finding_candidate",
        lambda **kwargs: {
            "rule_key": "any_any_upload",
            "severity": "MED",
            "file_path": "src/Main.java",
            "line_start": 10,
            "line_end": 10,
            "source_file": "src/Main.java",
            "source_line": 2,
            "sink_file": "src/Main.java",
            "sink_line": 10,
            "has_path": False,
            "path_length": None,
            "paths": [],
            "evidence": {
                "repair_status": "downgraded_no_path",
                "candidate_edge_types": ["ARG", "HAS_CALL"],
            },
        },
    )

    persisted = scan_service_module._persist_external_finding_live(
        job=job,
        db_bind=db_session.get_bind(),
        raw_finding={"rule_key": "any_any_upload", "has_path": True, "paths": [{}]},
        seen_fingerprints=None,
    )

    stored = (
        db_session.query(scan_service_module.Finding).filter_by(job_id=job.id).all()
    )

    assert persisted is None
    assert stored == []


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
