from __future__ import annotations

import os
import re
import uuid
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.services.source_location_service import resolve_snapshot_relative_source_path

VULN_TYPE_DISPLAY: dict[str, str] = {
    "SQLI": "SQL Injection",
    "XSS": "Cross-Site Scripting",
    "SSRF": "Server-Side Request Forgery",
    "XXE": "XML External Entity",
    "RCE": "Remote Code Execution",
    "UPLOAD": "Arbitrary File Upload",
}

RULE_KEY_DISPLAY: dict[str, str] = {
    "config_secret_hardcode": "Hardcoded Secret",
    "config_secret_weekpass": "Weak Password",
    "id_mybatis_hpe": "Horizontal Privilege Escalation",
    "pom_log4j_codei": "Remote Code Execution",
    "any_any_upload": "Arbitrary File Upload",
    "any_mybatis_sqli": "SQL Injection",
}

MAPPING_METHODS: dict[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

STRING_LITERAL_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
REQUEST_METHOD_RE = re.compile(r"RequestMethod\.([A-Z]+)")
METHOD_DECL_RE = re.compile(r"\b(public|protected|private)\b.*\(")
CLASS_DECL_RE = re.compile(r"\b(class|interface|enum)\b")


def build_finding_presentation(
    *,
    version_id: uuid.UUID,
    rule_key: str,
    vuln_type: str | None,
    source_file: str | None,
    source_line: int | None,
    file_path: str | None,
    line_start: int | None,
) -> dict[str, str | None]:
    vuln_display_name = build_vuln_display_name(rule_key=rule_key, vuln_type=vuln_type)
    entry_display, entry_kind = build_entry_display(
        version_id=version_id,
        source_file=source_file,
        source_line=source_line,
        fallback_file_path=file_path,
        fallback_line=line_start,
    )
    return {
        "vuln_display_name": vuln_display_name,
        "entry_display": entry_display,
        "entry_kind": entry_kind,
    }


def build_vuln_display_name(*, rule_key: str, vuln_type: str | None) -> str:
    normalized_rule_key = (rule_key or "").strip()
    normalized_vuln_type = (vuln_type or "").strip().upper()
    if normalized_rule_key in RULE_KEY_DISPLAY:
        return RULE_KEY_DISPLAY[normalized_rule_key]
    if normalized_vuln_type in VULN_TYPE_DISPLAY:
        return VULN_TYPE_DISPLAY[normalized_vuln_type]
    if normalized_vuln_type == "CUSTOM" and normalized_rule_key:
        return _titleize_rule_key(normalized_rule_key)
    if normalized_rule_key:
        return _titleize_rule_key(normalized_rule_key)
    return "Unknown Vulnerability"


def build_entry_display(
    *,
    version_id: uuid.UUID,
    source_file: str | None,
    source_line: int | None,
    fallback_file_path: str | None,
    fallback_line: int | None,
) -> tuple[str | None, str | None]:
    route_display = resolve_route_display(
        version_id=version_id,
        source_file=source_file,
        source_line=source_line,
    )
    if route_display:
        return route_display, "route"

    location_display = _format_location(
        file_path=fallback_file_path or source_file,
        line=fallback_line or source_line,
    )
    if location_display:
        return location_display, "file"
    return None, None


def resolve_route_display(
    *, version_id: uuid.UUID, source_file: str | None, source_line: int | None
) -> str | None:
    normalized_source_file = (source_file or "").strip()
    if not normalized_source_file or source_line is None or source_line <= 0:
        return None
    return _resolve_route_display_cached(
        str(version_id), normalized_source_file, int(source_line)
    )


@lru_cache(maxsize=2048)
def _resolve_route_display_cached(
    version_id_text: str, source_file: str, source_line: int
) -> str | None:
    version_id = uuid.UUID(version_id_text)
    relative_path = resolve_snapshot_relative_source_path(
        version_id=version_id,
        raw_path=source_file,
    )
    if not relative_path or not relative_path.lower().endswith(".java"):
        return None

    lines = _read_snapshot_lines(version_id=version_id, relative_path=relative_path)
    if not lines:
        return None

    method_decl_index = _find_method_decl_index(lines=lines, source_line=source_line)
    if method_decl_index is None:
        return None

    class_decl_index = _find_class_decl_index(
        lines=lines, upper_bound=method_decl_index
    )
    class_annotations = (
        _collect_annotations(lines=lines, decl_index=class_decl_index)
        if class_decl_index is not None
        else []
    )
    method_annotations = _collect_annotations(lines=lines, decl_index=method_decl_index)
    if not class_annotations and not method_annotations:
        return None

    class_path, _ = _extract_mapping(class_annotations)
    method_path, http_method = _extract_mapping(method_annotations)
    route_path = _combine_route_paths(class_path, method_path)
    if not route_path:
        return None
    if http_method:
        return f"{http_method} {route_path}"
    return route_path


def _read_snapshot_lines(*, version_id: uuid.UUID, relative_path: str) -> list[str]:
    source_root = _snapshot_source_root(version_id=version_id)
    source_file = source_root / relative_path
    if not source_file.exists() or not source_file.is_file():
        return []
    try:
        return source_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _snapshot_source_root(*, version_id: uuid.UUID) -> Path:
    snapshot_root = Path(os.path.normpath(str(get_settings().snapshot_storage_root)))
    if not snapshot_root.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        snapshot_root = backend_root / snapshot_root
    return snapshot_root / str(version_id) / "source"


def _find_method_decl_index(*, lines: list[str], source_line: int) -> int | None:
    start = min(max(source_line - 1, 0), len(lines) - 1)
    lower_bound = max(0, start - 40)
    current_stripped = lines[start].strip()
    if current_stripped.startswith("@") and not current_stripped.startswith(
        ("@RequestParam", "@PathVariable", "@RequestBody", "@Param")
    ):
        upper_bound = min(len(lines) - 1, start + 10)
        for index in range(start, upper_bound + 1):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("@") or stripped.startswith("//"):
                continue
            if METHOD_DECL_RE.search(stripped):
                return index
    for index in range(start, lower_bound - 1, -1):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("@") or stripped.startswith("//"):
            continue
        if METHOD_DECL_RE.search(stripped):
            return index
    upper_bound = min(len(lines) - 1, start + 10)
    for index in range(start, upper_bound + 1):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("@") or stripped.startswith("//"):
            continue
        if METHOD_DECL_RE.search(stripped):
            return index
    for index in range(start, lower_bound - 1, -1):
        stripped = lines[index].strip()
        if _looks_like_method_declaration(stripped):
            return index
    for index in range(start, upper_bound + 1):
        stripped = lines[index].strip()
        if _looks_like_method_declaration(stripped):
            return index
    return None


def _looks_like_method_declaration(stripped: str) -> bool:
    if not stripped or stripped.startswith(
        ("@", "//", "if", "for", "while", "switch", "catch")
    ):
        return False
    if stripped.startswith(("public ", "protected ", "private ")) and "(" in stripped:
        return True
    if " throws " in stripped and "(" in stripped:
        return True
    if stripped.endswith("{") and "(" in stripped:
        return True
    return False


def _find_class_decl_index(*, lines: list[str], upper_bound: int) -> int | None:
    for index in range(min(upper_bound, len(lines) - 1), -1, -1):
        if CLASS_DECL_RE.search(lines[index]):
            return index
    return None


def _collect_annotations(*, lines: list[str], decl_index: int) -> list[str]:
    collected_reversed: list[str] = []
    current_parts: list[str] = []
    paren_balance = 0

    for index in range(decl_index - 1, -1, -1):
        stripped = lines[index].strip()
        if not stripped:
            if current_parts:
                break
            continue
        if current_parts:
            current_parts.insert(0, stripped)
            paren_balance += stripped.count("(") - stripped.count(")")
            if stripped.startswith("@") and paren_balance <= 0:
                collected_reversed.append(" ".join(current_parts))
                current_parts = []
                paren_balance = 0
            continue
        if stripped.startswith("@"):
            current_parts = [stripped]
            paren_balance = stripped.count("(") - stripped.count(")")
            if paren_balance <= 0:
                collected_reversed.append(stripped)
                current_parts = []
                paren_balance = 0
            continue
        break

    if current_parts:
        collected_reversed.append(" ".join(current_parts))
    collected_reversed.reverse()
    return collected_reversed


def _extract_mapping(annotations: list[str]) -> tuple[str | None, str | None]:
    for annotation in annotations:
        stripped = annotation.strip()
        for annotation_name, http_method in MAPPING_METHODS.items():
            if stripped.startswith(f"@{annotation_name}"):
                return _extract_path_literal(stripped), http_method
        if not stripped.startswith("@RequestMapping"):
            continue
        return _extract_path_literal(stripped), _extract_request_method(stripped)
    return None, None


def _extract_path_literal(annotation: str) -> str | None:
    for key in ("value", "path"):
        keyed_match = re.search(rf"{key}\s*=\s*(\{{.*?\}}|\".*?\")", annotation)
        if keyed_match:
            value = keyed_match.group(1)
            literal = _extract_first_string_literal(value)
            if literal:
                return literal
    return _extract_first_string_literal(annotation)


def _extract_first_string_literal(value: str) -> str | None:
    match = STRING_LITERAL_RE.search(value)
    if not match:
        return None
    return match.group(1).strip() or None


def _extract_request_method(annotation: str) -> str | None:
    match = REQUEST_METHOD_RE.search(annotation)
    if not match:
        return None
    return match.group(1).strip().upper() or None


def _combine_route_paths(class_path: str | None, method_path: str | None) -> str | None:
    parts = []
    for item in (class_path, method_path):
        normalized = (item or "").strip()
        if not normalized:
            continue
        parts.append(normalized.strip("/"))
    if not parts:
        return None
    joined = "/".join(part for part in parts if part)
    return f"/{joined}" if joined else "/"


def _format_location(*, file_path: str | None, line: int | None) -> str | None:
    normalized_file_path = (file_path or "").strip()
    if not normalized_file_path:
        return None
    if line is not None and line > 0:
        return f"{normalized_file_path}:{line}"
    return normalized_file_path


def _titleize_rule_key(rule_key: str) -> str:
    normalized = (rule_key or "").strip().replace("-", "_")
    if not normalized:
        return "Unknown Vulnerability"
    parts = [part for part in normalized.split("_") if part]
    if not parts:
        return normalized
    noise_tokens = {"any", "other", "id", "java", "pom", "config"}
    filtered = [part for part in parts if part.lower() not in noise_tokens]
    tokens = filtered or parts
    return " ".join(
        token.upper() if token.isupper() else token.capitalize() for token in tokens
    )
