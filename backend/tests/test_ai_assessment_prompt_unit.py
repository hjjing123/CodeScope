from __future__ import annotations

from app.services.ai_service import (
    _render_assessment_user_prompt,
    _resolve_assessment_profile_key,
    _shrink_assessment_context_payload,
)


def test_resolve_assessment_profile_key_supports_extended_profiles() -> None:
    assert (
        _resolve_assessment_profile_key(vuln_type="RCE", rule_key="any_any_cmdi")
        == "CMDI"
    )
    assert (
        _resolve_assessment_profile_key(vuln_type="RCE", rule_key="any_spel_codei")
        == "CODEI"
    )
    assert (
        _resolve_assessment_profile_key(
            vuln_type="HARDCODE_SECRET",
            rule_key="java_secret_hardcode",
        )
        == "HARDCODE_SECRET"
    )
    assert (
        _resolve_assessment_profile_key(
            vuln_type="OPEN_REDIRECT",
            rule_key="any_any_urlredirect",
        )
        == "REDIRECT"
    )


def test_render_assessment_user_prompt_preserves_extraction_facts_when_shrinking() -> (
    None
):
    context_payload = {
        "finding_core": {
            "rule_key": "any_jdbc_sqli",
            "vuln_type": "SQLI",
        },
        "analysis_focus": {
            "trace_summary": "request.id -> sql -> executeQuery" * 30,
            "key_path_summary": "controller -> dao -> executeQuery" * 30,
            "why_flagged": "Untrusted input reaches a dynamic SQL sink." * 30,
            "data_flow_chain": [
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
                {
                    "step_order": 2,
                    "location": "src/Main.java:15",
                    "display_name": "render",
                    "code_snippet": "return result;",
                },
                {
                    "step_order": 3,
                    "location": "src/Main.java:16",
                    "display_name": "done",
                    "code_snippet": "return response;",
                },
            ],
        },
        "evidence_preview": ["item"] * 8,
        "code_context": {
            "focus": 'String sql = "select * from user where id=" + userInput;' * 60,
            "source": 'String userInput = request.getParameter("id");' * 60,
            "sink": "statement.executeQuery(sql);" * 60,
        },
        "extraction": {
            "profile": "SQLI",
            "structured_facts": {
                "sql_string_contains_user_input": "yes",
                "has_param_binding_calls": "no",
            },
            "source_highlights": [
                {
                    "kind": "sql_binding",
                    "location": "src/Main.java:14-15",
                    "snippet": "14: PreparedStatement ps = connection.prepareStatement(sql);\n15: ps.setString(1, userInput);",
                }
            ],
            "filter_points": [
                {
                    "kind": "param_binding",
                    "status": "missing",
                    "detail": "参数绑定或预编译语句",
                }
            ],
            "missing_evidence": ["确认是否真实使用参数绑定。"],
            "expanded_code_context": {
                "focus": 'String sql = "select * from user where id=" + userInput;'
                * 80,
                "source": 'String userInput = request.getParameter("id");' * 80,
                "sink": "statement.executeQuery(sql);" * 80,
                "path_steps": [
                    {"step_order": 0, "display_name": "userInput"},
                    {"step_order": 1, "display_name": "sql"},
                    {"step_order": 2, "display_name": "executeQuery"},
                    {"step_order": 3, "display_name": "render"},
                ],
            },
        },
    }

    shrunk = False
    for _ in range(80):
        changed = _shrink_assessment_context_payload(context_payload)
        if not changed:
            break
        shrunk = True

    prompt, budget_meta = _render_assessment_user_prompt(
        context_payload=context_payload,
        budget_meta={
            "max_context_tokens": 2048,
            "reserved_output_tokens": 512,
            "reserved_system_tokens": 256,
            "safety_margin_tokens": 128,
            "max_input_tokens": 8000,
            "profile": "SQLI",
            "rule_hint_applied": False,
        },
    )

    assert shrunk is True
    assert budget_meta["input_tokens_estimate"] <= budget_meta["max_input_tokens"]
    assert "structured_facts" in prompt
    assert "sql_string_contains_user_input" in prompt
    assert "source_highlights" in prompt
    assert (
        context_payload["extraction"]["structured_facts"]["has_param_binding_calls"]
        == "no"
    )
    assert context_payload["extraction"]["source_highlights"]
    assert context_payload["extraction"]["filter_points"]
    assert context_payload["extraction"]["missing_evidence"]
