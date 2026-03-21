from __future__ import annotations

import pytest

from app.services.assessment_context_service import (
    build_assessment_extraction,
    resolve_assessment_profile,
)
from app.services.rule_file_service import _infer_vuln_type


@pytest.mark.parametrize(
    ("rule_key", "vuln_type", "expected"),
    [
        ("any_any_cmdi", "RCE", "CMDI"),
        ("any_spel_codei", "RCE", "CODEI"),
        ("any_jndi_jndii", None, "JNDII"),
        ("any_any_ldapi", None, "LDAPI"),
        ("id_jdbc_hpe", None, "HPE"),
        ("origin_alloworigin_cors", None, "CORS"),
        ("config_actuator_misconfig", None, "MISCONFIG"),
        ("java_secret_hardcode", None, "HARDCODE_SECRET"),
        ("config_secret_weekpass", None, "WEAK_PASSWORD"),
        ("other_hash_weekhash", None, "WEAK_HASH"),
        ("cookie_response_cookiesecure", None, "COOKIE_FLAGS"),
        ("any_any_pathtraver", "PATH_TRAVERSAL", "PATHTRAVERSAL"),
        ("any_any_urlredirect", "OPEN_REDIRECT", "REDIRECT"),
    ],
)
def test_resolve_assessment_profile_covers_extended_categories(
    rule_key: str,
    vuln_type: str | None,
    expected: str,
) -> None:
    assert (
        resolve_assessment_profile(vuln_type=vuln_type, rule_key=rule_key) == expected
    )


def test_build_assessment_extraction_marks_sqli_controls_and_missing_evidence() -> None:
    extraction = build_assessment_extraction(
        rule_key="any_jdbc_sqli",
        vuln_type="SQLI",
        source={"file": "src/Main.java", "line": 12},
        sink={"file": "src/Main.java", "line": 14},
        trace_summary="request.id -> sql -> executeQuery",
        code_context={
            "source": '12: String userInput = request.getParameter("id");',
            "focus": '13: String sql = "select * from user where id=" + userInput;',
            "sink": "14: statement.executeQuery(sql);",
        },
        evidence={"items": ["request.id", "executeQuery"]},
        data_flow_chain=[
            {
                "step_order": 0,
                "location": "src/Main.java:12",
                "display_name": "userInput",
                "code_snippet": 'String userInput = request.getParameter("id");',
            },
            {
                "step_order": 1,
                "location": "src/Main.java:14",
                "display_name": "executeQuery",
                "code_snippet": "statement.executeQuery(sql);",
            },
        ],
    )

    assert extraction["profile"] == "SQLI"
    assert extraction["structured_facts"]["sql_string_contains_user_input"] == "yes"
    assert extraction["structured_facts"]["has_param_binding_calls"] == "no"
    assert extraction["filter_points"][0]["kind"] == "param_binding"
    assert extraction["filter_points"][0]["status"] == "missing"
    assert extraction["missing_evidence"]


def test_build_assessment_extraction_accepts_snapshot_style_code_context_and_source_highlights() -> (
    None
):
    extraction = build_assessment_extraction(
        rule_key="any_jdbc_sqli",
        vuln_type="SQLI",
        source={"file": "src/Main.java", "line": 12},
        sink={"file": "src/Main.java", "line": 16},
        trace_summary="request.id -> sql -> prepareStatement",
        code_context={
            "focus": {
                "file_path": "src/Main.java",
                "start_line": 13,
                "end_line": 16,
                "snippet": '13: String sql = "select * from user where id=" + userInput;\n14: PreparedStatement ps = connection.prepareStatement(sql);',
            },
            "source": {
                "file_path": "src/Main.java",
                "start_line": 12,
                "end_line": 12,
                "snippet": '12: String userInput = request.getParameter("id");',
            },
        },
        evidence={"items": ["request.id", "prepareStatement"]},
        data_flow_chain=[],
        source_highlights=[
            {
                "kind": "sql_binding",
                "location": "src/Main.java:14-15",
                "snippet": "14: PreparedStatement ps = connection.prepareStatement(sql);\n15: ps.setString(1, userInput);",
            }
        ],
    )

    assert extraction["general_facts"]["source_highlights_count"] == 1
    assert extraction["source_highlights"][0]["kind"] == "sql_binding"
    assert "prepareStatement" in extraction["expanded_code_context"]["focus"]


@pytest.mark.parametrize(
    ("rule_key", "vuln_type", "code_context", "expected_key", "expected_value"),
    [
        (
            "any_any_cmdi",
            "CMDI",
            {
                "focus": '@PreAuthorize("hasRole("ADMIN")")\nProcessBuilder pb = new ProcessBuilder("sh", "-c", "ls " + filepath);',
                "source": 'String filepath = request.getParameter("path");',
                "sink": "pb.start();",
            },
            "has_admin_gate",
            "yes",
        ),
        (
            "any_spel_codei",
            "CODEI",
            {
                "focus": "SimpleEvaluationContext context = SimpleEvaluationContext.forReadOnlyDataBinding().build();\nreturn parser.parseExpression(expr);",
                "source": 'String expr = request.getParameter("expr");',
                "sink": "return parser.parseExpression(expr);",
            },
            "has_expression_allowlist",
            "yes",
        ),
        (
            "any_jndi_jndii",
            "JNDII",
            {
                "focus": 'String jndiName = request.getParameter("jndiName");\nreturn ctx.lookup("ldap://127.0.0.1:1389/obj");',
                "source": 'String jndiName = request.getParameter("jndiName");',
                "sink": 'return ctx.lookup("ldap://127.0.0.1:1389/obj");',
            },
            "uses_remote_jndi_scheme",
            "yes",
        ),
        (
            "any_java_deserialization",
            "DESERIALIZATION",
            {
                "focus": "ParserConfig.getGlobalInstance().setSafeMode(true);\nreturn JSON.parseObject(body, UserDto.class);",
                "source": "String body = request.getBody();",
                "sink": "return JSON.parseObject(body, UserDto.class);",
            },
            "fastjson_safemode_enabled",
            "yes",
        ),
        (
            "java_secret_hardcode",
            "HARDCODE_SECRET",
            {
                "focus": 'dataSource.setPassword("p@ssw0rd");\nreturn DriverManager.getConnection(url, "admin", "p@ssw0rd");',
                "source": 'String password = "p@ssw0rd";',
                "sink": 'return DriverManager.getConnection(url, "admin", "p@ssw0rd");',
            },
            "used_in_connection_call",
            "yes",
        ),
        (
            "any_any_xss",
            "XSS",
            {
                "focus": 'response.getWriter().println(name);\nresponse.setHeader("Content-Security-Policy", "default-src self");',
                "source": 'String name = request.getParameter("name");',
                "sink": "response.getWriter().println(name);",
            },
            "uses_csp",
            "yes",
        ),
        (
            "any_thymeleaf_ssti",
            "SSTI",
            {
                "focus": "templateRepository.save(templateContent);\nreturn templateEngine.process(name, context);",
                "source": 'String templateContent = request.getParameter("tpl");',
                "sink": "return templateEngine.process(name, context);",
            },
            "template_source_persisted",
            "yes",
        ),
        (
            "any_any_urlredirect",
            "OPEN_REDIRECT",
            {
                "focus": 'String returnUrl = request.getParameter("returnUrl");\nresponse.sendRedirect(returnUrl);',
                "source": 'String returnUrl = request.getParameter("returnUrl");',
                "sink": "response.sendRedirect(returnUrl);",
            },
            "used_for_auth_flow",
            "yes",
        ),
        (
            "any_any_ldapi",
            "LDAPI",
            {
                "focus": 'String filter = String.format("(uid=%s)", uid);\nreturn dirContext.search(baseDn, filter, controls);',
                "source": 'String uid = request.getParameter("uid");',
                "sink": "return dirContext.search(baseDn, filter, controls);",
            },
            "filter_uses_string_interpolation",
            "yes",
        ),
        (
            "other_hash_weekhash",
            "WEAK_HASH",
            {
                "focus": 'MessageDigest md = MessageDigest.getInstance("MD5");\nreturn Hex.encodeHexString(md.digest(password.getBytes()));',
                "source": 'String password = request.getParameter("password");',
                "sink": "return Hex.encodeHexString(md.digest(password.getBytes()));",
            },
            "uses_message_digest_api",
            "yes",
        ),
        (
            "origin_alloworigin_cors",
            "CORS",
            {
                "focus": 'registry.addMapping("/**").allowedOrigins("*").allowCredentials(true);\nSecurityFilterChain chain = http.build();',
                "source": "",
                "sink": 'response.setHeader("Access-Control-Allow-Origin", origin);',
            },
            "configured_in_security_chain",
            "yes",
        ),
        (
            "cookie_response_cookiesecure",
            "COOKIE_FLAGS",
            {
                "focus": 'Cookie cookie = new Cookie("JSESSIONID", token);\nresponse.addCookie(cookie);',
                "source": "String token = issueToken();",
                "sink": "response.addCookie(cookie);",
            },
            "cookie_written_to_response",
            "yes",
        ),
        (
            "exception_any_infoleak",
            "INFOLEAK",
            {
                "focus": "response.getWriter().println(ex.getMessage());\nex.printStackTrace();",
                "source": "Exception ex = caught;",
                "sink": "response.getWriter().println(ex.getMessage());",
            },
            "returns_exception_message",
            "yes",
        ),
        (
            "any_any_ssrf",
            "SSRF",
            {
                "focus": "Proxy proxy = new Proxy(Proxy.Type.HTTP, addr);\nreturn client.newCall(request).execute();",
                "source": 'String url = request.getParameter("url");',
                "sink": "return client.newCall(request).execute();",
            },
            "uses_proxy_or_egress_gateway",
            "yes",
        ),
        (
            "any_any_upload",
            "UPLOAD",
            {
                "focus": 'String key = request.getParameter("dir") + "/" + file.getOriginalFilename();',
                "source": 'MultipartFile file = uploadRequest.getFile("file");',
                "sink": "s3Client.putObject(bucket, key, inputStream, metadata);",
            },
            "targets_object_storage",
            "yes",
        ),
        (
            "id_jdbc_hpe",
            "HPE",
            {
                "focus": "return orderMapper.selectById(orderId);",
                "source": 'Long orderId = Long.valueOf(request.getParameter("orderId"));',
                "sink": "return orderMapper.selectById(orderId);",
            },
            "query_uses_resource_id_only",
            "yes",
        ),
        (
            "any_any_pathtraver",
            "PATHTRAVERSAL",
            {
                "focus": "Path path = Paths.get(baseDir, URLDecoder.decode(fileName, UTF_8)).toRealPath();",
                "source": 'String fileName = request.getParameter("file");',
                "sink": "return Files.readAllBytes(path);",
            },
            "uses_real_path_resolution",
            "yes",
        ),
    ],
)
def test_build_assessment_extraction_refines_priority_profiles(
    rule_key: str,
    vuln_type: str,
    code_context: dict[str, str],
    expected_key: str,
    expected_value: str,
) -> None:
    extraction = build_assessment_extraction(
        rule_key=rule_key,
        vuln_type=vuln_type,
        source={"file": "src/Main.java", "line": 10},
        sink={"file": "src/Main.java", "line": 20},
        trace_summary="source -> sink",
        code_context=code_context,
        evidence={"items": ["source", "sink"]},
        data_flow_chain=[
            {
                "step_order": 0,
                "location": "src/Main.java:10",
                "display_name": "source",
                "code_snippet": code_context["source"],
            },
            {
                "step_order": 1,
                "location": "src/Main.java:20",
                "display_name": "sink",
                "code_snippet": code_context["sink"],
            },
        ],
    )

    assert extraction["profile"] == resolve_assessment_profile(
        vuln_type=vuln_type,
        rule_key=rule_key,
    )
    assert extraction["structured_facts"][expected_key] == expected_value
    assert extraction["expanded_code_context"]["path_steps"]


@pytest.mark.parametrize(
    ("rule_key", "expected"),
    [
        ("any_jndi_jndii", "JNDII"),
        ("any_any_ldapi", "LDAPI"),
        ("id_jdbc_hpe", "HPE"),
        ("origin_alloworigin_cors", "CORS"),
        ("config_actuator_misconfig", "MISCONFIG"),
        ("java_secret_hardcode", "HARDCODE_SECRET"),
        ("config_secret_weekpass", "WEAK_PASSWORD"),
        ("other_hash_weekhash", "WEAK_HASH"),
        ("cookie_response_cookiesecure", "COOKIE_FLAGS"),
        ("any_any_cmdi", "CMDI"),
        ("any_spel_codei", "CODEI"),
    ],
)
def test_infer_vuln_type_covers_extended_rule_keys(
    rule_key: str,
    expected: str,
) -> None:
    assert _infer_vuln_type(rule_key) == expected
