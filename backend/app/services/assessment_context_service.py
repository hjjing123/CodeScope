from __future__ import annotations

YES = "yes"
NO = "no"
UNKNOWN = "unknown"

PROFILE_KEYS = {
    "GENERIC",
    "CMDI",
    "CODEI",
    "JNDII",
    "DESERIALIZATION",
    "SQLI",
    "SSRF",
    "UPLOAD",
    "PATHTRAVERSAL",
    "XXE",
    "XSS",
    "SSTI",
    "REDIRECT",
    "LDAPI",
    "HPE",
    "CORS",
    "MISCONFIG",
    "INFOLEAK",
    "HARDCODE_SECRET",
    "WEAK_PASSWORD",
    "WEAK_HASH",
    "COOKIE_FLAGS",
}

VULN_TYPE_ALIASES = {
    "OPEN_REDIRECT": "REDIRECT",
    "URLREDIRECT": "REDIRECT",
    "PATH_TRAVERSAL": "PATHTRAVERSAL",
    "FILE_UPLOAD": "UPLOAD",
    "INFO_LEAK": "INFOLEAK",
    "IDOR": "HPE",
    "HORIZONTAL_PRIVILEGE_ESCALATION": "HPE",
}

RULE_KEY_PROFILE_TOKENS: tuple[tuple[str, str], ...] = (
    ("weekpass", "WEAK_PASSWORD"),
    ("weakpass", "WEAK_PASSWORD"),
    ("weekhash", "WEAK_HASH"),
    ("weakhash", "WEAK_HASH"),
    ("cookiesecure", "COOKIE_FLAGS"),
    ("cookie", "COOKIE_FLAGS"),
    ("hardcode", "HARDCODE_SECRET"),
    ("alloworigin", "CORS"),
    ("cors", "CORS"),
    ("misconfig", "MISCONFIG"),
    ("actuator", "MISCONFIG"),
    ("swagger", "MISCONFIG"),
    ("druid", "MISCONFIG"),
    ("h2", "MISCONFIG"),
    ("infoleak", "INFOLEAK"),
    ("pathtraver", "PATHTRAVERSAL"),
    ("travers", "PATHTRAVERSAL"),
    ("urlredirect", "REDIRECT"),
    ("redirect", "REDIRECT"),
    ("ldapi", "LDAPI"),
    ("ldap", "LDAPI"),
    ("jndii", "JNDII"),
    ("jndi", "JNDII"),
    ("deserialization", "DESERIALIZATION"),
    ("sqli", "SQLI"),
    ("ssrf", "SSRF"),
    ("upload", "UPLOAD"),
    ("ssti", "SSTI"),
    ("xxe", "XXE"),
    ("xss", "XSS"),
    ("hpe", "HPE"),
    ("idor", "HPE"),
    ("cmdi", "CMDI"),
    ("codei", "CODEI"),
)

PROFILE_MISSING_EVIDENCE: dict[str, list[str]] = {
    "CMDI": [
        "确认命令参数是否真正由外部输入控制。",
        "确认是否存在命令白名单或固定命令模板。",
        "确认是否最终经由 shell 解释器执行。",
        "确认是否校验或转义 shell 特殊字符。",
    ],
    "CODEI": [
        "确认表达式或脚本内容是否可由外部输入控制。",
        "确认是否使用受限执行上下文或沙箱。",
        "确认是否仅解析而未执行危险表达式。",
        "确认是否存在类型、方法或反射目标白名单。",
    ],
    "JNDII": [
        "确认 lookup 参数是否可被远程请求控制。",
        "确认是否限制为 java:comp/env 等本地命名空间。",
        "确认 JDK 与 trustURLCodebase 等安全开关状态。",
    ],
    "DESERIALIZATION": [
        "确认不可信数据是否真正进入反序列化入口。",
        "确认是否存在类白名单、ObjectInputFilter 或 safeMode。",
        "确认相关依赖版本与可达 gadget 条件。",
    ],
    "SQLI": [
        "确认 SQL 是否由字符串拼接或动态片段构造。",
        "确认是否真实使用参数绑定而非仅调用 prepareStatement。",
        "确认排序字段、表名等动态片段是否受白名单约束。",
    ],
    "SSRF": [
        "确认目标 URL 或 host 是否可由外部输入控制。",
        "确认是否阻断私网、本机与云元数据地址访问。",
        "确认 DNS 解析、重定向与协议白名单策略。",
    ],
    "UPLOAD": [
        "确认文件名、对象 Key 或落盘路径是否可控。",
        "确认类型校验是否覆盖扩展名、MIME 与内容。",
        "确认上传结果是否可被公网访问、解析或覆盖敏感位置。",
    ],
    "PATHTRAVERSAL": [
        "确认路径是否在 decode 后再做 normalize/canonical 校验。",
        "确认是否强制限制在预期根目录内。",
        "确认是否存在符号链接或 Windows 路径绕过。",
    ],
    "XXE": [
        "确认 XML 输入是否可由外部控制。",
        "确认是否禁用 DOCTYPE、外部实体和外部资源访问。",
        "确认解析结果是否会回显或触发 SSRF。",
    ],
    "XSS": [
        "确认输出位置是否为 HTML、属性或脚本上下文。",
        "确认是否存在正确的上下文编码或模板自动转义。",
        "确认数据是否可能成为存储型 XSS。",
    ],
    "SSTI": [
        "确认用户是否控制模板内容而不是仅控制变量值。",
        "确认模板引擎是否开启危险表达式能力或对象访问。",
        "确认是否存在模板沙箱或语法白名单。",
    ],
    "REDIRECT": [
        "确认跳转目标是否可控且允许绝对 URL。",
        "确认是否限制为相对路径或白名单域名。",
        "确认是否用于 OAuth、登录回跳等高风险场景。",
    ],
    "LDAPI": [
        "确认 LDAP filter 是否由外部输入拼接。",
        "确认是否做 LDAP 特殊字符转义或参数化查询。",
        "确认搜索基准与返回属性范围是否受限。",
    ],
    "HPE": [
        "确认资源查询是否同时约束 userId 或 tenantId。",
        "确认是否存在 checkPermission、@PreAuthorize 或 owner 校验。",
        "确认资源 ID 是否可枚举且接口可匿名触发。",
    ],
    "CORS": [
        "确认跨域策略是否应用到敏感接口。",
        "确认是否同时允许凭证并反射或通配 Origin。",
        "确认代理层是否覆写或收紧响应头。",
    ],
    "MISCONFIG": [
        "确认危险配置是否在生产 profile 生效。",
        "确认管理端点是否受鉴权、IP 白名单或网关保护。",
        "确认是否真实暴露到公网或仅开发环境可达。",
    ],
    "INFOLEAK": [
        "确认异常细节是否返回给客户端而非仅写日志。",
        "确认生产环境是否隐藏堆栈和内部路径。",
        "确认是否存在统一异常处理与脱敏策略。",
    ],
    "HARDCODE_SECRET": [
        "确认命中字面量是否为真实密钥而非占位值。",
        "确认是否进入运行时代码或生产构建。",
        "确认是否支持通过环境变量或配置中心轮换。",
    ],
    "WEAK_PASSWORD": [
        "确认弱口令是否用于默认账号或生产环境。",
        "确认是否可被 profile、环境变量或部署参数覆盖。",
        "确认是否存在强制改密、限速或 MFA 补偿控制。",
    ],
    "WEAK_HASH": [
        "确认弱哈希是否用于密码、签名或鉴权场景。",
        "确认是否存在盐、迭代或迁移兼容策略。",
        "确认该算法是否仅用于非安全用途。",
    ],
    "COOKIE_FLAGS": [
        "确认 Cookie 是否承载敏感会话或认证信息。",
        "确认是否设置 HttpOnly、Secure 与 SameSite。",
        "确认是否仅在 HTTPS 场景下发送。",
    ],
}


def resolve_assessment_profile(*, vuln_type: str | None, rule_key: str | None) -> str:
    normalized_rule_key = str(rule_key or "").strip().lower()
    normalized_vuln_type = str(vuln_type or "").strip().upper()
    normalized_vuln_type = VULN_TYPE_ALIASES.get(
        normalized_vuln_type, normalized_vuln_type
    )
    if normalized_vuln_type == "RCE":
        if "cmdi" in normalized_rule_key:
            return "CMDI"
        if "codei" in normalized_rule_key:
            return "CODEI"
    if normalized_vuln_type in PROFILE_KEYS:
        return normalized_vuln_type
    for token, profile in RULE_KEY_PROFILE_TOKENS:
        if token in normalized_rule_key:
            return profile
    return "GENERIC"


def build_assessment_extraction(
    *,
    rule_key: str | None,
    vuln_type: str | None,
    source: dict[str, object] | None,
    sink: dict[str, object] | None,
    trace_summary: str | None,
    code_context: dict[str, object] | None,
    evidence: dict[str, object] | None,
    data_flow_chain: list[dict[str, object]] | None = None,
    source_highlights: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    profile = resolve_assessment_profile(vuln_type=vuln_type, rule_key=rule_key)
    normalized_source = _normalize_location(source)
    normalized_sink = _normalize_location(sink)
    normalized_code_context = _normalize_code_context(code_context)
    normalized_chain = _normalize_data_flow_chain(data_flow_chain)
    normalized_evidence = evidence if isinstance(evidence, dict) else {}
    normalized_source_highlights = _normalize_source_highlights(source_highlights)
    text_bundle = _build_text_bundle(
        rule_key=rule_key,
        vuln_type=vuln_type,
        trace_summary=trace_summary,
        code_context=normalized_code_context,
        evidence=normalized_evidence,
        data_flow_chain=normalized_chain,
        source_highlights=normalized_source_highlights,
    )
    structured_facts = _build_profile_structured_facts(
        profile=profile,
        bundle=text_bundle,
        source=normalized_source,
        sink=normalized_sink,
        evidence=normalized_evidence,
        data_flow_chain=normalized_chain,
    )
    return {
        "profile": profile,
        "general_facts": {
            "source_available": YES if normalized_source["file"] else NO,
            "sink_available": YES if normalized_sink["file"] else NO,
            "path_available": YES if normalized_chain else NO,
            "code_context_available": YES if normalized_code_context else NO,
            "flow_steps_count": len(normalized_chain),
            "source_highlights_count": len(normalized_source_highlights),
        },
        "structured_facts": structured_facts,
        "source_highlights": normalized_source_highlights,
        "filter_points": _build_filter_points(
            profile=profile,
            structured_facts=structured_facts,
            bundle=text_bundle,
        ),
        "missing_evidence": _build_missing_evidence(
            profile=profile,
            structured_facts=structured_facts,
        ),
        "expanded_code_context": _build_expanded_code_context(
            code_context=normalized_code_context,
            data_flow_chain=normalized_chain,
        ),
    }


def _normalize_location(payload: dict[str, object] | None) -> dict[str, object]:
    item = payload if isinstance(payload, dict) else {}
    return {
        "file": str(item.get("file") or "").strip() or None,
        "line": _to_int(item.get("line")),
    }


def _normalize_code_context(payload: dict[str, object] | None) -> dict[str, str]:
    item = payload if isinstance(payload, dict) else {}
    normalized: dict[str, str] = {}
    for key in ("focus", "source", "sink"):
        text = _normalize_code_context_text(item.get(key))
        if text:
            normalized[key] = text
    return normalized


def _normalize_code_context_text(value: object) -> str | None:
    if isinstance(value, dict):
        snippet = _normalize_text(value.get("snippet"))
        if snippet:
            return snippet
        file_path = _normalize_text(value.get("file_path"))
        start_line = _to_int(value.get("start_line"))
        end_line = _to_int(value.get("end_line"))
        if file_path and start_line is not None and end_line is not None:
            return f"{file_path}:{start_line}-{end_line}"
        if file_path and start_line is not None:
            return f"{file_path}:{start_line}"
        return file_path
    return _normalize_text(value)


def _normalize_data_flow_chain(
    payload: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    items: list[dict[str, object]] = []
    for raw in payload[:8]:
        if not isinstance(raw, dict):
            continue
        item = {
            "step_order": _to_int(raw.get("step_order")),
            "location": _normalize_text(raw.get("location")),
            "display_name": _normalize_text(raw.get("display_name")),
            "node_kind": _normalize_text(raw.get("node_kind")),
            "code_snippet": _normalize_text(raw.get("code_snippet")),
            "edge_to_next": _normalize_text(raw.get("edge_to_next")),
        }
        if any(item.values()):
            items.append(item)
    return items


def _build_text_bundle(
    *,
    rule_key: str | None,
    vuln_type: str | None,
    trace_summary: str | None,
    code_context: dict[str, str],
    evidence: dict[str, object],
    data_flow_chain: list[dict[str, object]],
    source_highlights: list[dict[str, object]],
) -> dict[str, object]:
    parts = [
        str(rule_key or "").strip(),
        str(vuln_type or "").strip(),
        str(trace_summary or "").strip(),
    ]
    parts.extend(code_context.values())
    for item in data_flow_chain:
        _collect_text_fragments(item, parts=parts)
    for item in source_highlights:
        _collect_text_fragments(item, parts=parts)
    _collect_text_fragments(evidence, parts=parts)
    combined = "\n".join(part for part in parts if part)
    return {
        "combined": combined,
        "combined_lower": combined.lower(),
        "focus": code_context.get("focus", ""),
        "source": code_context.get("source", ""),
        "sink": code_context.get("sink", ""),
    }


def _normalize_source_highlights(
    payload: list[dict[str, object]] | None,
) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []
    items: list[dict[str, str]] = []
    for raw in payload[:6]:
        if not isinstance(raw, dict):
            continue
        kind = _normalize_text(raw.get("kind"))
        location = _normalize_text(raw.get("location"))
        snippet = _normalize_text(raw.get("snippet"))
        if not kind or not snippet:
            continue
        item = {
            "kind": kind,
            "location": location or "-",
            "snippet": _truncate_text(snippet, 500),
        }
        items.append(item)
    return items


def _build_profile_structured_facts(
    *,
    profile: str,
    bundle: dict[str, object],
    source: dict[str, object],
    sink: dict[str, object],
    evidence: dict[str, object],
    data_flow_chain: list[dict[str, object]],
) -> dict[str, object]:
    risky_input = bool(source.get("file"))
    if profile == "CMDI":
        shell_wrapper = _has_any(
            bundle, "sh -c", "bash -c", "cmd /c", "powershell -command"
        ) or (
            _has_any(bundle, '"-c"', '"/c"')
            and _has_any(bundle, '"sh"', '"bash"', '"cmd"', "powershell")
        )
        user_input = risky_input and _has_any(
            bundle,
            "+",
            "string.format",
            "formatter",
            "getparameter",
            "requestparam",
            "filepath",
            "command",
        )
        allowlist = _has_any(
            bundle,
            "allowlist",
            "whitelist",
            "approvedcommands",
            "allowedcommands",
        )
        escaped = _has_any(
            bundle,
            "escapeshell",
            "quotedstring",
            "sanitize",
            "replaceall",
            "matches(",
        )
        return {
            "uses_runtime_exec": _to_flag(
                _has_any(bundle, "runtime.getruntime().exec", ".exec(")
            ),
            "uses_processbuilder": _to_flag(_has_any(bundle, "processbuilder")),
            "command_is_constant": _constant_command_flag(
                bundle=bundle, risky=user_input
            ),
            "command_includes_user_input": _to_flag(user_input),
            "has_command_allowlist": _control_flag(control=allowlist, risky=user_input),
            "splits_args_safely": _safe_args_flag(
                bundle=bundle, shell_wrapper=shell_wrapper
            ),
            "escapes_or_validates_shell_meta_chars": _control_flag(
                control=escaped,
                risky=user_input,
            ),
            "uses_shell_wrapper": _to_flag(shell_wrapper),
            "command_template_has_placeholder": _to_flag(
                _has_any(bundle, "%s", "{}", "format", "placeholder")
            ),
            "command_passes_through_intermediate_var": _to_flag(
                _has_any(bundle, "cmd", "command", "cmdlist", "args")
            ),
            "has_admin_gate": _to_flag(
                _has_any(bundle, "@preauthorize", "hasrole", "isadmin", "adminonly")
            ),
            "returns_command_output": _to_flag(
                _has_any(
                    bundle,
                    "getinputstream",
                    "bufferedreader",
                    "inputstreamreader",
                    "response.getwriter",
                    "sendoutput",
                )
            ),
        }
    if profile == "CODEI":
        user_controlled = risky_input and _has_any(
            bundle,
            "getparameter",
            "requestbody",
            "expression",
            "spel",
            "ognl",
            "script",
            "+",
        )
        return {
            "expression_source_user_controlled": _to_flag(user_controlled),
            "uses_standard_evaluation_context": _to_flag(
                _has_any(bundle, "standardevaluationcontext")
            ),
            "uses_simple_evaluation_context": _to_flag(
                _has_any(bundle, "simpleevaluationcontext")
            ),
            "allows_type_reference": _to_flag(
                _has_any(bundle, "t(", "typelocator", "class.forname")
            ),
            "allows_constructor_call": _to_flag(
                _has_any(bundle, "newinstance", "new ", "constructor")
            ),
            "uses_script_engine_eval": _to_flag(
                _has_any(
                    bundle,
                    "scriptengine.eval",
                    "groovyshell",
                    "jshell",
                    "beanshell",
                    "ognl",
                    "mvel",
                )
            ),
            "reflect_target_user_controlled": _to_flag(
                user_controlled
                and _has_any(bundle, "class.forname", "method.invoke", "reflection")
            ),
            "parse_only_without_execution": _to_flag(
                _has_any(bundle, "parseexpression", "createvalueexpression")
                and not _has_any(
                    bundle,
                    "getvalue(",
                    ".eval(",
                    "scriptengine.eval",
                    "method.invoke",
                    "class.forname",
                )
            ),
            "has_expression_allowlist": _to_flag(
                _has_any(
                    bundle,
                    "allowlist",
                    "whitelist",
                    "resolver",
                    "simpleevaluationcontext",
                )
            ),
        }
    if profile == "JNDII":
        user_controlled = risky_input and _has_any(bundle, "lookup(", "jndi", "+")
        return {
            "lookup_arg_user_controlled": _to_flag(user_controlled),
            "scheme_allowlist_present": _control_flag(
                control=_has_any(bundle, "allowlist", "whitelist", "java:comp/env"),
                risky=user_controlled,
            ),
            "blocks_remote_codebase": _to_flag(
                _has_any(
                    bundle, "trusturlcodebase=false", "object.trusturlcodebase=false"
                )
            ),
            "network_egress_restricted": _to_flag(
                _has_any(bundle, "egress", "firewall", "proxy", "allowlist")
            ),
            "uses_fixed_jndi_name": _to_flag(_has_any(bundle, "java:comp/env")),
            "uses_remote_jndi_scheme": _to_flag(
                _has_any(bundle, "ldap://", "rmi://", "dns://")
            ),
        }
    if profile == "DESERIALIZATION":
        fastjson = _has_any(bundle, "json.parseobject", "fastjson")
        return {
            "deserializes_untrusted_input": _to_flag(
                risky_input
                and _has_any(
                    bundle,
                    "readobject",
                    "xmldecoder",
                    "json.parseobject",
                    "hessian",
                    "yaml.load",
                    "xstream",
                )
            ),
            "has_class_whitelist": _to_flag(
                _has_any(bundle, "allowlist", "whitelist", "acceptlist", "typefilter")
            ),
            "has_object_input_filter": _to_flag(_has_any(bundle, "objectinputfilter")),
            "fastjson_autotype_enabled": _to_flag(
                fastjson and _has_any(bundle, "autotype", "setautotypesupport(true)")
            ),
            "fastjson_safemode_enabled": _to_flag(
                fastjson and _has_any(bundle, "safemode", "safemode=true")
            ),
            "xmldecoder_used_on_untrusted_xml": _to_flag(
                risky_input and _has_any(bundle, "xmldecoder")
            ),
            "hessian_allows_nonserializable": _to_flag(
                _has_any(bundle, "allownonserializable")
            ),
        }
    if profile == "SQLI":
        prepared = _has_any(bundle, "preparestatement", "preparedstatement")
        binding = _has_any(bundle, "setstring", "setint", "setlong", "#{", "bind(")
        dynamic = _has_any(
            bundle, "${", "+", "string.format", ".apply(", ".last(", ".insql("
        )
        return {
            "uses_prepared_statement": _to_flag(prepared),
            "uses_statement_execute": _to_flag(
                _has_any(bundle, "statement.execute", "executequery(", "executeupdate(")
            ),
            "sql_string_contains_user_input": _to_flag(risky_input and dynamic),
            "has_param_binding_calls": _control_flag(control=binding, risky=dynamic),
            "mybatis_uses_dollar_syntax": _to_flag(_has_any(bundle, "${")),
            "orderby_field_allowlist": _to_flag(
                _has_any(bundle, "order by", "orderby")
                and _has_any(bundle, "allowlist", "whitelist", "enum", "allowedsort")
            ),
            "wrapper_apply_last_used": _to_flag(
                _has_any(bundle, ".apply(", ".last(", ".insql(")
            ),
            "path_crosses_mapper_or_dao": _to_flag(
                _has_any(bundle, "mapper", "repository", "dao", "jdbc")
            ),
            "query_uses_dynamic_fragment": _to_flag(dynamic),
        }
    if profile == "SSRF":
        url_controlled = risky_input and _has_any(
            bundle,
            "http://",
            "https://",
            "url(",
            "uri(",
            "+",
            "getparameter",
        )
        return {
            "url_user_controlled": _to_flag(url_controlled),
            "scheme_allowlist_present": _control_flag(
                control=_has_any(bundle, "allowlist", "whitelist", 'startswith("http'),
                risky=url_controlled,
            ),
            "blocks_private_ip": _to_flag(
                _has_any(
                    bundle,
                    "issitelocaladdress",
                    "isloopbackaddress",
                    "127.0.0.1",
                    "169.254.169.254",
                    "private ip",
                )
            ),
            "resolves_dns_before_allow": _to_flag(
                _has_any(bundle, "inetaddress.getbyname", "resolve", "dns")
            ),
            "follows_redirects": _to_flag(
                _has_any(
                    bundle, "followredirects(true)", "setinstancefollowredirects(true)"
                )
            ),
            "allows_gopher_file": _to_flag(_has_any(bundle, "gopher://", "file://")),
            "allows_custom_host_header": _to_flag(
                _has_any(
                    bundle, 'setheader("host"', 'addheader("host"', 'header("host"'
                )
            ),
            "uses_proxy_or_egress_gateway": _to_flag(
                _has_any(bundle, "proxy", "proxyselector", "gateway", "egress")
            ),
        }
    if profile == "UPLOAD":
        object_storage = _has_any(
            bundle, "putobject", "presigned", "minio", "ossclient", "s3client"
        )
        return {
            "uses_transfer_to": _to_flag(_has_any(bundle, "transferto")),
            "original_filename_used": _to_flag(
                _has_any(bundle, "getoriginalfilename", "filename", "objectkey")
            ),
            "path_or_object_key_user_controlled": _to_flag(
                risky_input and _has_any(bundle, "filename", "objectkey", "path", "+")
            ),
            "has_extension_allowlist": _to_flag(
                _has_any(bundle, "allowlist", "whitelist", "endswith", "contenttype")
            ),
            "checks_mime_or_content_type": _to_flag(
                _has_any(bundle, "mime", "contenttype", "mediatype")
            ),
            "stores_under_webroot": _to_flag(
                _has_any(bundle, "webroot", "static/", "public/")
            ),
            "returns_public_url_or_public_acl": _to_flag(
                object_storage
                and _has_any(bundle, "public-read", "presigned", "public url", "url")
            ),
            "targets_object_storage": _to_flag(object_storage),
            "targets_local_filesystem": _to_flag(
                _has_any(
                    bundle,
                    "transferto",
                    "files.write",
                    "fileoutputstream",
                    "filewriter",
                )
            ),
            "renames_or_randomizes_filename": _to_flag(
                _has_any(bundle, "uuid", "randomuuid", "timestamp", "rename")
            ),
        }
    if profile == "PATHTRAVERSAL":
        risky_path = risky_input and _has_any(
            bundle, "../", "..\\", "paths.get", "new file", "+"
        )
        return {
            "path_user_controlled": _to_flag(risky_path),
            "uses_paths_normalize": _to_flag(
                _has_any(bundle, "normalize()", ".normalize(")
            ),
            "uses_canonical_path_check": _to_flag(
                _has_any(bundle, "getcanonicalpath", "realpath")
            ),
            "enforces_base_directory": _to_flag(
                _has_any(bundle, "startswith(basedir", "prefix", "basedir")
            ),
            "rejects_dotdot": _to_flag(_has_any(bundle, "..", "dotdot")),
            "decodes_input_before_validation": _to_flag(
                _has_any(bundle, "urldecoder.decode", "decode(")
                and _has_any(bundle, "normalize(", "getcanonicalpath", "realpath")
            ),
            "uses_real_path_resolution": _to_flag(
                _has_any(bundle, "realpath", "torealpath")
            ),
        }
    if profile == "XXE":
        xml_controlled = risky_input or _has_any(
            bundle, "xml", "documentbuilder", "saxreader"
        )
        return {
            "xml_input_user_controlled": _to_flag(xml_controlled),
            "disallows_doctype": _to_flag(
                _has_any(bundle, "disallow-doctype-decl", "disallowdoctype")
            ),
            "external_entities_disabled": _to_flag(
                _has_any(
                    bundle,
                    "external-general-entities",
                    "external-parameter-entities",
                    "setexpandentityreferences(false)",
                )
            ),
            "secure_processing_enabled": _to_flag(
                _has_any(bundle, "feature_secure_processing", "secure_processing")
            ),
            "uses_safe_parser": _to_flag(
                _has_any(
                    bundle,
                    "secure_processing",
                    "saxparserfactory",
                    "documentbuilderfactory",
                )
            ),
        }
    if profile == "XSS":
        html_output = _has_any(
            bundle,
            "getwriter()",
            "printwriter",
            "writer.println",
            "th:utext",
            "velocity",
            "freemarker",
            "html",
        )
        return {
            "output_is_html_context": _to_flag(html_output),
            "output_escaped": _to_flag(
                _has_any(bundle, "escapehtml", "htmlutils", "stringescapeutils")
            ),
            "uses_template_autoescape": _to_flag(
                _has_any(bundle, "autoescape", "html escaping", "thymeleaf")
            ),
            "uses_unescaped_output_api": _to_flag(
                _has_any(bundle, "th:utext", "writer.println", "printf(", "print(")
            ),
            "stored_xss_possible": _to_flag(
                _has_any(bundle, "database", "repository", "persist", "stored")
            ),
            "uses_csp": _to_flag(
                _has_any(
                    bundle,
                    "content-security-policy",
                    'setheader("content-security-policy"',
                    'addheader("content-security-policy"',
                )
            ),
        }
    if profile == "SSTI":
        return {
            "template_content_user_controlled": _to_flag(
                risky_input
                and _has_any(bundle, "template", "puttemplate", "processtemplate")
            ),
            "only_template_vars_user_controlled": _to_flag(
                _has_any(bundle, "model.addattribute", "context.setvariable")
            ),
            "freemarker_allows_new_api": _to_flag(
                _has_any(bundle, "newbuiltinclassresolver", "templateclassresolver")
            ),
            "thymeleaf_allows_springel": _to_flag(
                _has_any(bundle, "thymeleaf", "springel")
            ),
            "has_template_sandbox": _to_flag(
                _has_any(bundle, "sandbox", "restricted", "safe mode")
            ),
            "template_source_persisted": _to_flag(
                _has_any(
                    bundle,
                    "repository",
                    "database",
                    "templatecontent",
                    "savetemplate",
                    "findtemplate",
                )
            ),
        }
    if profile == "REDIRECT":
        controlled = risky_input and _has_any(
            bundle, "sendredirect", "redirect:", "location"
        )
        return {
            "redirect_target_user_controlled": _to_flag(controlled),
            "allows_absolute_url": _to_flag(
                _has_any(bundle, "http://", "https://", "//")
            ),
            "scheme_allowlist_present": _control_flag(
                control=_has_any(bundle, "allowlist", "whitelist", "http", "https"),
                risky=controlled,
            ),
            "host_allowlist_present": _control_flag(
                control=_has_any(bundle, "alloweddomain", "allowedhost", "allowlist"),
                risky=controlled,
            ),
            "uses_relative_redirect_only": _to_flag(
                _has_any(bundle, 'startswith("/")', "relative")
            ),
            "used_for_auth_flow": _to_flag(
                _has_any(
                    bundle, "oauth", "login", "callback", "redirect_uri", "returnurl"
                )
            ),
        }
    if profile == "LDAPI":
        risky_filter = risky_input and _has_any(bundle, "search(", "filter", "uid=")
        return {
            "ldap_filter_user_controlled": _to_flag(risky_filter),
            "has_ldap_escape": _to_flag(
                _has_any(bundle, "ldapencoder", "escape", "filterescape")
            ),
            "uses_parameterized_ldap": _to_flag(
                _has_any(bundle, "searchcontrols", "filterargs", "querybuilder")
            ),
            "restricts_search_base": _to_flag(
                _has_any(bundle, "basedn", "searchbase", "ou=")
            ),
            "filter_uses_string_interpolation": _to_flag(
                _has_any(bundle, "string.format", "+", "uid=%s", "cn=%s")
            ),
        }
    if profile == "HPE":
        authz = _has_any(bundle, "checkpermission", "@preauthorize", "hasrole", "owner")
        scoped = _has_any(bundle, "userid", "tenantid", "currentuser", "ownerid")
        return {
            "authn_required": _to_flag(
                _has_any(bundle, "@authenticated", "session", "token", "login")
            ),
            "has_authorization_check": _control_flag(
                control=authz, risky=bool(sink.get("file"))
            ),
            "query_scoped_by_user": _control_flag(
                control=scoped, risky=bool(sink.get("file"))
            ),
            "uses_check_permission": _to_flag(_has_any(bundle, "checkpermission")),
            "resource_id_enumerable": _to_flag(
                risky_input and _has_any(bundle, "id", "orderid", "billid", "projectid")
            ),
            "query_uses_resource_id_only": _to_flag(
                _has_any(bundle, "where id", "findbyid", "selectbyid", "getbyid")
                and not scoped
            ),
            "authorization_signal_near_query": _to_flag(
                authz
                and _has_any(bundle, "query", "select", "mapper", "repository", "dao")
            ),
        }
    if profile == "CORS":
        return {
            "allow_origin_star": _to_flag(
                _has_any(
                    bundle,
                    'access-control-allow-origin", "*"',
                    'allow-origin", "*"',
                    'allowedorigins("*")',
                )
            ),
            "reflects_origin": _to_flag(
                _has_any(bundle, 'getheader("origin")', 'request.getheader("origin")')
            ),
            "allow_credentials_true": _to_flag(
                _has_any(bundle, "allow-credentials", "allowcredentials(true)")
            ),
            "origin_allowlist_present": _to_flag(
                _has_any(bundle, "allowlist", "whitelist", "allowedorigins")
            ),
            "cors_applies_to_sensitive_routes": _to_flag(
                _has_any(bundle, "cookie", "authorization", "token", "session")
            ),
            "configured_in_security_chain": _to_flag(
                _has_any(
                    bundle,
                    "corsregistry",
                    "corsconfiguration",
                    "corsconfigurationsource",
                    "securityfilterchain",
                )
            ),
        }
    if profile == "MISCONFIG":
        return {
            "enabled_in_config": _to_flag(
                _has_any(
                    bundle,
                    "enabled=true",
                    "web-allow-others=true",
                    "swagger",
                    "actuator",
                )
            ),
            "protected_by_auth": _to_flag(
                _has_any(
                    bundle,
                    "securityfilterchain",
                    "basicauth",
                    "loginusername",
                    "loginpassword",
                )
            ),
            "ip_restricted": _to_flag(
                _has_any(bundle, "allow", "deny", "ip", "whitelist")
            ),
            "exposed_to_public_network": _to_flag(
                _has_any(
                    bundle, "0.0.0.0", "public", "internet", "web-allow-others=true"
                )
            ),
            "only_dev_profile": _to_flag(
                _has_any(
                    bundle,
                    "dev",
                    "local",
                    '@profile("dev")',
                    "spring.profiles.active=dev",
                )
            ),
        }
    if profile == "INFOLEAK":
        stacktrace = _has_any(
            bundle, "getstacktrace", "printexception", "printstacktrace"
        )
        return {
            "stacktrace_sent_to_client": _to_flag(
                stacktrace
                and _has_any(
                    bundle, "writer", "response", "senderror", "model.addattribute"
                )
            ),
            "has_global_exception_handler": _to_flag(
                _has_any(bundle, "@controlleradvice", "@exceptionhandler")
            ),
            "only_logs_exception": _to_flag(
                stacktrace and _has_any(bundle, "logger.", "log.", "slf4j")
            ),
            "hides_details_in_prod": _to_flag(
                _has_any(
                    bundle,
                    "never",
                    "prod",
                    "include-message=never",
                    "include-stacktrace=never",
                )
            ),
            "returns_exception_message": _to_flag(
                _has_any(bundle, "getmessage", "exception.message")
                and _has_any(
                    bundle,
                    "writer",
                    "response",
                    "senderror",
                    "model.addattribute",
                )
            ),
        }
    if profile == "HARDCODE_SECRET":
        placeholder = _has_any(
            bundle, "changeme", "your-key", "example", "demo", "test"
        )
        return {
            "secret_is_literal": _to_flag(
                _has_any(
                    bundle, "password=", "secret=", "apikey=", "token=", "accesskey"
                )
            ),
            "secret_is_placeholder": _to_flag(placeholder),
            "used_in_runtime_code": _to_flag(
                _has_any(bundle, "datasource", "connect(", "setpassword", "setsecret")
            ),
            "in_test_or_example_only": _to_flag(
                _has_any(bundle, "test", "example", "sample")
            ),
            "rotatable_via_env": _to_flag(
                _has_any(bundle, "system.getenv", "@value", "vault", "config")
            ),
            "used_in_connection_call": _to_flag(
                _has_any(
                    bundle,
                    "getconnection(",
                    "connect(",
                    "setpassword(",
                    "setsecretkey(",
                    "secretkeyspec",
                )
            ),
        }
    if profile == "WEAK_PASSWORD":
        return {
            "value_is_weak_password": _to_flag(
                _has_any(bundle, "123456", "admin", "root", "password", "123123")
            ),
            "is_empty_password": _to_flag(
                _has_any(bundle, 'password=""', "password=''", "empty password")
            ),
            "applies_to_admin_account": _to_flag(
                _has_any(bundle, "admin", "root", "manager")
            ),
            "prod_profile_enabled": _to_flag(
                _has_any(bundle, "prod", "production", "release")
            ),
        }
    if profile == "WEAK_HASH":
        return {
            "uses_md5_or_sha1": _to_flag(_has_any(bundle, "md5", "sha-1", "sha1")),
            "used_for_password_hashing": _to_flag(
                _has_any(bundle, "password", "passwd", "credential")
            ),
            "has_salt": _to_flag(_has_any(bundle, "salt", "salted")),
            "used_for_signature": _to_flag(
                _has_any(bundle, "signature", "sign", "hmac")
            ),
            "legacy_compat_only": _to_flag(_has_any(bundle, "legacy", "compat")),
            "uses_message_digest_api": _to_flag(
                _has_any(
                    bundle,
                    "messagedigest.getinstance",
                    "digestutils.md5",
                    "digestutils.sha1",
                )
            ),
        }
    if profile == "COOKIE_FLAGS":
        return {
            "cookie_is_sensitive": _to_flag(
                _has_any(bundle, "jsessionid", "session", "token", "auth", "jwt")
            ),
            "cookie_http_only_set": _to_flag(_has_any(bundle, "sethttponly(true)")),
            "cookie_secure_set": _to_flag(_has_any(bundle, "setsecure(true)")),
            "cookie_samesite_set": _to_flag(
                _has_any(bundle, "samesite", "strict", "lax", "none")
            ),
            "sent_over_https_only": _to_flag(_has_any(bundle, "https", "secure=true")),
            "cookie_written_to_response": _to_flag(
                _has_any(bundle, "addcookie(", "setcookie(", "responsecookie.from")
            ),
        }
    generic_facts = {
        "source_to_sink_visible": _to_flag(
            bool(source.get("file")) and bool(sink.get("file"))
        ),
        "code_context_present": _to_flag(bool(bundle.get("combined"))),
        "path_chain_present": _to_flag(bool(data_flow_chain)),
    }
    if evidence:
        generic_facts["evidence_items_present"] = _to_flag(bool(evidence))
    return generic_facts


def _build_filter_points(
    *,
    profile: str,
    structured_facts: dict[str, object],
    bundle: dict[str, object],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if profile == "CMDI":
        _append_filter_point(
            items,
            "command_allowlist",
            structured_facts.get("has_command_allowlist"),
            "命令白名单或固定模板",
        )
        _append_filter_point(
            items,
            "shell_meta_validation",
            structured_facts.get("escapes_or_validates_shell_meta_chars"),
            "shell 特殊字符校验或转义",
        )
        _append_filter_point(
            items,
            "shell_wrapper",
            _invert_flag(structured_facts.get("uses_shell_wrapper")),
            "避免经由 shell 解释器执行",
        )
        _append_filter_point(
            items,
            "admin_gate",
            structured_facts.get("has_admin_gate"),
            "高风险命令入口应受权限边界保护",
        )
    elif profile == "CODEI":
        _append_filter_point(
            items,
            "restricted_context",
            structured_facts.get("uses_simple_evaluation_context"),
            "使用受限表达式上下文",
        )
        _append_filter_point(
            items,
            "sandbox",
            _to_flag(_has_any(bundle, "sandbox", "restricted", "safe mode")),
            "表达式或脚本沙箱",
        )
        _append_filter_point(
            items,
            "type_or_method_allowlist",
            structured_facts.get("has_expression_allowlist"),
            "类型、方法或反射目标白名单",
        )
    elif profile == "JNDII":
        _append_filter_point(
            items,
            "scheme_allowlist",
            structured_facts.get("scheme_allowlist_present"),
            "JNDI 协议或命名空间白名单",
        )
        _append_filter_point(
            items,
            "remote_codebase_block",
            structured_facts.get("blocks_remote_codebase"),
            "禁用远程 codebase 加载",
        )
        _append_filter_point(
            items,
            "local_namespace",
            structured_facts.get("uses_fixed_jndi_name"),
            "固定本地 JNDI 命名空间",
        )
    elif profile == "DESERIALIZATION":
        _append_filter_point(
            items,
            "class_whitelist",
            structured_facts.get("has_class_whitelist"),
            "反序列化类白名单",
        )
        _append_filter_point(
            items,
            "object_input_filter",
            structured_facts.get("has_object_input_filter"),
            "ObjectInputFilter 或同等机制",
        )
        _append_filter_point(
            items,
            "fastjson_safemode",
            structured_facts.get("fastjson_safemode_enabled"),
            "Fastjson safeMode",
        )
    elif profile == "SQLI":
        _append_filter_point(
            items,
            "param_binding",
            structured_facts.get("has_param_binding_calls"),
            "参数绑定或预编译语句",
        )
        _append_filter_point(
            items,
            "dynamic_fragment_allowlist",
            structured_facts.get("orderby_field_allowlist"),
            "排序字段或动态片段白名单",
        )
    elif profile == "SSRF":
        _append_filter_point(
            items,
            "scheme_allowlist",
            structured_facts.get("scheme_allowlist_present"),
            "协议白名单",
        )
        _append_filter_point(
            items,
            "private_ip_block",
            structured_facts.get("blocks_private_ip"),
            "私网与元数据地址阻断",
        )
        _append_filter_point(
            items,
            "dns_validation",
            structured_facts.get("resolves_dns_before_allow"),
            "DNS 解析后校验",
        )
        _append_filter_point(
            items,
            "egress_gateway",
            structured_facts.get("uses_proxy_or_egress_gateway"),
            "统一代理或出网网关",
        )
    elif profile == "UPLOAD":
        _append_filter_point(
            items,
            "file_type_validation",
            structured_facts.get("checks_mime_or_content_type"),
            "文件类型校验",
        )
        _append_filter_point(
            items,
            "extension_allowlist",
            structured_facts.get("has_extension_allowlist"),
            "扩展名白名单",
        )
        _append_filter_point(
            items,
            "non_public_storage",
            _invert_flag(structured_facts.get("returns_public_url_or_public_acl")),
            "避免公开访问或公共 ACL",
        )
    elif profile == "PATHTRAVERSAL":
        _append_filter_point(
            items,
            "normalize",
            structured_facts.get("uses_paths_normalize"),
            "路径 normalize",
        )
        _append_filter_point(
            items,
            "canonical_check",
            structured_facts.get("uses_canonical_path_check"),
            "canonical 路径校验",
        )
        _append_filter_point(
            items,
            "base_directory",
            structured_facts.get("enforces_base_directory"),
            "根目录约束",
        )
        _append_filter_point(
            items,
            "real_path_resolution",
            structured_facts.get("uses_real_path_resolution"),
            "real path 解析校验",
        )
    elif profile == "XXE":
        _append_filter_point(
            items,
            "doctype_disabled",
            structured_facts.get("disallows_doctype"),
            "禁用 DOCTYPE",
        )
        _append_filter_point(
            items,
            "external_entities_disabled",
            structured_facts.get("external_entities_disabled"),
            "禁用外部实体",
        )
        _append_filter_point(
            items,
            "secure_processing",
            structured_facts.get("secure_processing_enabled"),
            "安全处理模式",
        )
    elif profile == "XSS":
        _append_filter_point(
            items,
            "output_encoding",
            structured_facts.get("output_escaped"),
            "上下文编码或 HTML 转义",
        )
        _append_filter_point(
            items,
            "template_autoescape",
            structured_facts.get("uses_template_autoescape"),
            "模板自动转义",
        )
        _append_filter_point(
            items,
            "csp",
            structured_facts.get("uses_csp"),
            "CSP 或等效浏览器侧缓解",
        )
    elif profile == "SSTI":
        _append_filter_point(
            items,
            "template_sandbox",
            structured_facts.get("has_template_sandbox"),
            "模板沙箱",
        )
        _append_filter_point(
            items,
            "new_api_restriction",
            _invert_flag(structured_facts.get("freemarker_allows_new_api")),
            "限制危险模板 API",
        )
    elif profile == "REDIRECT":
        _append_filter_point(
            items,
            "relative_redirect_only",
            structured_facts.get("uses_relative_redirect_only"),
            "仅允许站内相对路径跳转",
        )
        _append_filter_point(
            items,
            "host_allowlist",
            structured_facts.get("host_allowlist_present"),
            "跳转目标域名白名单",
        )
    elif profile == "LDAPI":
        _append_filter_point(
            items,
            "ldap_escape",
            structured_facts.get("has_ldap_escape"),
            "LDAP 特殊字符转义",
        )
        _append_filter_point(
            items,
            "parameterized_ldap",
            structured_facts.get("uses_parameterized_ldap"),
            "参数化 LDAP 查询或 SearchControls",
        )
        _append_filter_point(
            items,
            "search_base_scope",
            structured_facts.get("restricts_search_base"),
            "限制搜索基准范围",
        )
    elif profile == "HPE":
        _append_filter_point(
            items,
            "authorization_check",
            structured_facts.get("has_authorization_check"),
            "权限校验",
        )
        _append_filter_point(
            items,
            "query_scope",
            structured_facts.get("query_scoped_by_user"),
            "按用户或租户约束查询",
        )
    elif profile == "CORS":
        _append_filter_point(
            items,
            "origin_allowlist",
            structured_facts.get("origin_allowlist_present"),
            "Origin 白名单",
        )
        _append_filter_point(
            items,
            "allow_credentials",
            _invert_flag(structured_facts.get("allow_credentials_true")),
            "避免对敏感接口开放凭证跨域",
        )
        _append_filter_point(
            items,
            "security_chain",
            structured_facts.get("configured_in_security_chain"),
            "统一 Security/CORS 配置",
        )
    elif profile == "MISCONFIG":
        _append_filter_point(
            items,
            "auth_protection",
            structured_facts.get("protected_by_auth"),
            "鉴权保护",
        )
        _append_filter_point(
            items,
            "ip_restriction",
            structured_facts.get("ip_restricted"),
            "IP 白名单或网关限制",
        )
        _append_filter_point(
            items,
            "dev_only",
            structured_facts.get("only_dev_profile"),
            "仅开发环境启用",
        )
    elif profile == "INFOLEAK":
        _append_filter_point(
            items,
            "global_exception_handler",
            structured_facts.get("has_global_exception_handler"),
            "统一异常处理",
        )
        _append_filter_point(
            items,
            "server_side_logging",
            structured_facts.get("only_logs_exception"),
            "仅保留服务端日志，不回显异常细节",
        )
        _append_filter_point(
            items,
            "hide_prod_details",
            structured_facts.get("hides_details_in_prod"),
            "生产环境隐藏细节",
        )
    elif profile == "HARDCODE_SECRET":
        _append_filter_point(
            items,
            "env_rotation",
            structured_facts.get("rotatable_via_env"),
            "通过环境变量或密钥中心注入",
        )
    elif profile == "WEAK_PASSWORD":
        _append_filter_point(
            items,
            "prod_override",
            _invert_flag(structured_facts.get("prod_profile_enabled")),
            "避免在生产环境启用默认弱口令",
        )
    elif profile == "WEAK_HASH":
        _append_filter_point(
            items, "salt", structured_facts.get("has_salt"), "加盐或迭代保护"
        )
        _append_filter_point(
            items,
            "legacy_only",
            structured_facts.get("legacy_compat_only"),
            "仅用于兼容性场景",
        )
    elif profile == "COOKIE_FLAGS":
        _append_filter_point(
            items, "http_only", structured_facts.get("cookie_http_only_set"), "HttpOnly"
        )
        _append_filter_point(
            items, "secure", structured_facts.get("cookie_secure_set"), "Secure"
        )
        _append_filter_point(
            items, "samesite", structured_facts.get("cookie_samesite_set"), "SameSite"
        )
    return items


def _build_missing_evidence(
    *,
    profile: str,
    structured_facts: dict[str, object],
) -> list[str]:
    hints = PROFILE_MISSING_EVIDENCE.get(
        profile, PROFILE_MISSING_EVIDENCE.get("GENERIC", [])
    )
    missing: list[str] = []
    unknown_count = sum(1 for value in structured_facts.values() if value == UNKNOWN)
    for item in hints:
        if len(missing) >= 5:
            break
        if unknown_count == 0 and len(missing) >= 2:
            break
        missing.append(item)
    if not missing and unknown_count:
        missing.append("补齐与当前漏洞类型直接相关的防护代码和配置证据。")
    return missing


def _build_expanded_code_context(
    *,
    code_context: dict[str, str],
    data_flow_chain: list[dict[str, object]],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in ("focus", "source", "sink"):
        text = code_context.get(key)
        if text:
            payload[key] = _truncate_text(text, 1200)
    path_steps: list[dict[str, object]] = []
    for item in data_flow_chain[:6]:
        entry = {
            "step_order": item.get("step_order"),
            "location": item.get("location"),
            "display_name": item.get("display_name"),
            "node_kind": item.get("node_kind"),
            "code_snippet": _truncate_text(
                str(item.get("code_snippet") or "").strip(), 300
            )
            or None,
        }
        if any(value for value in entry.values() if value not in {None, ""}):
            path_steps.append(entry)
    if path_steps:
        payload["path_steps"] = path_steps
    return payload


def _append_filter_point(
    items: list[dict[str, str]],
    key: str,
    flag: object,
    label: str,
) -> None:
    normalized_flag = str(flag or UNKNOWN)
    status = "unknown"
    if normalized_flag == YES:
        status = "present"
    elif normalized_flag == NO:
        status = "missing"
    items.append({"kind": key, "status": status, "detail": label})


def _invert_flag(value: object) -> str:
    if value == YES:
        return NO
    if value == NO:
        return YES
    return UNKNOWN


def _control_flag(*, control: bool, risky: bool) -> str:
    if control:
        return YES
    if risky:
        return NO
    return UNKNOWN


def _safe_args_flag(*, bundle: dict[str, object], shell_wrapper: bool) -> str:
    if shell_wrapper:
        return NO
    if _has_any(bundle, "processbuilder", "new string[]", "arrays.aslist"):
        return YES
    return UNKNOWN


def _constant_command_flag(*, bundle: dict[str, object], risky: bool) -> str:
    if risky:
        return NO
    sink = str(bundle.get("sink") or "")
    if 'exec("' in sink.lower() or 'processbuilder("' in sink.lower():
        return YES
    return UNKNOWN


def _has_any(bundle: dict[str, object], *tokens: str) -> bool:
    haystack = str(bundle.get("combined_lower") or "")
    return any(token.lower() in haystack for token in tokens if token)


def _to_flag(value: bool) -> str:
    return YES if value else UNKNOWN


def _normalize_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max(0, max_length - 1)] + "…"


def _collect_text_fragments(
    value: object,
    *,
    parts: list[str],
    prefix: str | None = None,
    depth: int = 0,
) -> None:
    if depth > 3 or len(parts) >= 200:
        return
    if isinstance(value, dict):
        for key, item in list(value.items())[:12]:
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _collect_text_fragments(
                item, parts=parts, prefix=next_prefix, depth=depth + 1
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value[:12]):
            next_prefix = f"{prefix}[{index}]" if prefix else str(index)
            _collect_text_fragments(
                item, parts=parts, prefix=next_prefix, depth=depth + 1
            )
        return
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        if not text:
            return
        parts.append(f"{prefix}={text}" if prefix else text)
